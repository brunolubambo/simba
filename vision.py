"""Visão de tela: tira um screenshot; o agente abre a imagem com a ferramenta Read."""
import time
from claude_agent_sdk import tool, create_sdk_mcp_server
from .config import WORKSPACE


@tool("screenshot", "Captura a tela do usuário e devolve o caminho da imagem (leia-a com Read).", {})
async def screenshot(args):
    try:
        import mss, mss.tools
    except ImportError:
        return {"content": [{"type": "text", "text": "Instale `mss` (pip install mss) para habilitar a visão de tela."}], "is_error": True}
    out = WORKSPACE / ".screens"
    out.mkdir(exist_ok=True)
    path = out / f"screen_{int(time.time())}.png"
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))
    return {"content": [{"type": "text", "text": str(path)}]}


vision_server = create_sdk_mcp_server(name="vision", version="1.0.0", tools=[screenshot])
