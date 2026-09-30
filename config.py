import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("SIMBA_DATA", ROOT / "data"))              # memória, banco, tokens (volume na nuvem)
WORKSPACE = Path(os.getenv("SIMBA_WORKSPACE", ROOT / "workspace"))  # onde o Simba cria arquivos
MEMORY = Path(os.getenv("SIMBA_MEMORY_DIR", DATA / "memory"))   # cofre do Obsidian
PROMPTS = Path(__file__).resolve().parent / "prompts"
TEMPLATES = Path(__file__).resolve().parent / "templates"
for p in (DATA, WORKSPACE, MEMORY, DATA / "google", DATA / "agents"):
    p.mkdir(parents=True, exist_ok=True)

MODEL = os.getenv("SIMBA_MODEL", "claude-sonnet-5-5")
FAST_MODEL = os.getenv("OBSERVER_MODEL", "claude-haiku-4-5-20251001")
MAX_TURNS = int(os.getenv("SIMBA_MAX_TURNS", "30"))
MAX_BUDGET_USD = float(os.getenv("SIMBA_MAX_BUDGET_USD", "2"))
TZ = os.getenv("SIMBA_TZ", "America/Fortaleza")

ACCOUNTS = {
    "pessoal": os.getenv("GOOGLE_PESSOAL", "brunolubambo@gmail.com"),
    "profissional": os.getenv("GOOGLE_PROFISSIONAL", "brunolubamboadm@gmail.com"),
}

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def now() -> datetime:
    """Hora local, sem fuso (tudo no banco é hora local)."""
    return datetime.now(ZoneInfo(TZ)).replace(tzinfo=None, microsecond=0)


def now_label() -> str:
    n = now()
    return f"{DIAS[n.weekday()]}, {n:%Y-%m-%d %H:%M} ({TZ})"


def public_url() -> str:
    """URL pública do app (para o login do Google). Na Railway é detectada sozinha."""
    if os.getenv("PUBLIC_URL"):
        return os.getenv("PUBLIC_URL").rstrip("/")
    if os.getenv("RAILWAY_PUBLIC_DOMAIN"):
        return "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")
    return "http://localhost:8000"
