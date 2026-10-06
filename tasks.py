"""Tarefas de fundo do servidor: lembretes, rotinas agendadas e vigias (e-mail e agenda).

Rotinas ficam em DATA/routines.json (SIMBA_DATA; na nuvem, /data). O laço relê o arquivo
sozinho, então criar, editar ou pausar vale em até um minuto, sem reiniciar o servidor.
"""
import asyncio, json, re, threading, unicodedata
from datetime import timedelta
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock, tool, create_sdk_mcp_server
from .config import DATA, PROMPTS, FAST_MODEL, DIAS, now
from .toolkit import schema, safe
from . import life, google, telegram

ROUTINES = DATA / "routines.json"
SEEN = DATA / "seen_mail.json"
_ERRO_HORA = "Horário inválido. Use HH:MM, entre 00:00 e 23:59."
_ERRO_DIAS = "Dias inválidos. Use segunda a domingo, dias úteis, fim de semana ou todos."
_ERRO_CANAL = "Canal inválido. Use HUD, voz ou Telegram."
_CANAIS = {"hud": "HUD", "voz": "voz", "telegram": "Telegram"}
_DIA = {
    "segunda": 0, "seg": 0, "2a": 0,
    "terca": 1, "ter": 1, "3a": 1,
    "quarta": 2, "qua": 2, "4a": 2,
    "quinta": 3, "qui": 3, "5a": 3,
    "sexta": 4, "sex": 4, "6a": 4,
    "sabado": 5, "sab": 5,
    "domingo": 6, "dom": 6,
}
DEFAULT_ROUTINES = [
    {"id": "briefing", "nome": "briefing", "horario": "07:00", "dias": [0, 1, 2, 3, 4],
     "acao": "Briefing da manhã para ler no celular: agenda de hoje nas duas contas; e-mails não lidos que pedem ação "
             "(separe pessoal e profissional, destaque recrutadores e prazos); lembretes de hoje. Curto.",
     "canal": "Telegram", "ativa": True},
    {"id": "fechamento_semana", "nome": "fechamento_semana", "horario": "18:00", "dias": [4],
     "acao": "Fechamento da semana: resumo de gastos da semana, treinos e estudos registrados, e o que ficou pendente "
             "nos e-mails profissionais. Curto.",
     "canal": "Telegram", "ativa": True},
]
_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_listener = None


def bind(loop: asyncio.AbstractEventLoop, listener) -> None:
    """O servidor registra o laço e um callback async para avisar o HUD quando o arquivo muda."""
    global _loop, _listener
    _loop, _listener = loop, listener


def _emit(itens: list) -> None:
    if not (_loop and _listener):
        return

    def kick(copia=itens):
        asyncio.create_task(_listener(copia))

    try:
        _loop.call_soon_threadsafe(kick)
    except RuntimeError:
        pass


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def _slug(nome: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", _fold(nome)).strip("_")[:40]
    return base or "rotina"


def _nome(v) -> str:
    nome = str(v or "").strip()
    if not nome:
        raise ValueError("Informe um nome para a rotina.")
    if len(nome) > 60:
        raise ValueError("O nome da rotina é longo demais (máximo 60 caracteres).")
    return nome


def _horario(v) -> str:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(v or "").strip())
    if not m:
        raise ValueError(_ERRO_HORA)
    hora, minuto = int(m.group(1)), int(m.group(2))
    if hora > 23 or minuto > 59:
        raise ValueError(_ERRO_HORA)
    return f"{hora:02d}:{minuto:02d}"


