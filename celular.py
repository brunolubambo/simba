"""Controle do celular Android (Galaxy A33 5G, One UI 8) pelo Tasker.

O SIMBA manda um push pelo Firebase Cloud Messaging; o Tasker executa e DEVOLVE o resultado
em POST /celular/resultado (ou a foto em POST /celular/foto). Enquanto essa confirmação não
chega, a ferramenta não diz que executou.

Variáveis (Railway → Variables):
  FCM_PROJECT_ID        id do projeto no Google Cloud (obrigatório)
  FCM_SERVICE_ACCOUNT   JSON da conta de serviço, ou o caminho de um arquivo no volume (obrigatório)
  CELULAR_FCM_TOKEN     token do aparelho, em Tasker → Preferências → MISC (obrigatório)
  CELULAR_TOKEN         token que o Tasker manda de volta (se vazio, usa SIMBA_TOKEN)
  CELULAR_TASK          nome da tarefa no Tasker (padrão: SimbaComando)
  CELULAR_TIMEOUT_S     segundos de espera pela confirmação (padrão: 20)

Sem as três primeiras a ferramenta não é registrada. Guia: celular-tasker.md."""
import asyncio, json, os, re, secrets, ssl, urllib.error, urllib.request
from pathlib import Path
from claude_agent_sdk import tool, create_sdk_mcp_server
from .toolkit import schema, ok, err

PROJECT = os.getenv("FCM_PROJECT_ID", "").strip()
CREDENTIAL = os.getenv("FCM_SERVICE_ACCOUNT", "").strip()
DEVICE = os.getenv("CELULAR_FCM_TOKEN", "").strip()
TASK = os.getenv("CELULAR_TASK", "SimbaComando").strip() or "SimbaComando"
WAIT = float(os.getenv("CELULAR_TIMEOUT_S", "20"))
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM = "https://fcm.googleapis.com/v1/projects/{}/messages:send"
HORA = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
FOTO_MAX = 8 * 1024 * 1024

# Lista fechada. Cada ação diz quais argumentos aceita; o resto é descartado.
ACOES: dict[str, tuple[str, ...]] = {
    "alarme": ("hora", "etiqueta"),
    "abrir_app": ("app",),
    "foto": ("camera",),
}
LIVRES = {"alarme", "abrir_app"}
_pending: dict[str, asyncio.Future] = {}
_creds = None
_sa = None


def _project_id() -> str:
    if PROJECT:
        return PROJECT
    if not CREDENTIAL:
        return ""
    try:
        return str(_service_account().get("project_id") or "")
    except Exception:
        return ""


def enabled() -> bool:
    return bool(CREDENTIAL and DEVICE and _project_id())


