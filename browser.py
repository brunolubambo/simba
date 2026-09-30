"""Navegador automatizado (Playwright MCP, precisa de Node.js). Abre um Chrome separado,
com login próprio: entre uma vez nos sites que quiser e ele lembra (perfil em data/browser)."""
import os
from .config import DATA

ENABLED = os.getenv("BROWSER_ENABLED", "true").lower() == "true"
READ = ["browser_navigate", "browser_navigate_back", "browser_snapshot", "browser_take_screenshot",
        "browser_tabs", "browser_wait_for", "browser_console_messages", "browser_resize", "browser_close"]
ACT = ["browser_click", "browser_type", "browser_fill_form", "browser_select_option", "browser_press_key",
       "browser_hover", "browser_drag", "browser_file_upload", "browser_handle_dialog", "browser_evaluate"]
NAMES = [f"mcp__browser__{n}" for n in READ + ACT]
FREE = {f"mcp__browser__{n}" for n in READ}


def server_config() -> dict:
    return {"browser": {"type": "stdio", "command": "npx",
                        "args": ["-y", "@playwright/mcp@latest", "--user-data-dir", str(DATA / "browser")]}}