def _dias_texto(texto: str) -> list[int]:
    t = _fold(texto)
    if t in ("todos", "todo dia", "todos os dias", "diario", "diariamente"):
        return list(range(7))
    if t in ("uteis", "dias uteis", "dia util", "dias de semana"):
        return [0, 1, 2, 3, 4]
    if t in ("fim de semana", "fins de semana", "fds"):
        return [5, 6]
    faixa = re.fullmatch(r"(.+?) a (.+)", t)
    if faixa and faixa.group(1) in _DIA and faixa.group(2) in _DIA:
        ini, fim = _DIA[faixa.group(1)], _DIA[faixa.group(2)]
        if ini <= fim:
            return list(range(ini, fim + 1))
        raise ValueError(_ERRO_DIAS)
    pedacos = [p.strip() for p in re.split(r"[,;/]| e ", t) if p.strip()]
    if not pedacos:
        raise ValueError(_ERRO_DIAS)
    out = []
    for p in pedacos:
        if p in ("uteis", "dias uteis", "dia util"):
            out.extend([0, 1, 2, 3, 4])
        elif p in ("fim de semana", "fins de semana", "fds"):
            out.extend([5, 6])
        elif p in _DIA:
            out.append(_DIA[p])
        else:
            raise ValueError(_ERRO_DIAS)
    return out


def _dias(v) -> list[int]:
    if v is None or (isinstance(v, str) and not v.strip()):
        return list(range(7))
    partes = list(v) if isinstance(v, (list, tuple)) else [v]
    achados: list[int] = []
    for parte in partes:
        if isinstance(parte, bool) or isinstance(parte, (list, tuple)):
            raise ValueError(_ERRO_DIAS)
        if isinstance(parte, int) or (isinstance(parte, str) and parte.strip().isdigit()):
            n = int(parte)
            if n < 0 or n > 6:
                raise ValueError(_ERRO_DIAS)
            achados.append(n)
        else:
            achados.extend(_dias_texto(str(parte)))
    if not achados:
        raise ValueError(_ERRO_DIAS)
    return sorted(set(achados))


def _acao(v) -> str:
    texto = str(v or "").strip()
    if not texto:
        raise ValueError("Diga o que a rotina deve fazer ou dizer.")
    return texto


def _canal(v) -> str:
    chave = _fold(v or "")
    if chave not in _CANAIS:
        raise ValueError(_ERRO_CANAL)
    return _CANAIS[chave]


def _ativa(v) -> bool:
    if isinstance(v, bool):
        return v
    chave = _fold(v if v is not None else "")
    if chave in ("sim", "ativa", "ativo", "true", "1", "yes"):
        return True
    if chave in ("nao", "pausada", "pausado", "false", "0", "no"):
        return False
    raise ValueError("Estado inválido. Use sim ou não.")


def _fmt_dias(dias: list[int]) -> str:
    if dias == list(range(7)):
        return "todos os dias"
    if dias == [0, 1, 2, 3, 4]:
        return "dias úteis"
    if dias == [5, 6]:
        return "fim de semana"
    return ", ".join(DIAS[d] for d in dias)


def _as_record(raw: dict) -> dict:
    """Aceita o JSON novo ou o antigo (name/time/days/prompt) e devolve o registro atual."""
    if "nome" in raw and "horario" in raw:
        nome = _nome(raw.get("nome"))
        return {
            "id": str(raw.get("id") or _slug(nome)).strip() or _slug(nome),
            "nome": nome, "horario": _horario(raw.get("horario")), "dias": _dias(raw.get("dias")),
            "acao": _acao(raw.get("acao") or raw.get("prompt")),
            "canal": _canal(raw.get("canal") or "Telegram"), "ativa": _ativa(raw.get("ativa", True)),
        }
    nome = _nome(raw.get("name") or raw.get("nome"))
    return {
        "id": _slug(nome), "nome": nome, "horario": _horario(raw.get("time") or raw.get("horario")),
        "dias": _dias(raw.get("days", raw.get("dias"))), "acao": _acao(raw.get("prompt") or raw.get("acao")),
        "canal": "Telegram", "ativa": True,
    }


def _public(r: dict) -> dict:
    return {"id": r["id"], "nome": r["nome"], "horario": r["horario"], "dias": list(r["dias"]),
            "canal": r["canal"], "ativa": bool(r["ativa"])}


def _json_arquivo():
    """Lê o JSON. O arquivo antigo no Windows pode estar em cp1252; UTF-8 inválido não pode zerar as rotinas."""
    data = ROUTINES.read_bytes()
    try:
        texto = data.decode("utf-8")
    except UnicodeDecodeError:
        texto = data.decode("cp1252")
    return json.loads(texto)


