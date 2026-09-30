"""Gmail, Google Agenda e Drive para as duas contas (pessoal e profissional).
Conectar: botão "Conectar" no app (nuvem), ou no terminal: python -m simba.google auth pessoal"""
import base64, os, re, sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from html import unescape
from claude_agent_sdk import tool, create_sdk_mcp_server
from .config import DATA, WORKSPACE, ACCOUNTS, TZ, ROOT, now
from .toolkit import schema, safe

GDIR = DATA / "google"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify",
          "https://www.googleapis.com/auth/calendar",
          "https://www.googleapis.com/auth/drive.readonly"]
CONTA = ("string", "'pessoal' (brunolubambo@) ou 'profissional' (brunolubamboadm@: vagas, recrutadores)")


def authorized() -> list[str]:
    return [c for c in ACCOUNTS if (GDIR / f"{c}.json").exists()]


def _creds(conta: str):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    if conta not in ACCOUNTS:
        raise ValueError(f"conta deve ser {list(ACCOUNTS)}")
    f = GDIR / f"{conta}.json"
    if not f.exists():
        raise RuntimeError(f"Conta '{conta}' não autorizada. Rode: python -m simba.google auth {conta}")
    c = Credentials.from_authorized_user_file(str(f), SCOPES)
    if not c.valid and c.refresh_token:
        c.refresh(Request())
        f.write_text(c.to_json())
    return c


def _svc(conta: str, name: str, ver: str):
    from googleapiclient.discovery import build
    return build(name, ver, credentials=_creds(conta), cache_discovery=False)


# ---------- Gmail ----------
def _b64d(s: str) -> str:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "replace")


def body_text(payload: dict) -> str:
    """Prefere text/plain; cai para text/html sem tags."""
    def walk(p, mime):
        if p.get("mimeType") == mime and p.get("body", {}).get("data"):
            return _b64d(p["body"]["data"])
        for part in p.get("parts") or []:
            t = walk(part, mime)
            if t:
                return t
        return ""
    t = walk(payload, "text/plain")
    if not t:
        html = walk(payload, "text/html")
        html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
        t = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", t).strip()


def _headers(msg: dict) -> dict:
    return {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}


def list_messages(conta: str, query: str, limit: int = 10) -> list[dict]:
    g = _svc(conta, "gmail", "v1")
    res = g.users().messages().list(userId="me", q=query, maxResults=limit).execute()
    out = []
    for m in res.get("messages", []):
        d = g.users().messages().get(userId="me", id=m["id"], format="metadata",
                                     metadataHeaders=["From", "Subject", "Date"]).execute()
        h = _headers(d)
        out.append({"id": m["id"], "de": h.get("From", ""), "assunto": h.get("Subject", ""),
                    "data": h.get("Date", ""), "trecho": d.get("snippet", "")})
    return out


def _compose(conta, para, assunto, corpo, responder_a=""):
    g = _svc(conta, "gmail", "v1")
    msg = EmailMessage()
    msg["To"], msg["From"] = para, ACCOUNTS[conta]
    msg.set_content(corpo)
    body = {}
    if responder_a:
        orig = g.users().messages().get(userId="me", id=responder_a, format="metadata",
                                        metadataHeaders=["Message-ID", "Subject", "From"]).execute()
        h = _headers(orig)
        subj = h.get("Subject", "")
        assunto = assunto or (subj if subj.lower().startswith("re:") else f"Re: {subj}")
        if h.get("Message-ID"):
            msg["In-Reply-To"] = msg["References"] = h["Message-ID"]
        body["threadId"] = orig["threadId"]
        if not para:
            msg.replace_header("To", h.get("From", ""))
    msg["Subject"] = assunto
    body["raw"] = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return g, body


@tool("gmail_buscar", "Busca e-mails (sintaxe do Gmail: is:unread, from:, newer_than:2d, subject:...).",
      schema({"conta": CONTA, "consulta": ("string", "consulta do Gmail")},
             {"limite": ("integer", "máx. resultados, padrão 10")}))
