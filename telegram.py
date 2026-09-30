"""Telegram: o SIMBA manda para o Bruno lembretes, aprovações, rotinas, avisos e documentos,
e também recebe pedidos, fotos e arquivos por lá.

Variáveis (Railway → Variables):
  TELEGRAM_BOT_TOKEN   token que o @BotFather entrega ao criar o bot (obrigatório)
  TELEGRAM_CHAT_ID     opcional: fixa o chat à mão (normalmente o vínculo é feito pelo código abaixo)
  SIMBA_PUSH_TAMBEM    opcional: "true" para receber a notificação do app além do Telegram

Vínculo (uma vez só): abra o bot no Telegram e toque em Iniciar. O bot responde com um código de 6 dígitos;
diga ao SIMBA no app "o código do Telegram é 123456". Só quem tem acesso ao app consegue confirmar,
então ninguém mais consegue se ligar ao seu SIMBA pelo Telegram. Mensagens de outros chats são ignoradas.

Sem TELEGRAM_BOT_TOKEN nada disto faz coisa alguma."""
import asyncio, hashlib, hmac, html, json, mimetypes, os, re, secrets, time, uuid
import urllib.error, urllib.request
from pathlib import Path
from claude_agent_sdk import tool, create_sdk_mcp_server
from .config import DATA, WORKSPACE, public_url
from .toolkit import schema, safe
from . import life

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
STATE = DATA / "telegram.json"
API = "https://api.telegram.org"
LIMIT = 3500                       # o Telegram aceita 4096 caracteres por mensagem; sobra folga para a formatação
CODE_TTL = 15 * 60                 # o código de vínculo vale 15 minutos
MAX_UPLOAD = 49 * 1024 * 1024      # bots enviam até 50 MB
MAX_DOWNLOAD = 20 * 1024 * 1024    # e baixam até 20 MB
_ctx: dict = {}                    # hub e função que roda um pedido no SIMBA (preenchidos por setup)
_approval_msgs: dict[str, tuple[int, int]] = {}   # aprovação -> (chat, mensagem), para tirar os botões depois


# ---------- estado ----------
def enabled() -> bool:
    return bool(TOKEN)


def _load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save(d: dict):
    STATE.write_text(json.dumps(d, ensure_ascii=False))


def chat_id() -> int | None:
    env = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if env.lstrip("-").isdigit():
        return int(env)
    c = _load().get("chat_id")
    return int(c) if c else None


def ready() -> bool:
    """Configurado e ligado a um chat: pronto para mandar mensagens."""
    return enabled() and chat_id() is not None


def setup(hub, run):
    """Chamado pelo servidor ao iniciar: hub (aprovações, sugestões) e a função que executa um pedido."""
    _ctx.update(hub=hub, run=run)


# ---------- API do Telegram (síncrona: chame numa thread) ----------
def _call(method: str, params: dict | None = None, files: dict | None = None, timeout: float = 30) -> dict:
    """Devolve o JSON do Telegram, também em caso de erro ({"ok": False, "description": ...}).
    Nunca registra a URL, porque ela contém o token."""
    url = f"{API}/bot{TOKEN}/{method}"
    if files:
        boundary = uuid.uuid4().hex
        body = bytearray()
        for k, v in (params or {}).items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, (name, data, ctype) in files.items():
            name = name.replace('"', "'")
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                     f"Content-Type: {ctype}\r\n\r\n").encode() + data + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=bytes(body),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        req = urllib.request.Request(url, data=json.dumps(params or {}, ensure_ascii=False).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "description": f"{type(e).__name__}"}


def _fetch_file(file_path: str) -> bytes:
    with urllib.request.urlopen(f"{API}/file/bot{TOKEN}/{file_path}", timeout=60) as r:
        return r.read()


