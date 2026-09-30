import asyncio, os
from typing import AsyncIterator, Awaitable, Callable
from claude_agent_sdk import (ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, UserMessage,
                              TextBlock, ToolUseBlock, ToolResultBlock, ResultMessage)
from .config import WORKSPACE, MODEL, MAX_TURNS, MAX_BUDGET_USD, PROMPTS, now_label
from .agents import build_agents
from .guardrails import make_can_use_tool
from .memory import memory_server, load_context
from .vision import vision_server
from .google import google_server, authorized
from .life import life_server
from .squad import squad_server, CHANGED
from .telegram import telegram_server
from .documentos import docs_server
from . import browser

Approver = Callable[[str], Awaitable[bool]]
AGENT_TOOLS = ("Task", "Agent")


class Simba:
    def __init__(self, approve: Approver):
        self.approve = approve
        self.session_id: str | None = None
        self._lock = asyncio.Lock()
        self._connected = False
        self._build()

    def _build(self):
        system = (PROMPTS / "simba.md").read_text() + "\n\n# Memória\n" + load_context()
        servers = {"memory": memory_server, "google": google_server, "vida": life_server, "squad": squad_server,
                   "telegram": telegram_server, "docs": docs_server}
        if os.getenv("OBSERVER_ENABLED", "true").lower() == "true":
            servers["vision"] = vision_server
        if browser.ENABLED:
            servers.update(browser.server_config())
        self.options = ClaudeAgentOptions(
            system_prompt=system, model=MODEL, cwd=str(WORKSPACE), agents=build_agents(), mcp_servers=servers,
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

    async def ask(self, text: str) -> AsyncIterator[dict]:
        """Eventos: text | tool | agent (working/idle) | done."""
        # region agent log
        import time as _t, json as _j
        _t0 = _t.perf_counter(); _seen: set = set()
        def _dbg(m, **d):
            open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cursor", "debug-f7a251.log"), "a", encoding="utf-8").write(_j.dumps({"sessionId": "f7a251", "runId": "run1", "hypothesisId": "A", "location": "core.py:ask", "message": m, "data": {**d, "ms": round((_t.perf_counter() - _t0) * 1000)}, "timestamp": int(_t.time() * 1000)}) + "\n")
        # endregion
        async with self._lock:
            if CHANGED["flag"]:
                await self.reload()
            # region agent log
            _was = self._connected
            # endregion
            await self.start()
            # region agent log
            _dbg("client ready", wasConnected=_was, model=MODEL)
            # endregion
            ctx = f"[agora: {now_label()} | contas Google conectadas: {authorized() or 'nenhuma'}]\n"
            await self.client.query(ctx + text)
            working: dict[str, str] = {}
            async for msg in self.client.receive_response():
                # region agent log
                _k = type(msg).__name__
                if _k not in _seen or _k == "ResultMessage":
                    _seen.add(_k); _dbg("first " + _k, apiMs=getattr(msg, "duration_api_ms", None), turns=getattr(msg, "num_turns", None), blocks=[type(b).__name__ for b in getattr(msg, "content", [])] if isinstance(getattr(msg, "content", None), list) else None)
                # endregion
                if isinstance(msg, AssistantMessage):
                    for b in msg.content:
                        if isinstance(b, TextBlock) and not getattr(msg, "parent_tool_use_id", None):
                            yield {"type": "text", "text": b.text}
                        elif isinstance(b, ToolUseBlock):
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
                    self.session_id = getattr(msg, "session_id", None) or self.session_id
                    for agent in working.values():
                        yield {"type": "agent", "id": agent, "state": "idle"}
                    yield {"type": "done", "cost_usd": getattr(msg, "total_cost_usd", None)}