@safe
def gmail_buscar(a):
    msgs = list_messages(a["conta"], a["consulta"], int(a.get("limite", 10)))
    return "\n".join(f"[{m['id']}] {m['data']} | {m['de']} | {m['assunto']}\n   {m['trecho']}" for m in msgs) or "Nenhum e-mail."


@tool("gmail_ler", "Lê um e-mail completo pelo id.", schema({"conta": CONTA, "id": ("string", "id do e-mail")}))
@safe
def gmail_ler(a):
    g = _svc(a["conta"], "gmail", "v1")
    m = g.users().messages().get(userId="me", id=a["id"], format="full").execute()
    h = _headers(m)
    anexos = [p.get("filename") for p in m["payload"].get("parts") or [] if p.get("filename")]
    return (f"De: {h.get('From')}\nPara: {h.get('To')}\nData: {h.get('Date')}\nAssunto: {h.get('Subject')}\n"
            f"Anexos: {anexos or 'nenhum'}\n\n{body_text(m['payload'])[:12000]}")


@tool("gmail_rascunho", "Cria um RASCUNHO no Gmail (não envia). Para responder, passe responder_a com o id do e-mail.",
      schema({"conta": CONTA, "corpo": ("string", "texto do e-mail")},
             {"para": ("string", "destinatário (opcional se responder_a)"), "assunto": ("string", "assunto"),
              "responder_a": ("string", "id do e-mail a responder")}))
@safe
def gmail_rascunho(a):
    g, body = _compose(a["conta"], a.get("para", ""), a.get("assunto", ""), a["corpo"], a.get("responder_a", ""))
    d = g.users().drafts().create(userId="me", body={"message": body}).execute()
    return f"Rascunho criado na conta {a['conta']} (id {d['id']}). Aparece em Rascunhos no Gmail."


@tool("gmail_enviar", "ENVIA um e-mail (sempre pede aprovação do usuário).",
      schema({"conta": CONTA, "corpo": ("string", "texto do e-mail")},
             {"para": ("string", "destinatário"), "assunto": ("string", "assunto"),
              "responder_a": ("string", "id do e-mail a responder")}))
@safe
def gmail_enviar(a):
    g, body = _compose(a["conta"], a.get("para", ""), a.get("assunto", ""), a["corpo"], a.get("responder_a", ""))
    s = g.users().messages().send(userId="me", body=body).execute()
    return f"Enviado pela conta {a['conta']} (id {s['id']})."


@tool("gmail_marcar_lido", "Marca e-mails como lidos.", schema({"conta": CONTA, "ids": ("string", "ids separados por vírgula")}))
@safe
def gmail_marcar_lido(a):
    g = _svc(a["conta"], "gmail", "v1")
    ids = [i.strip() for i in a["ids"].split(",") if i.strip()]
    g.users().messages().batchModify(userId="me", body={"ids": ids, "removeLabelIds": ["UNREAD"]}).execute()
    return f"{len(ids)} marcado(s) como lido(s)."


# ---------- Agenda ----------
def list_events(conta: str, start: datetime, end: datetime) -> list[dict]:
    c = _svc(conta, "calendar", "v3")
    res = c.events().list(calendarId="primary", timeMin=start.isoformat() + _offset(), timeMax=end.isoformat() + _offset(),
                          singleEvents=True, orderBy="startTime", timeZone=TZ, maxResults=50).execute()
    out = []
    for e in res.get("items", []):
        s = e["start"].get("dateTime", e["start"].get("date"))
        f = e["end"].get("dateTime", e["end"].get("date"))
        out.append({"id": e["id"], "titulo": e.get("summary", "(sem título)"), "inicio": s, "fim": f,
                    "local": e.get("location", ""), "link": e.get("hangoutLink", ""), "descricao": e.get("description", "")})
    return out


def _offset() -> str:
    from zoneinfo import ZoneInfo
    off = datetime.now(ZoneInfo(TZ)).strftime("%z")
    return off[:3] + ":" + off[3:]


