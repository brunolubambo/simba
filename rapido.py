"""Via rapida: pedidos simples ou conversacionais do celular sao respondidos direto pelo Haiku,
frase por frase, sem passar pelo agente completo.

Fica DESLIGADA por padrao (RAPIDO_ATIVO). Pedido que precisa de ferramenta, acao, dado atual ou memoria
pessoal vai ao agente: pela lista local (vai_direto_ao_agente), ou porque o Haiku chamou a ferramenta
escalar_para_agente, ou porque a chamada ao Haiku falhou.

Nunca registrar o texto das falas, das respostas nem chaves: so tempos e contagens.
"""
import os
import re
import time
import unicodedata

from . import conversa, perfil
from .config import now_label

# ---------- configuracao (lida em funcao, para os testes poderem alterar o ambiente) ----------

_VERDADEIRO = ("1", "true", "sim", "yes", "on")


def ativo() -> bool:
    return os.getenv("RAPIDO_ATIVO", "false").strip().lower() in _VERDADEIRO


def modelo() -> str:
    """RAPIDO_MODEL; se vazia, o mesmo modelo do modo conversa (CONVERSA_MODEL)."""
    return os.getenv("RAPIDO_MODEL", "").strip() or os.getenv("CONVERSA_MODEL", "").strip() or conversa.MODEL


def max_tokens() -> int:
    try:
        return max(1, int(os.getenv("RAPIDO_MAX_TOKENS", "200")))
    except ValueError:
        return 200


def timeout_s() -> float:
    try:
        valor = float(os.getenv("RAPIDO_TIMEOUT_S", "6"))
    except ValueError:
        return 6.0
    return valor if valor > 0 else 6.0


# ---------- lista local: o que vai DIRETO ao agente ----------

# Palavras e expressoes (sem acento, minusculas) que mandam o pedido ao agente completo, sem chamar o Haiku.
# Casam por palavra inteira; no plural (+s) tambem. Na duvida, o pedido vai ao agente: edite a vontade.
DIRETO_AO_AGENTE = (
    # hora, data e tempo
    "hora", "horas", "data", "hoje", "amanha", "ontem", "semana", "tempo", "agora", "atual", "atualmente",
    # clima
    "clima", "previsao", "temperatura", "chuva", "transito",
    # agenda e comunicacao
    "agenda", "agende", "calendario", "compromisso", "reuniao", "reunioes", "evento",
    "email", "e-mail", "mensagem", "mensagens", "telegram", "whatsapp",
    # alarme, lembrete, anotacao
    "alarme", "despertador", "timer", "cronometro", "lembrete", "lembre", "lembra", "lembrar",
    "anote", "anota", "anotar", "acorde", "acorda", "avise", "avisa",
    # acoes no celular e no PC
    "abra", "abre", "abrir", "feche", "fechar", "ligue", "ligar", "desligue", "desligar",
    "toque", "toca", "tocar", "mande", "manda", "mandar", "envie", "enviar",
    "foto", "camera", "tela", "computador", "pc", "arquivo", "pasta",
    # busca e dados de fora
    "pesquise", "pesquisa", "pesquisar", "busque", "buscar", "procure", "procurar",
    "preco", "cotacao", "dolar", "euro", "bitcoin", "noticia", "placar",
    # rotinas e tarefas
    "rotina", "tarefa",
    # praticar idioma / simular situacao: so o agente tem a ferramenta iniciar_modo_conversa
    "praticar", "pratica", "praticamos", "treinar", "treino", "simular", "simule", "simulacao",
    "entrevista", "negociacao", "debate", "apresentacao", "atendimento", "modo conversa", "conversar em",
    # memoria e fatos pessoais
    "meu", "minha", "meus", "minhas", "lembra que", "o que eu disse",
)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