def _read_unlocked() -> tuple[list[dict], bool]:
    if not ROUTINES.exists():
        return [dict(r) for r in DEFAULT_ROUTINES], True
    try:
        raw = _json_arquivo()
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return [], False
    if not isinstance(raw, list):
        return [], False
    itens, mudou = [], False
    for row in raw:
        if not isinstance(row, dict):
            mudou = True
            continue
        try:
            rec = _as_record(row)
        except ValueError:
            continue
        itens.append(rec)
        if row != rec:
            mudou = True
    return itens, mudou


def _write_unlocked(items: list[dict]) -> None:
    ROUTINES.parent.mkdir(parents=True, exist_ok=True)
    tmp = ROUTINES.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(ROUTINES)


def load_routines() -> list[dict]:
    with _lock:
        items, changed = _read_unlocked()
        if changed:
            _write_unlocked(items)
            publica = [_public(r) for r in items]
        else:
            publica = None
    if publica is not None:
        _emit(publica)
    return items


def snapshot() -> list[dict]:
    try:
        return [_public(r) for r in load_routines()]
    except Exception:
        return []


def _nome_existe(items: list[dict], nome: str, ignorar: str | None = None) -> bool:
    chave = nome.casefold()
    return any(r["nome"].casefold() == chave and r["id"] != ignorar for r in items)


def _id_livre(items: list[dict], nome: str) -> str:
    base = _slug(nome)
    ids = {r["id"] for r in items}
    if base not in ids:
        return base
    n = 2
    while f"{base}_{n}" in ids:
        n += 1
    return f"{base}_{n}"


def _achar(items: list[dict], ref: str) -> dict:
    chave = str(ref or "").strip()
    if not chave:
        raise ValueError("Diga o nome da rotina.")
    alvo = chave.casefold()
    hits = [r for r in items if r["id"].casefold() == alvo or r["nome"].casefold() == alvo]
    if not hits:
        raise ValueError(f"Não encontrei a rotina '{chave}'.")
    if len(hits) > 1:
        raise ValueError(f"Há mais de uma rotina parecida com '{chave}'. Use o id.")
    return hits[0]


def _resumo(r: dict) -> str:
    estado = "ativa" if r["ativa"] else "pausada"
    return f"{r['horario']}, {_fmt_dias(r['dias'])}, canal {r['canal']}, {estado}"


def listar_texto() -> str:
    rows = load_routines()
    if not rows:
        return "Nenhuma rotina programada."
    return "\n".join(
        f"{r['nome']} (id {r['id']}) · {_resumo(r)}\n  {r['acao']}" for r in rows)


def criar(a: dict) -> str:
    nome = _nome(a.get("nome"))
    horario = _horario(a.get("horario"))
    acao = _acao(a.get("acao"))
    dias = _dias(a.get("dias"))
    canal = _canal(a.get("canal") or "Telegram")
    with _lock:
        items, _changed = _read_unlocked()
        if _nome_existe(items, nome):
            raise ValueError(f"Já existe uma rotina com o nome '{nome}'.")
        items.append({"id": _id_livre(items, nome), "nome": nome, "horario": horario, "dias": dias,
                      "acao": acao, "canal": canal, "ativa": True})
        _write_unlocked(items)
        publica = [_public(r) for r in items]
    _emit(publica)
    return f"Rotina '{nome}' criada: {horario}, {_fmt_dias(dias)}, canal {canal}."


def editar(a: dict) -> str:
    with _lock:
        items, _changed = _read_unlocked()
        rec = _achar(items, a.get("nome") or a.get("id"))
        if a.get("novo_nome"):
            novo = _nome(a.get("novo_nome"))
            if _nome_existe(items, novo, rec["id"]):
                raise ValueError(f"Já existe uma rotina com o nome '{novo}'.")
            rec["nome"] = novo
        if a.get("horario"):
            rec["horario"] = _horario(a.get("horario"))
        if a.get("dias") not in (None, ""):
            rec["dias"] = _dias(a.get("dias"))
        if a.get("acao"):
            rec["acao"] = _acao(a.get("acao"))
        if a.get("canal"):
            rec["canal"] = _canal(a.get("canal"))
        if a.get("ativa") not in (None, ""):
            rec["ativa"] = _ativa(a.get("ativa"))
        _write_unlocked(items)
        publica = [_public(r) for r in items]
        texto = f"Rotina '{rec['nome']}' atualizada: {_resumo(rec)}."
    _emit(publica)
    return texto


