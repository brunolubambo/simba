"""Níveis de autonomia aplicados a cada chamada de ferramenta.
Livre: ler, buscar, rascunhar, registrar dados locais, navegar/ler sites.
Pede aprovação: enviar e-mail, remover evento, evento com convidados, clicar/digitar em sites,
comandos sensíveis, escrita fora do workspace. Bloqueado: comandos destrutivos."""
import re
from pathlib import Path
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from .config import WORKSPACE
from . import browser

FREE = {"Read", "Glob", "Grep", "WebSearch", "WebFetch", "TodoWrite", "Task", "Agent",
        "mcp__memory__remember", "mcp__memory__recall", "mcp__vision__screenshot",
        "mcp__google__gmail_buscar", "mcp__google__gmail_ler", "mcp__google__gmail_rascunho",
        "mcp__google__gmail_marcar_lido", "mcp__google__agenda_listar",
        "mcp__google__drive_buscar", "mcp__google__drive_ler",
        "mcp__squad__agente_criar", "mcp__squad__agente_listar"} | browser.FREE
FREE_PREFIX = ("mcp__vida__",)   # dados locais, reversíveis
BLOCKED_BASH = [r"\brm\s+-rf?\s+(/|~|\$HOME)", r"\bsudo\b", r"\bmkfs\b", r"\bdd\s+if=",
                r":\(\)\s*\{", r"\bchmod\s+-R\s+777\s+/", r"curl[^|]*\|\s*(ba)?sh"]
ALWAYS_ASK_BASH = [r"\bvercel\b.*--prod", r"\bgit\s+push\b", r"\bnpm\s+publish\b", r"\brm\b"]


def _inside_workspace(p: str) -> bool:
    try:
        Path(p).resolve().relative_to(WORKSPACE.resolve())
        return True
    except ValueError:
        return False


def describe(tool: str, i: dict) -> str | None:
    """Texto da aprovação, ou None se a ação é livre."""
    if tool in FREE or tool.startswith(FREE_PREFIX):
        return None
    if tool == "mcp__google__gmail_enviar":
        para = i.get("para") or ("resposta ao e-mail " + i.get("responder_a", ""))
        return f"Enviar e-mail pela conta {i.get('conta')} para {para}\nAssunto: {i.get('assunto', '(mesmo do original)')}\n\n{i.get('corpo', '')[:600]}"
    if tool == "mcp__google__agenda_criar":
        if not i.get("convidados"):
            return None
        return f"Criar '{i.get('titulo')}' em {i.get('inicio')} na agenda {i.get('conta')} e convidar {i.get('convidados')}"
    if tool == "mcp__google__agenda_remover":
        return f"Remover evento {i.get('id')} da agenda {i.get('conta')}"
    if tool == "mcp__squad__agente_remover":
        return f"Remover o especialista '{i.get('id')}'"
    if tool.startswith("mcp__browser__"):
        return f"No navegador: {tool.split('__')[-1].replace('browser_', '')} {str(i)[:250]}"
    if tool in ("Write", "Edit", "NotebookEdit"):
        p = i.get("file_path", "")
        return None if _inside_workspace(p) else f"Escrever fora do workspace: {p}"
    if tool == "Bash":
        cmd = i.get("command", "")
        return f"Executar: {cmd}" if any(re.search(p, cmd) for p in ALWAYS_ASK_BASH) else None
    return f"Usar {tool}: {str(i)[:250]}"


def make_can_use_tool(approve):
    async def can_use_tool(tool_name, tool_input, context):
        if tool_name == "Bash" and any(re.search(p, tool_input.get("command", "")) for p in BLOCKED_BASH):
            return PermissionResultDeny(message="Comando bloqueado pelos guardrails.")
        text = describe(tool_name, tool_input)
        if text is None:
            return PermissionResultAllow()
        ok = await approve(text)
        return PermissionResultAllow() if ok else PermissionResultDeny(message="Usuário negou. Não tente contornar.")
    return can_use_tool
