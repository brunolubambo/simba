"""Servidor central (roda no PC). PC e celular abrem o mesmo app web e compartilham o mesmo Simba.
WebSocket /ws?token=...&device=pc|celular
  entrada: {type:message,text} | {type:approve,id,ok} | {type:accept,id} | {type:dismiss,id} | {type:reminder_snooze,id,min} | {type:observer,on}
  saída:   text | tool | done | approval | approval_closed | suggestion | activity | status | error
HTTP: POST /upload?token= (imagem do celular, ex.: Atalho do iOS) | POST /push/subscribe | GET /push/key
      POST /tts?token= ({text} -> {id}) + GET /tts/{id}?token= (voz neural em MP3, transmitida) | POST /telegram/webhook (mensagens do bot, ver telegram.py)"""
import asyncio, json, os, re, secrets, sys, time
from datetime import date
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
# google.py deste projeto não pode sombrear a biblioteca Google.
# Isso acontece quando o servidor sobe com a pasta do repositório no sys.path.
_pkg = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _pkg]
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Query, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from .config import ROOT, WORKSPACE, ACCOUNTS, public_url
from .core import Simba
from .hub import Hub, save_sub, send_push, vapid, PUSH_TOO
from .observer import Observer
from . import tasks, life, google, memory, telegram
from .agents import roster

TOKEN = os.getenv("SIMBA_TOKEN", "")
AUTO_ACT = os.getenv("SIMBA_AUTO", "true").lower() == "true"     # executa sugestões sem pedir clique
VOICE = os.getenv("SIMBA_VOICE", "pt-BR-AntonioNeural")          # voz neural usada pelo app (edge-tts)
VOICE_RATE = os.getenv("SIMBA_VOICE_RATE", "-4%")               # velocidade: ex. "+0%", "-10%"
VOICE_PITCH = os.getenv("SIMBA_VOICE_PITCH", "-6Hz")            # tom: negativo = mais grave, ex. "-10Hz"
STATS = {"start": time.time(), "day": date.today().isoformat(), "tasks": 0, "cost": 0.0}
hub = Hub()
state: dict = {}


def check(token: str):
    if not TOKEN or not secrets.compare_digest(token, TOKEN):
        raise HTTPException(401, "token inválido")


async def run_and_broadcast(text: str, origin: str):
    await hub.broadcast({"type": "user", "text": text, "device": origin})
    final: list[str] = []                    # texto depois da última ferramenta = a resposta final
    try:
        async for ev in state["simba"].ask(text):
            await hub.broadcast(ev)
            kind = ev.get("type")
            if kind == "text":
                final.append(ev["text"])
            elif kind == "tool" or (kind == "agent" and ev.get("state") == "working"):
                final = []
            elif kind == "done":
                if STATS["day"] != date.today().isoformat():
                    STATS.update(day=date.today().isoformat(), tasks=0, cost=0.0)
                STATS["tasks"] += 1
                STATS["cost"] += ev.get("cost_usd") or 0
        last = "\n\n".join(t.strip() for t in final if t.strip())
        if origin == "telegram" and not last:
            last = "Feito."
        sent = False
        if last and origin in ("rotina", "proativo", "telegram"):   # chegam no Telegram mesmo com o app fechado
            sent = await telegram.deliver(last, origin)
        if origin == "rotina" and last and (not sent or PUSH_TOO):
            await asyncio.to_thread(send_push, {"titulo": "SIMBA", "motivo": last})
    except Exception as e:
        await hub.broadcast({"type": "error", "text": str(e)})
        if origin == "telegram":
            await telegram.deliver(f"Não consegui concluir: {e}"[:500], origin)


def status() -> dict:
    ok = google.authorized()
    return {"type": "status", "devices": hub.devices(), "observer": state["observer"].enabled,
            "observer_available": state["observer"].available,
            "google": {c: {"email": e, "ok": c in ok} for c, e in ACCOUNTS.items()},
            "telegram": telegram.snapshot()}