# ---------- formatação ----------
def _html(md: str) -> str:
    """Markdown simples do Claude -> HTML do Telegram (negrito, código, títulos, links e listas)."""
    out = []
    for part in re.split(r"(```.*?```)", md, flags=re.S):
        if part.startswith("```") and part.endswith("```") and len(part) >= 6:
            code = re.sub(r"^```[\w+-]*\n?", "", part)[:-3]
            out.append(f"<pre>{html.escape(code, quote=False)}</pre>")
            continue
        t = html.escape(part, quote=False)
        t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)",
                   lambda m: f'<a href="{m.group(2).replace(chr(34), "%22")}">{m.group(1)}</a>', t)
        t = re.sub(r"^#{1,6}\s*(.+)$", lambda m: "<b>" + m.group(1).replace("**", "") + "</b>", t, flags=re.M)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"(?m)^(\s*)[-*]\s+", r"\1• ", t)
        out.append(t)
    return "".join(out)


def _plain(md: str) -> str:
    t = re.sub(r"```[\w+-]*\n?", "", md)
    t = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)", r"\1 (\2)", t)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    return t.replace("**", "").replace("`", "")


def _chunks(text: str, size: int = LIMIT) -> list[str]:
    out, rest = [], text.strip()
    while len(rest) > size:
        cut = rest.rfind("\n", 0, size)
        if cut < size // 2:
            cut = rest.rfind(" ", 0, size)
        if cut < size // 2:
            cut = size
        out.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        out.append(rest)
    return out


def _parse_error(r: dict) -> bool:
    return not r.get("ok") and "parse" in str(r.get("description", "")).lower()


# ---------- envio ----------
def send_text(text: str, buttons: list | None = None, chat: int | None = None) -> int | None:
    """Manda texto (em partes, se for longo). Devolve o id da última mensagem, ou None se não enviou."""
    chat = chat or chat_id()
    if not (enabled() and chat and text and text.strip()):
        return None
    pieces = _chunks(text)
    last = None
    for i, piece in enumerate(pieces):
        params = {"chat_id": chat, "text": _html(piece), "parse_mode": "HTML",
                  "link_preview_options": {"is_disabled": True}}
        if buttons and i == len(pieces) - 1:
            params["reply_markup"] = {"inline_keyboard": buttons}
        r = _call("sendMessage", params)
        if _parse_error(r):                       # formatação recusada: manda como texto simples
            params.pop("parse_mode")
            params["text"] = _plain(piece)
            r = _call("sendMessage", params)
        if not r.get("ok"):
            print(f"[telegram] mensagem não enviada: {str(r.get('description', ''))[:160]}")
            return None
        last = r["result"]["message_id"]
    return last


def _resolve(path: str) -> Path:
    """Só arquivos do workspace (onde o SIMBA cria documentos) podem ser enviados."""
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE / p
    p = p.resolve()
    try:
        p.relative_to(WORKSPACE.resolve())
    except ValueError:
        raise ValueError("só posso enviar arquivos que estão no workspace do SIMBA")
    if not p.is_file():
        raise FileNotFoundError(f"arquivo não encontrado: {p.name}")
    return p


def send_file(path: str, caption: str = "", chat: int | None = None) -> int:
    chat = chat or chat_id()
    p = _resolve(path)
    data = p.read_bytes()
    if len(data) > MAX_UPLOAD:
        raise ValueError("arquivo maior que 50 MB")
    cap = (caption or "").strip()
    if len(cap) > 900:                            # legenda tem limite de 1024 caracteres: manda o texto antes
        send_text(cap, chat=chat)
        cap = ""
    params = {"chat_id": chat}
    if cap:
        params.update(caption=_html(cap), parse_mode="HTML")
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    r = _call("sendDocument", params, files={"document": (p.name, data, ctype)}, timeout=120)
    if _parse_error(r):
        params.pop("parse_mode")
        params["caption"] = _plain(cap)
        r = _call("sendDocument", params, files={"document": (p.name, data, ctype)}, timeout=120)
    if not r.get("ok"):
        raise RuntimeError(f"o Telegram recusou o arquivo: {str(r.get('description', ''))[:160]}")
    return r["result"]["message_id"]


async def deliver(text: str, origin: str = "") -> bool:
    """Resposta final de uma rotina, de uma ação automática ou de um pedido feito pelo Telegram."""
    if not ready() or not (text or "").strip():
        return False
    prefix = "💡 " if origin == "proativo" else ""
    return bool(await asyncio.to_thread(send_text, prefix + text))


async def notify(ev: dict) -> bool:
    """Espelha no Telegram o que vira notificação no celular. Devolve True se entregou."""
    if not ready():
        return False
    kind = ev.get("type")
    if kind == "reminder":
        rid = ev.get("id")
        buttons = [[{"text": "Adiar 10 min", "callback_data": f"rs:{rid}:10"},
                    {"text": "Adiar 1 h", "callback_data": f"rs:{rid}:60"}]]
        return bool(await asyncio.to_thread(send_text, f"⏰ **Lembrete:** {ev.get('motivo', '')}", buttons))
    if kind == "approval":
        aid = ev.get("id", "")
        buttons = [[{"text": "✅ Aprovar", "callback_data": f"ap:{aid}:1"},
                    {"text": "❌ Negar", "callback_data": f"ap:{aid}:0"}]]
        mid = await asyncio.to_thread(send_text, f"🔐 **O SIMBA precisa da sua aprovação**\n\n{ev.get('prompt', '')}", buttons)
        if mid:
            _approval_msgs[aid] = (chat_id(), mid)
        return bool(mid)
    if kind == "approval_closed":                 # resolvida (no app ou aqui): tira os botões
        ref = _approval_msgs.pop(ev.get("id", ""), None)
        if ref:
            await asyncio.to_thread(_call, "editMessageReplyMarkup",
                                    {"chat_id": ref[0], "message_id": ref[1], "reply_markup": {"inline_keyboard": []}})
        return False
    if kind == "suggestion":
        if ev.get("auto"):                        # modo automático: o resultado chega depois, já feito
            return False
        sid = ev.get("id", "")
        buttons = [[{"text": "Fazer", "callback_data": f"sg:{sid}:1"},
                    {"text": "Ignorar", "callback_data": f"sg:{sid}:0"}]]
        return bool(await asyncio.to_thread(send_text, f"💡 **{ev.get('titulo') or 'Sugestão'}**\n{ev.get('motivo', '')}", buttons))
    return False


# ---------- vínculo ----------
def _new_code(chat: int, nome: str) -> str:
    code = f"{secrets.randbelow(10 ** 6):06d}"
    d = _load()
    d["pendente"] = {"codigo": code, "chat_id": chat, "nome": nome, "expira": time.time() + CODE_TTL}
    _save(d)
    return code


def confirm(code: str) -> str:
    d = _load()
    p = d.get("pendente") or {}
    digits = re.sub(r"\D", "", code or "")
    if not p or time.time() > p.get("expira", 0):
        raise ValueError("não há código válido. Peça ao Bruno para abrir o bot no Telegram e tocar em Iniciar "
                         "(ou mandar /start) para gerar um código novo.")
    if not hmac.compare_digest(digits, p["codigo"]):
        raise ValueError("o código não confere. Peça para ele conferir os 6 dígitos que o bot mandou.")
    d.pop("pendente", None)
    d.update(chat_id=p["chat_id"], nome=p.get("nome", ""), ligado_em=time.strftime("%Y-%m-%d %H:%M"))
    _save(d)
    send_text("✅ **Pronto!** Este chat agora é do seu SIMBA. Por aqui chegam lembretes, aprovações, o briefing "
              "e os documentos que você pedir, e você pode me pedir coisas por aqui também.", chat=p["chat_id"])
    return "Telegram conectado. Ele vai receber uma mensagem de confirmação lá."


# ---------- webhook: mensagens e botões que chegam do Telegram ----------
def webhook_secret() -> str:
    return hmac.new(TOKEN.encode(), b"simba-telegram-webhook", hashlib.sha256).hexdigest()[:48]


def valid_secret(header: str) -> bool:
    return enabled() and hmac.compare_digest(header or "", webhook_secret())


async def setup_webhook():
    """Na nuvem (endereço https), diz ao Telegram para onde mandar as mensagens."""
    base = public_url()
    if not enabled() or not base.startswith("https://"):
        return
    r = await asyncio.to_thread(_call, "setWebhook", {"url": base + "/telegram/webhook", "secret_token": webhook_secret(),
                                                      "allowed_updates": ["message", "callback_query"]})
    print("[telegram] webhook " + ("ativo" if r.get("ok") else f"falhou: {str(r.get('description', ''))[:160]}"))


async def _say(text: str, chat: int, buttons: list | None = None):
    await asyncio.to_thread(send_text, text, buttons, chat)


async def _download(m: dict, chat: int) -> str | None:
    """Foto ou arquivo mandado ao bot -> workspace/.inbox. Devolve o caminho."""
    if m.get("document"):
        f, name = m["document"], m["document"].get("file_name") or "arquivo"
    elif m.get("photo"):
        f, name = m["photo"][-1], "foto.jpg"          # a última é a de maior resolução
    else:
        return None
    if (f.get("file_size") or 0) > MAX_DOWNLOAD:
        await _say("Esse arquivo passa de 20 MB, o limite que o Telegram deixa o bot baixar.", chat)
        return None
    r = await asyncio.to_thread(_call, "getFile", {"file_id": f.get("file_id")})
    fp = (r.get("result") or {}).get("file_path")
    if not fp:
        await _say("Não consegui baixar o arquivo. Tente de novo.", chat)
        return None
    data = await asyncio.to_thread(_fetch_file, fp)
    inbox = WORKSPACE / ".inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    clean = re.sub(r"[^\w.-]+", "_", name)[-80:]
    path = inbox / f"telegram_{int(time.time())}_{clean}"
    path.write_bytes(data)
    return str(path)


async def _typing(task: asyncio.Task, chat: int):
    """Mostra "digitando..." enquanto o SIMBA trabalha (até 4 minutos)."""
    for _ in range(50):
        if task.done():
            return
        await asyncio.to_thread(_call, "sendChatAction", {"chat_id": chat, "action": "typing"})
        await asyncio.sleep(4.5)


async def _on_button(q: dict):
    msg = q.get("message") or {}
    chat = (msg.get("chat") or {}).get("id")
    answer = "Ok"
    if not chat or chat != chat_id():
        await asyncio.to_thread(_call, "answerCallbackQuery", {"callback_query_id": q.get("id"), "text": "Sem permissão."})
        return
    kind, _, rest = str(q.get("data", "")).partition(":")
    ident, _, val = rest.partition(":")
    hub, run = _ctx.get("hub"), _ctx.get("run")
    if kind == "ap" and hub:
        if ident in hub.pending:
            hub.resolve(ident, val == "1")
            answer = "Aprovado" if val == "1" else "Negado"
            await _say("✅ Aprovado." if val == "1" else "❌ Negado.", chat)
        else:
            answer = "Essa aprovação já foi resolvida."
    elif kind == "rs" and ident.isdigit():
        minutes = int(val) if val.isdigit() else 10
        await asyncio.to_thread(life.snooze, int(ident), minutes)
        answer = f"Adiado {minutes} min"
    elif kind == "sg" and hub:
        s = hub.suggestions.pop(ident, None)
        if s and val == "1" and run:
            asyncio.create_task(run(f"[pelo Telegram] {s['acao']}", "telegram"))
            answer = "Fazendo..."
        else:
            answer = "Ok" if s else "Isso já foi resolvido."
    if msg.get("message_id"):
        await asyncio.to_thread(_call, "editMessageReplyMarkup",
                                {"chat_id": chat, "message_id": msg["message_id"], "reply_markup": {"inline_keyboard": []}})
    await asyncio.to_thread(_call, "answerCallbackQuery", {"callback_query_id": q.get("id"), "text": answer})


async def handle_update(u: dict):
    try:
        if "callback_query" in u:
            return await _on_button(u["callback_query"])
        m = u.get("message") or {}
        chat_info = m.get("chat") or {}
        chat = chat_info.get("id")
        if not chat or chat_info.get("type") != "private":
            return
        text = (m.get("text") or m.get("caption") or "").strip()
        bound = chat_id()
        if text.startswith("/start"):
            if bound == chat:
                return await _say("Já estamos conectados. É só me mandar o que precisar.", chat)
            if bound:
                return await _say("Este assistente é particular.", chat)
            nome = (m.get("from") or {}).get("first_name", "")
            code = _new_code(chat, nome)
            return await _say(f"Olá{', ' + nome if nome else ''}! Para ligar este chat ao seu SIMBA, diga a ele no app:\n\n"
                              f"**o código do Telegram é {code}**\n\nO código vale 15 minutos.", chat)
        if chat != bound:
            return                                   # só o dono conversa com o SIMBA
        run = _ctx.get("run")
        if not run:
            return
        if m.get("voice") or m.get("audio") or m.get("video_note"):
            return await _say("Ainda não entendo áudio por aqui. Dite pelo microfone do teclado que chega como texto.", chat)
        path = await _download(m, chat)
        if path:
            text = (f"O Bruno mandou pelo Telegram o arquivo {path}. Leia com Read. "
                    + (f"Pedido dele: {text}" if text else "Entenda do que se trata e diga o que você faria."))
        if not text:
            return
        task = asyncio.create_task(run(f"[pelo Telegram] {text}", "telegram"))
        asyncio.create_task(_typing(task, chat))
    except Exception as e:
        print(f"[telegram] erro ao tratar mensagem: {type(e).__name__}: {e}"[:200])


# ---------- ferramentas dos agentes ----------
def _need(bound: bool = True):
    if not enabled():
        raise RuntimeError("o Telegram não está configurado: falta a variável TELEGRAM_BOT_TOKEN no Railway.")
    if bound and not chat_id():
        raise RuntimeError("o Telegram ainda não está conectado. O Bruno precisa abrir o bot no Telegram, tocar em "
                           "Iniciar e dizer aqui o código de 6 dígitos (use telegram_confirmar).")


@tool("telegram_enviar",
      "Manda ao Bruno no Telegram uma mensagem e, se quiser, um arquivo do workspace (CV, carta, lista de vagas, "
      "planejamento, planilha, relatório). Use para tudo que ele deve receber fora do app. O chat é dele: não pede aprovação.",
      schema({"texto": ("string", "mensagem em markdown simples (ou a legenda do arquivo)")},
             {"arquivo": ("string", "caminho do arquivo no workspace, opcional")}))
@safe
def telegram_enviar(a):
    _need()
    if a.get("arquivo"):
        send_file(a["arquivo"], a.get("texto", ""))
        return "Arquivo enviado no Telegram."
    if not send_text(a.get("texto", "")):
        raise RuntimeError("a mensagem não foi enviada (texto vazio ou o Telegram recusou)")
    return "Mensagem enviada no Telegram."


@tool("telegram_confirmar",
      "Conecta o Telegram do Bruno com o código de 6 dígitos que o bot mostrou quando ele tocou em Iniciar.",
      schema({"codigo": ("string", "os 6 dígitos")}))
@safe
def telegram_confirmar(a):
    _need(bound=False)
    return confirm(a["codigo"])


@tool("telegram_status", "Diz se o Telegram está configurado e conectado.", schema({}))
@safe
def telegram_status(a):
    if not enabled():
        return "Telegram não configurado (falta TELEGRAM_BOT_TOKEN no Railway)."
    if not chat_id():
        return "Telegram configurado, mas ainda não conectado: abrir o bot, tocar em Iniciar e dizer o código."
    d = _load()
    return f"Telegram conectado{' (' + d['nome'] + ')' if d.get('nome') else ''}{', desde ' + d['ligado_em'] if d.get('ligado_em') else ''}."


@tool("telegram_desconectar", "Desliga o chat do Telegram do SIMBA (por exemplo, para ligar outro).", schema({}))
@safe
def telegram_desconectar(a):
    d = _load()
    old = d.pop("chat_id", None)
    d.pop("pendente", None)
    _save(d)
    if old:
        send_text("Este chat foi desligado do SIMBA.", chat=int(old))
    return "Telegram desconectado." + (" (TELEGRAM_CHAT_ID no Railway continua valendo.)" if os.getenv("TELEGRAM_CHAT_ID") else "")


TOOLS = [telegram_enviar, telegram_confirmar, telegram_status, telegram_desconectar]
telegram_server = create_sdk_mcp_server(name="telegram", version="1.0.0", tools=TOOLS)
NAMES = [f"mcp__telegram__{t.name}" for t in TOOLS]
