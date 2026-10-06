"""Memória permanente como cofre do Obsidian (markdown + [[links]] + frontmatter).
  Perfil.md         quem você é e regras (criado do template)
  Notas.md          fatos soltos, com data
  Índice.md         links para os tópicos
  topicos/<X>.md    um arquivo por assunto (Carreira, Finanças, Pessoas...)
No PC, aponte SIMBA_MEMORY_DIR para uma pasta do seu cofre. Na nuvem, baixe pelo painel."""
import io, re, shutil, zipfile
from claude_agent_sdk import tool, create_sdk_mcp_server
from .config import MEMORY, TEMPLATES, now
from .toolkit import schema, ok

PROFILE = MEMORY / "Perfil.md"
NOTES = MEMORY / "Notas.md"
INDEX = MEMORY / "Índice.md"
TOPICS = MEMORY / "topicos"
TOPICS.mkdir(parents=True, exist_ok=True)
if (MEMORY / "profile.md").exists() and not PROFILE.exists():     # versões antigas
    (MEMORY / "profile.md").rename(PROFILE)
if (MEMORY / "notes.md").exists() and not NOTES.exists():
    (MEMORY / "notes.md").rename(NOTES)
if not PROFILE.exists():
    shutil.copy(TEMPLATES / "profile.md", PROFILE)


def slug(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|#^\[\]]", "", name).strip()
    return name[:1].upper() + name[1:60] if name else "Geral"


def topics() -> list[str]:
    return sorted(p.stem for p in TOPICS.glob("*.md"))


def _write_index():
    INDEX.write_text("---\ntags: [simba]\n---\n# Índice da memória do Simba\n\n- [[Perfil]]\n- [[Notas]]\n"
                     + "".join(f"- [[{t}]]\n" for t in topics()), encoding="utf-8")


def add_fact(fact: str, topico: str = "") -> str:
    stamp = f"{now():%Y-%m-%d}"
    if not topico:
        if not NOTES.exists():
            NOTES.write_text("---\ntags: [simba]\n---\n# Notas\n\n", encoding="utf-8")
        with NOTES.open("a", encoding="utf-8") as f:
            f.write(f"- {stamp}: {fact}\n")
        return "Notas"
    t = slug(topico)
    f = TOPICS / f"{t}.md"
    if not f.exists():
        f.write_text(f"---\ntags: [simba, topico]\ncriado: {stamp}\n---\n# {t}\n\nVoltar: [[Índice]]\n\n", encoding="utf-8")
        _write_index()
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"- {stamp}: {fact}\n")
    return t


def load_context() -> str:
    parts = [PROFILE.read_text(encoding="utf-8")]
    if NOTES.exists():
        parts.append("## Notas recentes\n" + NOTES.read_text(encoding="utf-8")[-4000:])
    if topics():
        parts.append("## Tópicos na memória (use recall para ler)\n" + ", ".join(topics()))
    return "\n\n".join(parts)


def search(q: str, limit: int = 40) -> list[str]:
    q = q.lower()
    hits = []
    for f in sorted(MEMORY.rglob("*.md")):
        if q in f.stem.lower():
            hits.append(f"## {f.stem}\n" + f.read_text(encoding="utf-8")[-3000:])
            continue
        hits += [f"[{f.stem}] {l}" for l in f.read_text(encoding="utf-8").splitlines() if q in l.lower()]
    return hits[:limit]


def export_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in MEMORY.rglob("*.md"):
            z.write(f, "Simba/" + str(f.relative_to(MEMORY)))
    return buf.getvalue()


def stats() -> dict:
    lines = sum(1 for f in MEMORY.rglob("*.md") for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("- "))
    return {"topicos": topics(), "fatos": lines}


@tool("remember", "Guarda um fato durável. Use `topico` para agrupar (ex.: Carreira, Finanças, Saúde e treino, Pessoas, "
      "Apartamento, Projetos). Não guarde senhas nem dados bancários.",
      schema({"fact": ("string", "o fato")}, {"topico": ("string", "assunto/nota do Obsidian")}))
async def remember(args):
    return ok(f"Guardado em [[{add_fact(args['fact'], args.get('topico', ''))}]].")


@tool("recall", "Busca na memória por palavra-chave ou nome de tópico (retorna o tópico inteiro).",
      schema({"query": ("string", "palavra-chave ou tópico")}))
async def recall(args):
    return ok("\n".join(search(args["query"])) or "Nada encontrado.")


memory_server = create_sdk_mcp_server(name="memory", version="1.0.0", tools=[remember, recall])
