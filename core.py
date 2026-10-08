import asyncio, inspect, os, time
from typing import AsyncIterator, Awaitable, Callable
from claude_agent_sdk import (ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, UserMessage,
                              TextBlock, ToolUseBlock, ToolResultBlock, ResultMessage)
from .config import WORKSPACE, MODEL, MAX_TURNS, MAX_SESSION_TURNS, MAX_BUDGET_USD, PROMPTS, now_label
from .agents import build_agents
from .guardrails import make_can_use_tool
from .memory import memory_server, load_context
from .vision import vision_server
from .google import google_server, authorized
from .life import life_server
from .squad import squad_server, CHANGED
from .tasks import routines_server
from .telegram import telegram_server
from .documentos import docs_server
from . import browser, celular, pc, rapido
from .conversa import conversa_server

Approver = Callable[[str], Awaitable[bool]]
AGENT_TOOLS = ("Task", "Agent")


def _mcp_tool_count(servers: dict) -> int:
    """Quantas ferramentas MCP foram montadas para esta consulta. Só para o log [perf]."""
    total = 0
    for spec in servers.values():
        if not isinstance(spec, dict):
            continue
        if spec.get("type") != "sdk":
            total += len(browser.NAMES)
            continue
        try:
            entry = spec["instance"]._request_handlers["tools/list"]
            tools = inspect.getclosurevars(entry.handler).nonlocals.get("tools") or []
            total += len(tools)
        except Exception:
            pass
    return total


