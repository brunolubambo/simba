"""Subagentes: fixos (em grupos) + especialistas criados pelo Squad Creator (data/agents/*.json)."""
import json
from claude_agent_sdk import AgentDefinition
from .config import PROMPTS, DATA
from . import google, life, browser, documentos

READ = ["Read", "Glob", "Grep"]
BUILD = READ + ["Write", "Edit", "Bash"]
WEB = ["WebSearch", "WebFetch"]
MEM = ["mcp__memory__remember", "mcp__memory__recall"]
TG = ["mcp__telegram__telegram_enviar"]            # mandar mensagens e arquivos ao Bruno no Telegram
DOCS = documentos.NAMES                             # criar .docx/.pdf
CUSTOM_DIR = DATA / "agents"

# Ferramentas que um especialista criado pode receber
PRESETS = {
    "web": WEB, "arquivos": ["Write", "Edit"], "codigo": ["Write", "Edit", "Bash"],
    "email_agenda": google.NAMES, "lembretes": life.names(life.LEMBRETES), "financas": life.names(life.FINANCAS),
    "treinos": life.names(life.TREINOS), "estudos": life.names(life.ESTUDOS), "navegador": browser.NAMES,
    "telegram": TG, "documentos": DOCS,
}


def _p(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


# nome: (grupo, rótulo no painel, descrição para o orquestrador, ferramentas)
BASE = {
    "secretaria": ("Dia a dia", "Secretária", "E-mails (duas contas), agenda, lembretes e Drive: triagem, respostas, compromissos.",
                   READ + google.NAMES + life.names(life.LEMBRETES) + MEM + TG + DOCS),
    "carreira": ("Dia a dia", "Carreira", "Vagas, recrutadores, processos seletivos, CV, carta, entrevistas (conta profissional).",
                 READ + ["Write", "Edit"] + WEB + google.NAMES + life.names(life.LEMBRETES) + MEM + TG + DOCS),
    "financas": ("Dia a dia", "Finanças", "Registra gastos e receitas, resumos, orçamentos e planilhas.",
                 BUILD + life.names(life.FINANCAS) + MEM + TG + DOCS),
    "treinador": ("Dia a dia", "Treinador", "Treinos, cargas, evolução e rotina de academia.",
                  READ + ["Write"] + life.names(life.TREINOS + life.LEMBRETES) + MEM + TG),
    "tutor": ("Dia a dia", "Tutor", "Aulas e prática de idiomas e estudos, com registro de progresso.",
              READ + ["Write", "WebSearch"] + life.names(life.ESTUDOS) + MEM + TG),
    "pesquisador": ("Dia a dia", "Pesquisador", "Pesquisa na web e comparações (produtos, imóveis, carros, serviços) com links.",
                    WEB + ["Read", "Write"] + TG + DOCS),
    "navegador": ("Dia a dia", "Navegador", "Opera sites: acompanha páginas, preenche formulários, extrai dados.",
                  READ + browser.NAMES),
    "analista": ("Especialistas", "Analista", "Analisa dados e números (gastos, treinos, estudos, planilhas, CSV) e mostra padrões com gráficos.",
                 BUILD + life.names(life.FINANCAS + life.TREINOS + life.ESTUDOS) + TG + DOCS),
    "rootcause": ("Especialistas", "Rootcause", "Investiga a causa raiz de problemas (erros, falhas, algo que parou de funcionar) antes de corrigir.",
                  READ + ["Bash"] + WEB),
    "arquiteto": ("Criação", "Arquiteto", "Planeja estrutura e stack antes de construir um projeto novo.", READ + ["WebSearch"]),
    "desenvolvedor": ("Criação", "Desenvolvedor", "Escreve código: sites, apps, scripts, automações, dashboards.", BUILD),
    "designer_ux": ("Criação", "Designer UX", "Layout, hierarquia, acessibilidade e textos de interfaces.", READ + ["Write", "Edit"]),
    "qa": ("Criação", "QA", "Testa o que foi construído e reporta bugs.", READ + ["Bash"]),
    "publicador": ("Criação", "DevOps", "Faz deploy/publica entregas online (só com aprovação).", READ + ["Bash"]),
    "conclave_defensor": ("Conclave", "Defensor", "Conclave: constrói o MELHOR argumento a favor da opção em análise.", READ + WEB + ["mcp__memory__recall"]),
    "conclave_advogado": ("Conclave", "Advogado do diabo", "Conclave: ataca a opção em análise, riscos e custos ocultos.", READ + WEB + ["mcp__memory__recall"]),
    "conclave_sintetizador": ("Conclave", "Sintetizador", "Conclave: pesa defesa e ataque e dá a recomendação final com condições.", READ + ["mcp__memory__recall"]),
    "revisor": ("Conclave", "Crítico", "Critica planos e resultados importantes antes de entregar (e-mails sensíveis, candidaturas).", READ),
}


def load_custom() -> dict:
    out = {}
    for f in sorted(CUSTOM_DIR.glob("*.json")):
        try:
            out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return out


def _active():
    return {n: v for n, v in BASE.items() if n != "navegador" or browser.ENABLED}


def build_agents() -> dict:
    agents = {n: AgentDefinition(description=d, prompt=_p(n), tools=t) for n, (_, _, d, t) in _active().items()}
    for name, c in load_custom().items():
        tools = READ + MEM + [t for p in c.get("ferramentas", []) for t in PRESETS.get(p, [])]
        agents[name] = AgentDefinition(description=f"[Especialista criado] {c['descricao']}",
                                       prompt=c["instrucoes"], tools=sorted(set(tools)))
    return agents


def roster() -> list[dict]:
    """Para o painel."""
    out = [{"id": n, "nome": r, "grupo": g, "descricao": d} for n, (g, r, d, _) in _active().items()]
    out += [{"id": n, "nome": c.get("rotulo", n), "grupo": "Criados por você", "descricao": c["descricao"]}
            for n, c in load_custom().items()]
    return out