def _marcar(ref: str, ativa: bool) -> str:
    with _lock:
        items, _changed = _read_unlocked()
        rec = _achar(items, ref)
        rec["ativa"] = ativa
        _write_unlocked(items)
        publica = [_public(r) for r in items]
        nome = rec["nome"]
    _emit(publica)
    return f"Rotina '{nome}' {'reativada' if ativa else 'pausada'}."


def pausar(a: dict) -> str:
    return _marcar(a.get("nome") or a.get("id"), False)


def reativar(a: dict) -> str:
    return _marcar(a.get("nome") or a.get("id"), True)


def apagar(a: dict) -> str:
    with _lock:
        items, _changed = _read_unlocked()
        rec = _achar(items, a.get("nome") or a.get("id"))
        items = [r for r in items if r["id"] != rec["id"]]
        _write_unlocked(items)
        publica = [_public(r) for r in items]
        nome = rec["nome"]
    _emit(publica)
    return f"Rotina '{nome}' apagada."


@tool("rotina_listar", "Lista as rotinas programadas: horário, dias, canal e se está ativa ou pausada.", schema({}))
@safe
def rotina_listar(a):
    return listar_texto()


@tool("rotina_criar", "Cria uma rotina programada. Ela dispara sozinha no horário, sem editar código nem fazer deploy.",
      schema({"nome": ("string", "nome único, ex.: treino"),
              "horario": ("string", "HH:MM, hora local"),
              "acao": ("string", "o que o SIMBA deve fazer ou dizer quando disparar")},
             {"dias": ("string", "segunda a domingo, dias úteis, fim de semana ou todos. Padrão: todos os dias"),
              "canal": ("string", "HUD, voz ou Telegram. Padrão: Telegram")}))
@safe
def rotina_criar(a):
    return criar(a)


@tool("rotina_editar", "Altera horário, dias, ação, canal ou nome de uma rotina. Vale no próximo minuto, sem reiniciar.",
      schema({"nome": ("string", "nome ou id da rotina")},
             {"novo_nome": ("string", "novo nome"), "horario": ("string", "HH:MM"),
              "dias": ("string", "dias da semana"), "acao": ("string", "o que fazer ou dizer"),
              "canal": ("string", "HUD, voz ou Telegram"), "ativa": ("string", "sim ou não")}))
@safe
def rotina_editar(a):
    return editar(a)


@tool("rotina_pausar", "Pausa uma rotina. Ela deixa de disparar até ser reativada.",
      schema({"nome": ("string", "nome ou id da rotina")}))
@safe
def rotina_pausar(a):
    return pausar(a)


@tool("rotina_reativar", "Volta a disparar uma rotina pausada.",
      schema({"nome": ("string", "nome ou id da rotina")}))
@safe
def rotina_reativar(a):
    return reativar(a)


@tool("rotina_apagar", "Apaga uma rotina de vez. Pede confirmação antes.",
      schema({"nome": ("string", "nome ou id da rotina")}))
@safe
def rotina_apagar(a):
    return apagar(a)


ROTINA_TOOLS = [rotina_listar, rotina_criar, rotina_editar, rotina_pausar, rotina_reativar, rotina_apagar]
routines_server = create_sdk_mcp_server(name="rotinas", version="1.0.0", tools=ROTINA_TOOLS)


async def fast_json(system: str, prompt: str):
    """Chamada barata (Haiku, sem ferramentas) que devolve JSON."""
    opts = ClaudeAgentOptions(system_prompt=system, model=FAST_MODEL, tools=[], max_turns=1)
    out = []
    async for msg in query(prompt=prompt, options=opts):
        if isinstance(msg, AssistantMessage):
            out += [b.text for b in msg.content if isinstance(b, TextBlock)]
    m = re.search(r"(\[.*\]|\{.*\})", "\n".join(out), re.S)
    return json.loads(m.group(1)) if m else None


