"""Servidor central (roda no PC). PC e celular abrem o mesmo app web e compartilham o mesmo Simba.
WebSocket /ws?token=...&device=pc|celular
  entrada: {type:message,text} | {type:approve,id,ok} | {type:accept,id} | {type:dismiss,id} | {type:reminder_snooze,id,min} | {type:observer,on}
  saída:   text | tool | done | approval | approval_closed | suggestion | activity | status | error
HTTP: POST /upload?token= (imagem do celular, ex.: Atalho do iOS) | POST /push/subscribe | GET /push/key"""
import asyncio, json, os, secrets, time
from datetime import date
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Query, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, Response
from .config import ROOT, WORKSPACE, ACCOUNTS, public_url
from .core import Simba
from .hub import Hub, save_sub, send_push, vapid
from .observer import Observer
from . import tasks, life, google, memory
from .agents import roster

TOKEN = os.getenv("SIMBA_TOKEN", "")
AUTO_ACT = os.getenv("SIMBA_AUTO", "true").lower() == "true"     # executa sugestões sem pedir clique
STATS = {"start": time.time(), "day": date.today().isoformat(), "tasks": 0, "cost": 0.0}
hub = Hub()
state: dict = {}


def check(token: str):
    if not TOKEN or not secrets.compare_digest(token, TOKEN):
        raise HTTPException(401, "token inválido")


async def run_and_broadcast(text: str, origin: str):
    await hub.broadcast({"type": "user", "text": text, "device": origin})
    last = ""
    try:
        async for ev in state["simba"].ask(text):
            await hub.broadcast(ev)
            if ev.get("type") == "text":
                last = ev["text"]
            elif ev.get("type") == "done":
                if STATS["day"] != date.today().isoformat():
                    STATS.update(day=date.today().isoformat(), tasks=0, cost=0.0)
                STATS["tasks"] += 1
                STATS["cost"] += ev.get("cost_usd") or 0
        if origin == "rotina" and last:      # rotinas chegam no celular mesmo com o app fechado
            await asyncio.to_thread(send_push, {"titulo": "SIMBA", "motivo": last})
    except Exception as e:
        await hub.broadcast({"type": "error", "text": str(e)})


def status() -> dict:
    ok = google.authorized()
    return {"type": "status", "devices": hub.devices(), "observer": state["observer"].enabled,
            "observer_available": state["observer"].available,
            "google": {c: {"email": e, "ok": c in ok} for c, e in ACCOUNTS.items()}}


@asynccontextmanager
async def lifespan(app):
    state["simba"] = Simba(hub.approve)
    if AUTO_ACT:
        async def act(s):
            asyncio.create_task(run_and_broadcast(s["acao"], "proativo"))
        hub.on_suggest = act
    state["observer"] = Observer(hub)
    bg = [asyncio.create_task(c) for c in (
        state["observer"].run(), tasks.reminders_loop(hub), tasks.routines_loop(run_and_broadcast),
        tasks.mail_loop(hub), tasks.calendar_loop(hub))]
    yield
    for t in bg:
        t.cancel()
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


app.mount("/", StaticFiles(directory=ROOT / "pwa", html=True), name="pwa")