@asynccontextmanager
async def lifespan(app):
    state["simba"] = Simba(hub.approve)
    if AUTO_ACT:
        async def act(s):
            asyncio.create_task(run_and_broadcast(s["acao"], "proativo"))
        hub.on_suggest = act
    state["observer"] = Observer(hub)
    telegram.setup(hub, run_and_broadcast)
    hub.mirror = telegram.notify
    telegram.spawn()
    bg = [asyncio.create_task(c) for c in (
        state["simba"].warm(), state["observer"].run(), tasks.reminders_loop(hub), tasks.routines_loop(run_and_broadcast),
        tasks.mail_loop(hub), tasks.calendar_loop(hub))]
    yield
    for t in bg:
        t.cancel()
    await telegram.stop()
    await state["simba"].stop()


app = FastAPI(title="Simba", lifespan=lifespan)


@app.websocket("/ws")
async def ws(socket: WebSocket, token: str = "", device: str = "pc"):
    if not TOKEN or not secrets.compare_digest(token, TOKEN):
        await socket.close(code=4401)
        return
    await socket.accept()
    hub.add(socket, device)
    await hub.broadcast(status())
    tasks = set()
    try:
        while True:
            data = json.loads(await socket.receive_text())
            kind = data.get("type")
            if kind == "message" and data.get("text", "").strip():
                t = asyncio.create_task(run_and_broadcast(data["text"], device))
                tasks.add(t); t.add_done_callback(tasks.discard)
            elif kind == "approve":
                hub.resolve(data.get("id", ""), data.get("ok", False))
            elif kind == "accept":
                s = hub.suggestions.pop(data.get("id", ""), None)
                if s:
                    t = asyncio.create_task(run_and_broadcast(s["acao"], device))
                    tasks.add(t); t.add_done_callback(tasks.discard)
            elif kind == "reminder_snooze":
                life.snooze(int(data.get("id", 0)), int(data.get("min", 10)))
            elif kind == "dismiss":
                hub.suggestions.pop(data.get("id", ""), None)
            elif kind == "observer":
                state["observer"].enabled = bool(data.get("on"))
                await hub.broadcast(status())
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(socket)
        await hub.broadcast(status())


@app.post("/upload")
async def upload(file: UploadFile = File(...), token: str = Query(""), note: str = Query("")):
    """Tela do celular: o Atalho do iOS / app do Android envia um print aqui."""
    check(token)
    inbox = WORKSPACE / ".inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    ext = (file.filename or "img.png").rsplit(".", 1)[-1][:5]
    path = inbox / f"celular_{int(time.time())}.{ext}"
    path.write_bytes(await file.read())
    prompt = (f"O usuário enviou uma captura da tela do CELULAR em {path}. Leia a imagem com Read. "
              f"{('Pedido: ' + note) if note else 'Entenda o que ele está fazendo e antecipe: diga o que você faria e faça o que for seguro.'}")
    asyncio.create_task(run_and_broadcast(prompt, "celular"))
    return {"ok": True}


@app.get("/push/key")
def push_key(token: str = Query("")):
    check(token)
    return {"key": vapid()[1]}


@app.get("/painel")
def painel(token: str = Query("")):
    check(token)
    import sqlite3
    with life.db() as c:
        pend = c.execute("SELECT COUNT(*) FROM lembretes WHERE feito=0").fetchone()[0]
    return {"agents": roster(), "auto": AUTO_ACT, "lembretes": pend, "memoria": memory.stats(),
            "stats": {"uptime_s": int(time.time() - STATS["start"]), "tarefas_hoje": STATS["tasks"],
                      "custo_hoje": round(STATS["cost"], 4)}}