def _native_claude() -> str | None:
    """No Windows o npm publica um claude.cmd, que o SDK recusa. O executável nativo fica ao lado."""
    if os.name != "nt":
        return None
    roots = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(os.path.join(appdata, "npm", "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe"))
    roots.append(os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe"))
    return next((p for p in roots if os.path.isfile(p)), None)


_BUDGET_REPLY = "Atingi o limite de custo desta sessão. Reiniciei, tente de novo."


def _over_budget(msg=None, exc=None) -> bool:
    """Teto da sessão: resultado com custo no limite, ou erro de budget do SDK."""
    if msg is not None:
        subtype = (getattr(msg, "subtype", "") or "").lower()
        if "budget" in subtype:
            return True
        errors = getattr(msg, "errors", None) or []
        if any("budget" in str(item).lower() for item in errors):
            return True
        cost = getattr(msg, "total_cost_usd", None)
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= MAX_BUDGET_USD:
            return True
    if exc is not None:
        subtype = (getattr(exc, "subtype", "") or "").lower()
        if "budget" in subtype or "budget" in str(exc).lower():
            return True
        data = getattr(exc, "data", None)
        if isinstance(data, dict):
            cost = data.get("total_cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= MAX_BUDGET_USD:
                return True
    return False


class Simba:
    def __init__(self, approve: Approver):
        self.approve = approve
        self.session_id: str | None = None
        self._lock = asyncio.Lock()
        self._connected = False
        self._turns = 0
        self._session_cost = 0.0
        self._last_user = ""
        self._last_answer = ""
        self._bridge = ""
        self._build()

    def _build(self):
        prompt = (PROMPTS / "simba.md").read_text(encoding="utf-8")
        memory = load_context()
        system = prompt + "\n\n# Memória\n" + memory
        servers = {"memory": memory_server, "google": google_server, "vida": life_server, "squad": squad_server,
                   "telegram": telegram_server, "docs": docs_server, "rotinas": routines_server,
                   "conversa": conversa_server}
        if os.getenv("OBSERVER_ENABLED", "true").lower() == "true":
            servers["vision"] = vision_server
        if celular.enabled():
            servers["celular"] = celular.celular_server
        if pc.enabled() and pc.pc_server:
            servers["pc"] = pc.pc_server
        if browser.ENABLED:
            servers.update(browser.server_config())
        agents = build_agents()
        self._load = {"prompt": len(prompt), "memory": len(memory), "system": len(system),
                      "agents": len(agents), "mcp": _mcp_tool_count(servers)}
        cli = _native_claude()
        self.options = ClaudeAgentOptions(
            system_prompt=system, model=MODEL, cwd=str(WORKSPACE), agents=agents, mcp_servers=servers,
            cli_path=cli,
            can_use_tool=make_can_use_tool(self.approve), max_turns=MAX_TURNS, max_budget_usd=MAX_BUDGET_USD,
            permission_mode="default", resume=self.session_id)
        self.client = ClaudeSDKClient(options=self.options)

    async def start(self):
        if not self._connected:
            await self.client.connect()
            self._connected = True

    async def warm(self):
        """Abre o Claude ao ligar o servidor, para a primeira pergunta não pagar a abertura."""
        async with self._lock:
            await self.start()

    async def stop(self):
        if self._connected:
            await self.client.disconnect()
            self._connected = False

    async def reload(self):
        """Recarrega agentes e memória mantendo a conversa (retoma a mesma sessão)."""
        await self.stop()
        self._build()
        CHANGED["flag"] = False

    def _topic_summary(self) -> str:
        """Resumo local do último assunto. Sem chamada ao modelo."""
        user = " ".join(self._last_user.split())
        answer = " ".join(self._last_answer.split())
        if not user and not answer:
            return ""
        return f"Pergunta: {user} Resposta: {answer}"[:400]

    def _compose(self, text: str, ponte_rapida: str | None = None) -> str:
        """`ponte_rapida`: bloco da via rapida ja tirado para este pedido (o reenvio reusa o mesmo, para a
        sessao nova tambem receber). Sem ele, pega agora o que a via rapida ainda nao entregou."""
        lines = [f"[agora: {now_label()} | contas Google conectadas: {authorized() or 'nenhuma'}]"]
        if self._bridge:
            lines.append(f"[assunto anterior: {self._bridge}]")
            self._bridge = ""
        if ponte_rapida is None:
            ponte_rapida = rapido.tomar_para_agente(rapido.DISPOSITIVO)
        if ponte_rapida:
            lines.append(ponte_rapida)
        return "\n".join(lines) + "\n" + text

    def _remember_cost(self, msg) -> None:
        self.session_id = getattr(msg, "session_id", None) or self.session_id
        cost = getattr(msg, "total_cost_usd", None)
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            self._session_cost = float(cost)

    def _log_cost(self) -> None:
        print(f"[custo] sessão=US$ {self._session_cost:.2f} turnos={self._turns}", flush=True)

    async def _reset_session(self, reason: str) -> None:
        """Encerra o cliente atual. A memória continua no prompt da sessão nova."""
        print(
            f"[sessao] reset por {reason} turnos={self._turns} custo=US$ {self._session_cost:.2f}",
            flush=True,
        )
        self._bridge = self._topic_summary()
        await self.stop()
        self.session_id = None
        self._turns = 0
        self._session_cost = 0.0
        self._build()

    async def ask(self, text: str) -> AsyncIterator[dict]:
        """Eventos: text | tool | agent (working/idle) | done."""
        t0 = time.perf_counter()
        async with self._lock:
            print(f"[perf] {time.strftime('%H:%M:%S')} espera pelo _lock +{time.perf_counter() - t0:.2f}s", flush=True)
            if CHANGED["flag"]:
                await self.reload()
            if MAX_SESSION_TURNS > 0 and self._turns >= MAX_SESSION_TURNS:
                await self._reset_session("turnos")
            ponte_rapida = rapido.tomar_para_agente(rapido.DISPOSITIVO)   # entregue uma vez; reenvio reusa
            query_text = self._compose(text, ponte_rapida)
            load = getattr(self, "_load", {})
            first_text = False
            first_s = None
            for attempt in (1, 2):
                await self.start()
                label = "recebida" if attempt == 1 else "reenvio"
                print(f"[perf] {time.strftime('%H:%M:%S')} {label} chars={len(text)} "
                      f"sistema={load.get('system', '?')}c (prompt={load.get('prompt', '?')} memoria={load.get('memory', '?')}) "
                      f"agentes={load.get('agents', '?')} mcp={load.get('mcp', '?')}", flush=True)
                pending: list[dict] = []
                shown: list[str] = []
                flushed = False
                working: dict[str, str] = {}
                over = False
                result_msg = None

                def drain():
                    nonlocal flushed
                    while pending:
                        ev = pending.pop(0)
                        shown.append(ev["text"])
                        flushed = True
                        yield ev

                try:
                    await self.client.query(query_text)
                    async for msg in self.client.receive_response():
                        if isinstance(msg, AssistantMessage):
                            for b in msg.content:
                                if isinstance(b, TextBlock) and not getattr(msg, "parent_tool_use_id", None):
                                    if not first_text:
                                        first_text = True
                                        first_s = time.perf_counter() - t0
                                        print(f"[perf] {time.strftime('%H:%M:%S')} primeiro TextBlock "
                                              f"+{first_s:.2f}s", flush=True)
                                    pending.append({"type": "text", "text": b.text})
                                elif isinstance(b, ToolUseBlock):
                                    for ev in drain():
                                        yield ev
                                    if b.name in AGENT_TOOLS:
                                        agent = b.input.get("subagent_type", "?")
                                        working[b.id] = agent
                                        yield {"type": "agent", "id": agent, "state": "working",
                                               "task": str(b.input.get("description", ""))[:80]}
                                    else:
                                        yield {"type": "tool", "name": b.name.split("__")[-1], "input": b.input}
                        elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                            for b in msg.content:
                                if isinstance(b, ToolResultBlock) and b.tool_use_id in working:
                                    yield {"type": "agent", "id": working.pop(b.tool_use_id), "state": "idle"}
                        elif isinstance(msg, ResultMessage):
                            result_msg = msg
                            self._remember_cost(msg)
                            over = _over_budget(msg)
                            if not over:
                                for ev in drain():
                                    yield ev
                                self._last_user = text
                                self._last_answer = "".join(shown)[:2000]
                                self._turns += 1
                            if not first_text:
                                print(f"[perf] {time.strftime('%H:%M:%S')} primeiro TextBlock ausente", flush=True)
                            elapsed = time.perf_counter() - t0
                            print(f"[perf] {time.strftime('%H:%M:%S')} done +{elapsed:.2f}s "
                                  f"custo={getattr(msg, 'total_cost_usd', None)}", flush=True)
                            self._log_cost()
                            for agent in working.values():
                                yield {"type": "agent", "id": agent, "state": "idle"}
                            if not over:
                                yield {"type": "done", "cost_usd": getattr(msg, "total_cost_usd", None),
                                       "model_s": round(elapsed, 2),
                                       "first_s": round(first_s, 2) if first_s is not None else None}
                except Exception as exc:
                    if not _over_budget(exc=exc):
                        raise
                    over = True
                    data = getattr(exc, "data", None)
                    if isinstance(data, dict) and isinstance(data.get("total_cost_usd"), (int, float)):
                        self._session_cost = float(data["total_cost_usd"])
                    elapsed = time.perf_counter() - t0
                    print(f"[perf] {time.strftime('%H:%M:%S')} done +{elapsed:.2f}s custo=budget", flush=True)
                    self._log_cost()
                    for agent in working.values():
                        yield {"type": "agent", "id": agent, "state": "idle"}

                if not over:
                    if result_msg is None:
                        for ev in drain():
                            yield ev
                    return
                cost_now = self._session_cost
                await self._reset_session("custo")
                if attempt == 1 and not flushed:
                    query_text = self._compose(text, ponte_rapida)
                    continue
                if flushed:
                    for ev in drain():
                        yield ev
                else:
                    yield {"type": "text", "text": _BUDGET_REPLY}
                elapsed = time.perf_counter() - t0
                yield {"type": "done", "cost_usd": cost_now,
                       "model_s": round(elapsed, 2),
                       "first_s": round(first_s, 2) if first_s is not None else None}
                return
