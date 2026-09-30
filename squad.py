"""Squad Creator: cria, lista e remove especialistas sob demanda. Ficam em data/agents/<nome>.json
e passam a valer no pedido seguinte (a conversa continua)."""
import json, re, unicodedata
from claude_agent_sdk import tool, create_sdk_mcp_server
from .toolkit import schema, safe
from . import agents

CHANGED = {"flag": False}


def _id(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40] or "especialista"


@tool("agente_criar", "Cria um especialista novo e permanente. Escreva instruções completas (papel, método, formato da resposta, limites).",
      schema({"nome": ("string", "nome curto, ex.: Leilões judiciais"),
              "descricao": ("string", "1 frase: quando usar este especialista"),
              "instrucoes": ("string", "prompt de sistema completo do especialista")},
             {"ferramentas": ("string", "separadas por vírgula: " + ", ".join(agents.PRESETS))}))
@safe
def agente_criar(a):
    aid = _id(a["nome"])
    if aid in agents.BASE:
        raise ValueError(f"'{aid}' já é um agente fixo; escolha outro nome.")
    ferr = [f.strip() for f in a.get("ferramentas", "").split(",") if f.strip()]
    bad = [f for f in ferr if f not in agents.PRESETS]
    if bad:
        raise ValueError(f"ferramentas desconhecidas: {bad}. Opções: {list(agents.PRESETS)}")
    (agents.CUSTOM_DIR / f"{aid}.json").write_text(json.dumps(
        {"rotulo": a["nome"], "descricao": a["descricao"], "instrucoes": a["instrucoes"], "ferramentas": ferr},
        ensure_ascii=False, indent=2))
    CHANGED["flag"] = True
    return f"Especialista '{a['nome']}' criado (id {aid}). Estará disponível a partir do próximo pedido."


@tool("agente_listar", "Lista os especialistas criados.", schema({}))
@safe
def agente_listar(a):
    c = agents.load_custom()
    return "\n".join(f"{k}: {v['rotulo']} — {v['descricao']} [{', '.join(v['ferramentas'])}]" for k, v in c.items()) or "Nenhum criado ainda."


@tool("agente_remover", "Remove um especialista criado (pede aprovação).", schema({"id": ("string", "id do especialista")}))
@safe
def agente_remover(a):
    f = agents.CUSTOM_DIR / f"{_id(a['id'])}.json"
    if not f.exists():
        raise ValueError("não encontrado")
    f.unlink()
    CHANGED["flag"] = True
    return "Removido."


squad_server = create_sdk_mcp_server(name="squad", version="1.0.0", tools=[agente_criar, agente_listar, agente_remover])