@app.get("/memoria.zip")
def memoria_zip(token: str = Query("")):
    check(token)
    return Response(memory.export_zip(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=simba-memoria-obsidian.zip"})


def speech_pieces(text: str, limit: int = 1800) -> list[str]:
    """Parte o texto em falas que o edge-tts aceita, sem cortar o conteúdo."""
    parts, buf = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        while len(sentence) > limit:
            parts.append(sentence[:limit].strip())
            sentence = sentence[limit:].strip()
        if buf and len(buf) + 1 + len(sentence) > limit:
            parts.append(buf)
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip() if buf else sentence
    if buf:
        parts.append(buf)
    return [p for p in parts if p]


TTS_JOBS: dict[str, str] = {}


@app.post("/tts")
async def tts(body: dict = Body(...), token: str = Query("")):
    """Guarda a fala e devolve um id. O player abre GET /tts/{id}, que toca enquanto o áudio ainda chega."""
    check(token)
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(400, "texto vazio")
    while len(TTS_JOBS) >= 20:
        TTS_JOBS.pop(next(iter(TTS_JOBS)))
    job = secrets.token_urlsafe(12)
    TTS_JOBS[job] = text
    return {"id": job}


@app.get("/tts/{job}")
async def tts_stream(job: str, token: str = Query("")):
    """Voz neural em MP3, enviada pedaço a pedaço. Se falhar antes do primeiro pedaço, o app usa a voz do celular."""
    check(token)
    text = TTS_JOBS.pop(job, None)
    if not text:
        raise HTTPException(404, "fala expirada")

    async def audio():
        import edge_tts
        for piece in speech_pieces(text):
            async for chunk in edge_tts.Communicate(piece, VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH).stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

    chunks = audio()
    try:
        first = await chunks.__anext__()
    except Exception as e:
        raise HTTPException(503, f"voz indisponível: {e}"[:200])

    async def body():
        yield first
        async for data in chunks:
            yield data

    return StreamingResponse(body(), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/google/connect")
def google_connect(conta: str, token: str = Query("")):
    check(token)
    try:
        return RedirectResponse(google.start_web_auth(conta, public_url() + "/google/callback"))
    except Exception as e:
        return RedirectResponse("/?google=" + f"erro: {e}"[:200])


@app.get("/google/callback")
async def google_callback(state: str = "", code: str = "", error: str = ""):
    if error or not code:
        return RedirectResponse(f"/?google=erro: {error or 'cancelado'}")
    try:
        conta, email = await asyncio.to_thread(google.finish_web_auth, state, code)
    except Exception as e:
        return RedirectResponse("/?google=" + f"erro: {e}"[:200])
    await hub.broadcast(status())
    return RedirectResponse(f"/?google=ok: {conta} ({email}) conectada")


@app.post("/push/subscribe")
def push_subscribe(sub: dict = Body(...), token: str = Query("")):
    check(token)
    save_sub(sub)
    return {"ok": True}


@app.post("/telegram/token")
async def telegram_token(body: dict = Body(...), token: str = Query("")):
    """Guarda o token do @BotFather depois de o Telegram aceitar. Não devolve o token."""
    check(token)
    try:
        username = await telegram.save_bot_token(str(body.get("bot_token", "")))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await hub.broadcast(status())
    return {"ok": True, "username": username}


@app.post("/telegram/confirm")
async def telegram_confirm(body: dict = Body(...), token: str = Query("")):
    """Liga o chat com o código de 6 dígitos que o bot mostrou no /start."""
    check(token)
    try:
        text = await asyncio.to_thread(telegram.confirm, str(body.get("codigo", "")))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await hub.broadcast(status())
    return {"ok": True, "text": text}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """O Telegram entrega aqui as mensagens e os toques nos botões do bot (conferido pelo cabeçalho secreto)."""
    if not telegram.valid_secret(request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")):
        raise HTTPException(401, "não autorizado")
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}
    asyncio.create_task(telegram.handle_update(update))
    return {"ok": True}


app.mount("/", StaticFiles(directory=ROOT / "pwa", html=True), name="pwa")