async def reminders_loop(hub):
    while True:
        try:
            for r in life.due():
                await hub.broadcast({"type": "reminder", "id": r["id"], "titulo": "Lembrete", "motivo": r["texto"]}, push=True)
                life.fired(r["id"])
        except Exception as e:
            await hub.broadcast({"type": "error", "text": f"Lembretes: {e}"})
        await asyncio.sleep(30)


async def routines_loop(run):
    """Relê o JSON a cada 20s. Horário editado ou pausa passam a valer sem reiniciar."""
    done = set()
    while True:
        try:
            n = now()
            marca = n.strftime("%H:%M")
            for r in load_routines():
                if not r.get("ativa", True):
                    continue
                horario = r.get("horario")
                dias = r.get("dias") or []
                if horario != marca or n.weekday() not in dias:
                    continue
                key = (r.get("id"), n.date().isoformat(), horario)
                if key in done:
                    continue
                done.add(key)
                acao = r.get("acao") or ""
                if acao:
                    asyncio.create_task(run(acao, "rotina", r.get("canal") or "Telegram"))
        except Exception:
            pass
        await asyncio.sleep(20)


async def mail_loop(hub, interval_min: int = 10):
    """Vigia os e-mails novos das duas contas e sugere ação quando precisa.
    Na primeira vez que vê uma conta, só aprende o que já existe (não sugere nada antigo)."""
    seen: dict = json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {}
    while True:
        try:
            for conta in google.authorized():
                msgs = await asyncio.to_thread(google.list_messages, conta, "is:unread newer_than:2d category:primary", 15)
                first_time = conta not in seen
                known = set(seen.get(conta, []))
                new = [m for m in msgs if m["id"] not in known]
                seen[conta] = (list(known) + [m["id"] for m in new])[-1000:]
                SEEN.write_text(json.dumps(seen), encoding="utf-8")
                if first_time or not new or (not hub.clients and not hub.has_push() and not telegram.ready()):
                    continue
                lista = "\n".join(f"id={m['id']} | de={m['de']} | assunto={m['assunto']} | {m['trecho']}" for m in new)
                items = await fast_json((PROMPTS / "mail_triage.md").read_text(encoding="utf-8"), f"Conta: {conta}\n{lista}") or []
                for it in items:
                    if float(it.get("confianca", 0)) >= 0.6 and it.get("acao"):
                        await hub.suggest({"titulo": it.get("titulo"), "motivo": f"[{conta}] {it.get('motivo', '')}",
                                           "acao": f"[conta {conta}, e-mail id {it['id']}] {it['acao']}",
                                           "confianca": it.get("confianca")})
        except Exception as e:
            await hub.broadcast({"type": "error", "text": f"Vigia de e-mail: {e}"})
        await asyncio.sleep(interval_min * 60)


async def calendar_loop(hub, ahead_min: int = 20):
    """Avisa antes de cada compromisso e oferece preparar o contexto."""
    warned = set()
    while True:
        try:
            n = now()
            for conta in google.authorized():
                evs = await asyncio.to_thread(google.list_events, conta, n, n + timedelta(minutes=ahead_min))
                for e in evs:
                    if e["id"] in warned or "T" not in e["inicio"]:
                        continue
                    warned.add(e["id"])
                    hora = e["inicio"][11:16]
                    await hub.suggest({"titulo": f"{hora} · {e['titulo']}"[:60],
                                       "motivo": f"Começa em breve (agenda {conta})." + (f" Link: {e['link']}" if e["link"] else ""),
                                       "acao": f"Prepare-me para o compromisso '{e['titulo']}' às {hora} (agenda {conta}): "
                                               f"busque e-mails e memória relacionados e faça um resumo de 5 linhas.",
                                       "confianca": 1})
        except Exception as e:
            await hub.broadcast({"type": "error", "text": f"Vigia da agenda: {e}"})
        await asyncio.sleep(120)