def verdade(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("true", "1", "ok", "sim")


def token_ok(token: str) -> bool:
    """O retorno do Tasker usa CELULAR_TOKEN, ou o SIMBA_TOKEN se aquele estiver vazio."""
    expected = os.getenv("CELULAR_TOKEN", "").strip() or os.getenv("SIMBA_TOKEN", "").strip()
    return bool(expected) and bool(token) and secrets.compare_digest(token, expected)


def resumo(a: dict) -> str:
    acao = a.get("acao", "")
    if acao == "foto":
        return f"tirar uma foto com a câmera {a.get('camera') or 'traseira'} e enviar ao SIMBA"
    if acao == "alarme":
        return f"criar alarme às {a.get('hora')}" + (f" ({a.get('etiqueta')})" if a.get("etiqueta") else "")
    if acao == "abrir_app":
        return f"abrir o app {a.get('app')}"
    return f"executar {acao}"


def _prepara(a: dict) -> dict:
    """Valida e devolve só campos permitidos, todos string (exigência do FCM)."""
    acao = str(a.get("acao", "")).strip()
    if acao not in ACOES:
        raise ValueError(f"ação '{acao}' não existe; use uma de: {', '.join(ACOES)}")
    dados = {"acao": acao}
    for campo in ACOES[acao]:
        valor = str(a.get(campo, "")).strip()
        if valor:
            dados[campo] = valor[:200]
    if acao == "alarme":
        if not HORA.match(dados.get("hora", "")):
            raise ValueError("informe a hora do alarme como HH:MM, ex. 07:30")
    if acao == "abrir_app" and "app" not in dados:
        raise ValueError("informe o nome do app como ele aparece no celular")
    if acao == "foto":
        camera = dados.get("camera", "traseira")
        if camera not in ("frontal", "traseira"):
            raise ValueError("camera deve ser 'frontal' ou 'traseira'")
        dados["camera"] = camera
    return dados


def _ssl():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _service_account() -> dict:
    global _sa
    if _sa is not None:
        return _sa
    try:
        if CREDENTIAL.lstrip().startswith("{"):
            _sa = json.loads(CREDENTIAL)
        else:
            _sa = json.loads(Path(CREDENTIAL).read_text(encoding="utf-8"))
        if not isinstance(_sa, dict):
            raise ValueError("json")
        return _sa
    except Exception:
        _sa = None
        raise RuntimeError("a conta de serviço do Firebase está inválida") from None


def _access_token() -> str:
    global _creds
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    if _creds is None:
        _creds = service_account.Credentials.from_service_account_info(_service_account(), scopes=[SCOPE])
    if not _creds.valid:
        _creds.refresh(Request())
    return _creds.token


def _push(dados: dict):
    corpo = {"message": {"token": DEVICE, "android": {"priority": "HIGH"},
                         "data": {"task": TASK, **{k: str(v) for k, v in dados.items()}}}}
    req = urllib.request.Request(
        FCM.format(_project_id()), data=json.dumps(corpo, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_access_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_ssl()) as r:
            r.read()
    except urllib.error.HTTPError as e:
        detalhe = ""
        try:
            detalhe = json.loads(e.read().decode()).get("error", {}).get("status", "")
        except Exception:
            pass
        if e.code in (400, 404) or detalhe == "UNREGISTERED":
            raise RuntimeError("o Firebase não reconhece mais este aparelho; o token do Tasker precisa ser atualizado")
        raise RuntimeError(f"o Firebase recusou o envio (HTTP {e.code})")
    except Exception as e:
        raise RuntimeError(f"não consegui falar com o Firebase ({type(e).__name__})") from None


def report(cmd: str, sucesso: bool, detalhe: str = "") -> bool:
    """Chamado pelas rotas de retorno. False se o comando já expirou."""
    fut = _pending.pop(cmd, None)
    if fut is None or fut.done():
        return False
    fut.get_loop().call_soon_threadsafe(fut.set_result, (sucesso, detalhe))
    return True


async def executar(a: dict) -> str:
    dados = _prepara(a)
    acao = dados["acao"]
    if not enabled():
        raise RuntimeError("o controle do celular não está configurado (faltam as variáveis do Firebase no Railway)")
    while len(_pending) >= 20:
        _, velho = _pending.popitem()
        velho.cancel()
    cmd = secrets.token_urlsafe(8)
    fut = asyncio.get_running_loop().create_future()
    _pending[cmd] = fut
    try:
        await asyncio.to_thread(_push, {**dados, "cmd": cmd})
        sucesso, detalhe = await asyncio.wait_for(fut, WAIT)
    except asyncio.TimeoutError:
        print(f"[celular] {acao}: sem resposta do aparelho")
        raise RuntimeError(
            "o comando foi enviado mas o celular não confirmou, então NÃO foi executado. "
            "Verifique se o aparelho está ligado e com internet, e se o Tasker não foi suspenso pela bateria") from None
    except asyncio.CancelledError:
        raise
    except RuntimeError:
        raise
    except Exception as e:
        print(f"[celular] {acao}: falha ao enviar")
        raise RuntimeError(f"não consegui enviar o comando ao celular ({type(e).__name__})") from None
    finally:
        _pending.pop(cmd, None)
    print(f"[celular] {acao}: {'ok' if sucesso else 'erro'}")
    if not sucesso:
        raise RuntimeError(f"o celular recebeu o comando e não conseguiu executar: {detalhe or 'o Tasker não disse o motivo'}")
    extra = f" {detalhe}" if detalhe else ""
    if acao == "foto" and detalhe:
        extra = f" Imagem em {detalhe}. Leia com Read."
    return f"Feito no celular: {resumo(a)}.{extra}"


@tool("celular_acao",
      "Executa uma ação no celular Android do Bruno pelo Tasker. Ações: 'alarme' (hora HH:MM, etiqueta opcional), "
      "'abrir_app' (app: o nome como aparece no celular) e 'foto' (camera frontal ou traseira; a imagem chega no "
      "workspace para você ler com Read). Só responde sucesso quando o próprio celular confirma; se devolver erro, "
      "a ação NÃO aconteceu e você não deve dizer que aconteceu. Compromissos: use agenda_criar, que já aparece no "
      "celular pela conta Google.",
      schema({"acao": ("string", "alarme | abrir_app | foto")},
             {"hora": ("string", "alarme: HH:MM"), "etiqueta": ("string", "alarme: nome do alarme"),
              "app": ("string", "abrir_app: nome do app"), "camera": ("string", "foto: frontal ou traseira")}))
async def celular_acao(a):
    try:
        return ok(await executar(a))
    except Exception as e:
        return err(str(e) if isinstance(e, (RuntimeError, ValueError)) else f"{type(e).__name__}: {e}")


celular_server = create_sdk_mcp_server(name="celular", version="1.0.0", tools=[celular_acao])