@tool("agenda_listar", "Lista compromissos da agenda.",
      schema({"conta": CONTA}, {"dias": ("integer", "quantos dias à frente, padrão 7"),
                                "a_partir": ("string", "data inicial AAAA-MM-DD, padrão hoje")}))
@safe
def agenda_listar(a):
    start = datetime.fromisoformat(a["a_partir"]) if a.get("a_partir") else now().replace(hour=0, minute=0, second=0)
    evs = list_events(a["conta"], start, start + timedelta(days=int(a.get("dias", 7))))
    return "\n".join(f"[{e['id']}] {e['inicio']} → {e['fim']} | {e['titulo']}" + (f" | {e['local']}" if e["local"] else "")
                     for e in evs) or "Agenda livre no período."


@tool("agenda_criar", "Cria compromisso. Horários locais AAAA-MM-DDTHH:MM. Com convidados, pede aprovação.",
      schema({"conta": CONTA, "titulo": ("string", "título"), "inicio": ("string", "AAAA-MM-DDTHH:MM"),
              "fim": ("string", "AAAA-MM-DDTHH:MM")},
             {"descricao": ("string", "descrição"), "local": ("string", "local"),
              "convidados": ("string", "e-mails separados por vírgula"),
              "recorrencia": ("string", "RRULE, ex.: RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"),
              "lembrete_min": ("integer", "aviso X minutos antes")}))
@safe
def agenda_criar(a):
    c = _svc(a["conta"], "calendar", "v3")
    ev = {"summary": a["titulo"], "description": a.get("descricao", ""), "location": a.get("local", ""),
          "start": {"dateTime": a["inicio"] + ":00" if len(a["inicio"]) == 16 else a["inicio"], "timeZone": TZ},
          "end": {"dateTime": a["fim"] + ":00" if len(a["fim"]) == 16 else a["fim"], "timeZone": TZ}}
    if a.get("convidados"):
        ev["attendees"] = [{"email": e.strip()} for e in a["convidados"].split(",") if e.strip()]
    if a.get("recorrencia"):
        ev["recurrence"] = [a["recorrencia"]]
    if a.get("lembrete_min"):
        ev["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": int(a["lembrete_min"])}]}
    r = c.events().insert(calendarId="primary", body=ev, sendUpdates="all" if a.get("convidados") else "none").execute()
    return f"Criado na agenda {a['conta']}: {a['titulo']} ({r['id']}) {r.get('htmlLink', '')}"


@tool("agenda_remover", "Remove um compromisso (pede aprovação).", schema({"conta": CONTA, "id": ("string", "id do evento")}))
@safe
def agenda_remover(a):
    _svc(a["conta"], "calendar", "v3").events().delete(calendarId="primary", eventId=a["id"]).execute()
    return "Removido."


# ---------- Drive ----------
@tool("drive_buscar", "Busca arquivos no Google Drive por texto no nome ou conteúdo.",
      schema({"conta": CONTA, "texto": ("string", "o que procurar")}))
@safe
def drive_buscar(a):
    t = a["texto"].replace("\\", "").replace("'", "\\'")
    r = _svc(a["conta"], "drive", "v3").files().list(
        q=f"(name contains '{t}' or fullText contains '{t}') and trashed=false", pageSize=15,
        fields="files(id,name,mimeType,modifiedTime,webViewLink)").execute()
    return "\n".join(f"[{f['id']}] {f['name']} | {f['mimeType'].split('.')[-1]} | {f['modifiedTime'][:10]} | {f['webViewLink']}"
                     for f in r.get("files", [])) or "Nada encontrado."


@tool("drive_ler", "Lê um arquivo do Drive. Docs/Planilhas viram texto; outros (PDF etc.) são baixados para o workspace.",
      schema({"conta": CONTA, "id": ("string", "id do arquivo")}))
