"""Tarefas de fundo do servidor: lembretes, rotinas agendadas e vigias (e-mail e agenda)."""
import asyncio, json, re
from datetime import timedelta
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock
from .config import DATA, PROMPTS, FAST_MODEL, now
from . import life, google

ROUTINES = DATA / "routines.json"
SEEN = DATA / "seen_mail.json"
DEFAULT_ROUTINES = [
    {"name": "briefing", "time": "07:00", "days": [0, 1, 2, 3, 4],
     "prompt": "Briefing da manhã para ler no celular: agenda de hoje nas duas contas; e-mails não lidos que pedem ação "
               "(separe pessoal e profissional, destaque recrutadores e prazos); lembretes de hoje. Curto."},
    {"name": "fechamento_semana", "time": "18:00", "days": [4],
     "prompt": "Fechamento da semana: resumo de gastos da semana, treinos e estudos registrados, e o que ficou pendente "
               "nos e-mails profissionais. Curto."},
]


def load_routines() -> list:
    if not ROUTINES.exists():
        ROUTINES.write_text(json.dumps(DEFAULT_ROUTINES, ensure_ascii=False, indent=2))
    return json.loads(ROUTINES.read_text())


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
    done = set()
    while True:
        n = now()
        for r in load_routines():
            key = (r["name"], n.date())
            if (r["time"] == n.strftime("%H:%M") and n.weekday() in r.get("days", range(7)) and key not in done):
                done.add(key)
                asyncio.create_task(run(r["prompt"], "rotina"))
        await asyncio.sleep(20)


async def mail_loop(hub, interval_min: int = 10):
    """Vigia os e-mails novos das duas contas e sugere ação quando precisa.
    Na primeira vez que vê uma conta, só aprende o que já existe (não sugere nada antigo)."""
    seen: dict = json.loads(SEEN.read_text()) if SEEN.exists() else {}
    while True:
        try:
            for conta in google.authorized():
                msgs = await asyncio.to_thread(google.list_messages, conta, "is:unread newer_than:2d category:primary", 15)
                first_time = conta not in seen
                known = set(seen.get(conta, []))
                new = [m for m in msgs if m["id"] not in known]
                seen[conta] = (list(known) + [m["id"] for m in new])[-1000:]
                SEEN.write_text(json.dumps(seen))
                if first_time or not new or (not hub.clients and not hub.has_push()):
                    continue
                lista = "\n".join(f"id={m['id']} | de={m['de']} | assunto={m['assunto']} | {m['trecho']}" for m in new)
                items = await fast_json((PROMPTS / "mail_triage.md").read_text(), f"Conta: {conta}\n{lista}") or []
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