def _montar(termos) -> re.Pattern:
    # Palavra inteira (nada de letra ou numero colado) e plural simples; "hora" nao casa dentro de "ahora".
    corpo = "|".join(re.escape(t) + ("(?:s|es)?" if " " not in t else "") for t in sorted(termos, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{corpo})(?![a-z0-9])")


_PADRAO_DIRETO = _montar(DIRETO_AO_AGENTE)


def vai_direto_ao_agente(texto: str) -> bool:
    """True = a lista local manda o pedido ao agente completo (sem chamar o Haiku). Texto vazio tambem."""
    limpo = _normalizar(texto)
    if not limpo:
        return True
    return _PADRAO_DIRETO.search(limpo) is not None


# ---------- prompt minimo e ferramenta ----------

FERRAMENTA_NOME = "escalar_para_agente"

FERRAMENTA = {
    "name": FERRAMENTA_NOME,
    "description": (
        "Passa o pedido ao agente completo do SIMBA, que tem ferramentas (agenda, e-mail, alarme, celular, PC, "
        "busca na web, memoria). Chame ANTES de escrever qualquer texto quando o pedido depender de dado de fora, "
        "de uma acao, do PC, do celular, de memoria ou fatos pessoais do usuario, ou quando estiver em duvida."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"motivo": {"type": "string", "description": "motivo curto, em poucas palavras (opcional)"}},
        "required": [],
    },
}


def prompt_sistema(p: dict | None = None, agora: str | None = None) -> str:
    """Prompt minimo do Haiku: persona, regras de voz e de escalada. Sem Notas e sem a memoria do agente."""
    p = perfil.carregar() if p is None else p
    agora = agora or now_label()
    nome = p.get("nome_tutor") or "Simba"
    usuario = p.get("nome_usuario") or ""
    de = f"assistente pessoal de {usuario}" if usuario else "assistente pessoal do usuario"
    return (
        f"Voce e {nome}, {de}, falando por voz pelo celular. Portugues do Brasil. "
        "Formal, direto, com humor seco; \"senhor\" com moderacao. Discorda com respeito.\n"
        f"Agora: {agora}.\n\n"
        "Como falar:\n"
        "- Resposta curta, para ser dita em voz alta: de 1 a 3 frases, sem markdown, listas, emojis ou simbolos.\n"
        "- Responda em portugues. Se o usuario pedir traducao ou conversa em outro idioma, responda nesse idioma.\n"
        "- Cumprimentos, conversa casual, explicacoes curtas, traducao e perguntas gerais que nao dependem de "
        "dados atuais voce responde sozinho.\n\n"
        "Limites:\n"
        "- Voce NAO tem ferramentas. NUNCA diga que fez uma acao (criar alarme, enviar mensagem, abrir app, "
        "anotar, lembrar, etc.).\n"
        f"- Para qualquer coisa que dependa de dado de fora (clima, precos, noticias), de acao, do PC, do celular, "
        f"da agenda, de e-mail, de memoria ou de fatos pessoais do usuario, para praticar ou treinar um idioma, "
        f"simular uma situacao (entrevista, negociacao, debate), ou se estiver em duvida: chame a "
        f"ferramenta {FERRAMENTA_NOME} ANTES de escrever qualquer texto."
    )


# ---------- contadores em memoria (padrao de conversa.USO_TOTAL) ----------

RAPIDO_USO = {"desde": time.time(), "rapidas": 0, "escaladas_haiku": 0, "escaladas_lista": 0, "falhas": 0,
              "tokens_entrada": 0, "tokens_saida": 0}


def contar(usage) -> None:
    """Soma os tokens de uma resposta do Haiku (entrada inclui o que veio do cache)."""
    def valor(campo: str) -> int:
        v = getattr(usage, campo, None) if usage is not None else None
        return v if isinstance(v, int) and not isinstance(v, bool) else 0
    RAPIDO_USO["tokens_entrada"] += (valor("input_tokens") + valor("cache_creation_input_tokens")
                                     + valor("cache_read_input_tokens"))
    RAPIDO_USO["tokens_saida"] += valor("output_tokens")


def uso() -> dict:
    return {**RAPIDO_USO, "ativo": ativo(), "modelo": modelo()}