@safe
def drive_ler(a):
    d = _svc(a["conta"], "drive", "v3")
    meta = d.files().get(fileId=a["id"], fields="name,mimeType").execute()
    exports = {"application/vnd.google-apps.document": "text/plain",
               "application/vnd.google-apps.spreadsheet": "text/csv",
               "application/vnd.google-apps.presentation": "text/plain"}
    if meta["mimeType"] in exports:
        data = d.files().export(fileId=a["id"], mimeType=exports[meta["mimeType"]]).execute()
        return f"# {meta['name']}\n\n{data.decode('utf-8', 'replace')[:15000]}"
    out = WORKSPACE / "drive"
    out.mkdir(exist_ok=True)
    path = out / re.sub(r"[^\w.\- ]", "_", meta["name"])
    path.write_bytes(d.files().get_media(fileId=a["id"]).execute())
    return f"Baixado em {path}. Leia com a ferramenta Read."


TOOLS = [gmail_buscar, gmail_ler, gmail_rascunho, gmail_enviar, gmail_marcar_lido,
         agenda_listar, agenda_criar, agenda_remover, drive_buscar, drive_ler]
google_server = create_sdk_mcp_server(name="google", version="1.0.0", tools=TOOLS)
NAMES = [f"mcp__google__{t.name}" for t in TOOLS]


# ---------- autorização pelo app (nuvem) ----------
_FLOWS: dict = {}


def client_config() -> dict:
    cid, sec = os.getenv("GOOGLE_CLIENT_ID"), os.getenv("GOOGLE_CLIENT_SECRET")
    if cid and sec:
        return {"web": {"client_id": cid, "client_secret": sec,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"}}
    f = GDIR / "credentials.json"
    if f.exists():
        import json
        return json.loads(f.read_text())
    raise RuntimeError("Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET (veja o README).")


def start_web_auth(conta: str, redirect_uri: str) -> str:
    from google_auth_oauthlib.flow import Flow
    if conta not in ACCOUNTS:
        raise ValueError("conta inválida")
    flow = Flow.from_client_config(client_config(), SCOPES, redirect_uri=redirect_uri)
    url, state = flow.authorization_url(access_type="offline", prompt="consent select_account",
                                        login_hint=ACCOUNTS[conta])
    _FLOWS[state] = (conta, flow)
    return url


def finish_web_auth(state: str, code: str) -> tuple[str, str]:
    if state not in _FLOWS:
        raise RuntimeError("Sessão de login expirada. Tente conectar de novo.")
    conta, flow = _FLOWS.pop(state)
    flow.fetch_token(code=code)
    f = GDIR / f"{conta}.json"
    f.write_text(flow.credentials.to_json())
    email = _svc(conta, "gmail", "v1").users().getProfile(userId="me").execute()["emailAddress"]
    if email.lower() != ACCOUNTS[conta].lower():
        f.unlink()
        raise RuntimeError(f"Você entrou com {email}, mas a conta {conta} é {ACCOUNTS[conta]}.")
    return conta, email


# ---------- autorização (terminal, uso local) ----------
def auth(conta: str):
    from google_auth_oauthlib.flow import InstalledAppFlow
    secret = next((p for p in (GDIR / "credentials.json", ROOT / "credentials.json") if p.exists()), None)
    if not secret:
        sys.exit("Coloque o credentials.json (OAuth, tipo 'App para computador') em data/google/. Veja o README.")
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0, login_hint=ACCOUNTS[conta], prompt="consent")
    (GDIR / f"{conta}.json").write_text(creds.to_json())
    email = _svc(conta, "gmail", "v1").users().getProfile(userId="me").execute()["emailAddress"]
    if email.lower() != ACCOUNTS[conta].lower():
        (GDIR / f"{conta}.json").unlink()
        sys.exit(f"Você entrou com {email}, mas a conta '{conta}' é {ACCOUNTS[conta]}. Rode de novo com a conta certa.")
    print(f"OK: conta '{conta}' autorizada ({email}).")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "auth" and sys.argv[2] in ACCOUNTS:
        auth(sys.argv[2])
    else:
        print("uso: python -m simba.google auth pessoal|profissional")
