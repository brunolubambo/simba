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
from . import browser, celular

Approver = Callable[[str], Awaitable[bool]]
AGENT_TOOLS = ("Task", "Agent")


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
        if celular.enabled():
            servers["celular"] = celular.celular_server
        if browser.ENABLED:
            servers.update(browser.server_config())
        cli = _native_claude()
        self.options = ClaudeAgentOptions(
            system_prompt=system, model=MODEL, cwd=str(WORKSPACE), agents=build_agents(), mcp_servers=servers,
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

    async def ask(self, text: str) -> AsyncIterator[dict]:
        """Eventos: text | tool | agent (working/idle) | done."""
        async with self._lock:
            if CHANGED["flag"]:
                await self.reload()
            await self.start()
            ctx = f"[agora: {now_label()} | contas Google conectadas: {authorized() or 'nenhuma'}]\n"
            await self.client.query(ctx + text)
            working: dict[str, str] = {}
            async for msg in self.client.receive_response():
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
