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
from dataclasses import dataclass, field

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
FRASE_ESCALADA = "Um momento, vou verificar."   # dita so se nenhuma frase do Haiku ja saiu
CONTEXTO_MAX = 200                               # caracteres do que o Haiku ja disse, repassados ao agente

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


def prompt_sistema(p: dict | None = None, agora: str | None = None, contexto_agente: str = "") -> str:
    """Prompt minimo do Haiku: persona, regras de voz e de escalada. Sem Notas e sem a memoria do agente.
    `contexto_agente` e o resumo curto do que o agente tratou por ultimo (vazio = sem o bloco)."""
    p = perfil.carregar() if p is None else p
    agora = agora or now_label()
    nome = p.get("nome_tutor") or "Simba"
    usuario = p.get("nome_usuario") or ""
    de = f"assistente pessoal de {usuario}" if usuario else "assistente pessoal do usuario"
    resumo = _cortar(contexto_agente, CONTEXTO_AGENTE_MAX)
    extra = (
        "\n\nO agente completo, que tem as ferramentas, tratou disto ha pouco. Use so para entender o que o "
        f"usuario quer dizer e nao repita o conteudo.\nContexto recente do agente: {resumo}" if resumo else ""
    )
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
        f"{extra}"
    )


# ---------- historico curto da via rapida (so em memoria) ----------

# Nunca vai para disco nem para o log. Guarda so o que o Haiku respondeu sozinho; edite as constantes a vontade.
DISPOSITIVO = "celular"            # a via rapida so existe no app do celular
HISTORICO_TROCAS = 3               # quantas trocas (pergunta + resposta) o Haiku e o agente enxergam
HISTORICO_TEXTO_MAX = 300          # caracteres de cada texto guardado (pergunta e resposta)
HISTORICO_EXPIRA_S = 30 * 60       # sem trocas por este tempo, o historico do dispositivo e esquecido

# dispositivo -> {"ultima": instante da ultima troca registrada, "trocas": [{"pergunta","resposta","entregue"}]}
_HISTORICO: dict[str, dict] = {}


def _cortar(texto, limite: int) -> str:
    limpo = " ".join(str(texto or "").split())
    return limpo if len(limpo) <= limite else limpo[:limite - 3].rstrip() + "..."


def _vivo(device: str, agora: float) -> dict | None:
    """O historico do dispositivo, ou None se nao ha ou se expirou (nesse caso ele e apagado)."""
    dados = _HISTORICO.get(device)
    if dados is not None and agora - dados["ultima"] > HISTORICO_EXPIRA_S:
        _HISTORICO.pop(device, None)
        return None
    return dados


def registrar(device: str, pergunta: str, resposta: str, agora: float | None = None) -> None:
    """Guarda uma troca que o Haiku respondeu sozinho. Mantem so as ultimas HISTORICO_TROCAS. Texto vazio nao entra."""
    agora = time.monotonic() if agora is None else agora
    pergunta, resposta = _cortar(pergunta, HISTORICO_TEXTO_MAX), _cortar(resposta, HISTORICO_TEXTO_MAX)
    if not pergunta or not resposta:
        return
    dados = _vivo(device, agora)
    if dados is None:
        dados = _HISTORICO[device] = {"ultima": agora, "trocas": []}
    dados["trocas"].append({"pergunta": pergunta, "resposta": resposta, "entregue": False})
    del dados["trocas"][:-HISTORICO_TROCAS]
    dados["ultima"] = agora


def recentes(device: str, agora: float | None = None) -> list[tuple[str, str]]:
    """As trocas guardadas, da mais antiga para a mais nova, como (pergunta, resposta). Ler nao renova o prazo."""
    agora = time.monotonic() if agora is None else agora
    dados = _vivo(device, agora)
    return [(t["pergunta"], t["resposta"]) for t in dados["trocas"]] if dados else []


def limpar(device: str) -> None:
    _HISTORICO.pop(device, None)


PONTE_MAX = 600                    # caracteres do bloco "conversa rapida recente" que o agente recebe (total)
CONTEXTO_AGENTE_MAX = 400          # caracteres do resumo do agente que o Haiku recebe


def _montar_ponte(trocas: list[dict]) -> str:
    """"[conversa rapida recente: usuario: ...; assistente: ...]" com no maximo PONTE_MAX caracteres.
    Se nao couber tudo, ficam as trocas mais novas; uma troca sozinha grande demais e cortada."""
    prefixo, sufixo = "[conversa rapida recente: ", "]"
    folga = PONTE_MAX - len(prefixo) - len(sufixo)
    partes: list[str] = []
    usado = 0
    for t in reversed(trocas):
        parte = f"usuario: {t['pergunta']}; assistente: {t['resposta']}"
        custo = len(parte) + (2 if partes else 0)
        if usado + custo > folga:
            if not partes:
                partes.append(parte[:max(folga - 3, 0)].rstrip() + "...")
            break
        partes.insert(0, parte)
        usado += custo
    return prefixo + "; ".join(partes) + sufixo


def tomar_para_agente(device: str, agora: float | None = None) -> str:
    """O bloco com as trocas rapidas que o agente ainda nao viu, para o proximo Simba.ask. Cada troca e entregue
    uma unica vez (as que nao couberem no limite tambem contam como entregues). Vazio se nao ha nada novo
    ou se a via rapida esta desligada. As trocas continuam no historico do Haiku."""
    if not ativo():
        return ""
    agora = time.monotonic() if agora is None else agora
    dados = _vivo(device, agora)
    novas = [t for t in dados["trocas"] if not t["entregue"]] if dados else []
    if not novas:
        return ""
    for t in novas:
        t["entregue"] = True
    return _montar_ponte(novas)


def _mensagens(device: str, texto: str) -> list[dict]:
    """Trocas anteriores como turnos reais (user/assistant alternados), e por fim a mensagem atual."""
    mensagens: list[dict] = []
    for pergunta, resposta in recentes(device):
        mensagens.append({"role": "user", "content": pergunta})
        mensagens.append({"role": "assistant", "content": resposta})
    mensagens.append({"role": "user", "content": texto})
    return mensagens


# ---------- resposta do Haiku, frase por frase ----------

@dataclass
class Resultado:
    frases: list = field(default_factory=list)    # frases que ja SAIRAM para o app (ficam, mesmo se escalar)
    escalou: bool = False
    motivo: str = ""                              # "" | "haiku" (chamou a ferramenta) | "falha"
    primeira_frase: float | None = None
    total: float = 0.0


async def responder(texto: str, enviar, voz: str, idioma: str = "pt-BR", device: str = DISPOSITIVO,
                    contexto_agente: str = "") -> Resultado:
    """Pede a resposta ao Haiku e manda cada frase por `enviar` assim que fecha. Nunca levanta excecao:
    timeout, erro da API, resposta vazia ou falta de chave viram escalou=True, motivo="falha".
    O Haiku recebe as trocas anteriores do dispositivo; a troca de agora so entra no historico se ele a
    respondeu sozinho (sem escalar) e falou ao menos uma frase. `contexto_agente` e o resumo curto do que o
    agente tratou por ultimo, vindo de quem chama (rapido nao enxerga o Simba)."""
    t0 = time.perf_counter()
    res = Resultado()

    async def captar(ev):
        if ev.get("type") == "frase":
            if res.primeira_frase is None:
                res.primeira_frase = time.perf_counter() - t0
            res.frases.append(ev.get("text", ""))
        await enviar(ev)

    try:
        if conversa._CLIENTE is None and not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("sem ANTHROPIC_API_KEY")
        fala = await conversa.falar_stream(
            modelo=modelo(), sistema=prompt_sistema(contexto_agente=contexto_agente), mensagens=_mensagens(device, texto),
            max_tokens=max_tokens(), idioma=idioma, voz=voz, enviar=captar, contar=contar,
            timeout=timeout_s(), ferramentas=[FERRAMENTA])
    except Exception as e:
        print(f"[rapido] falha ({type(e).__name__})", flush=True)
        RAPIDO_USO["falhas"] += 1
        res.escalou, res.motivo = True, "falha"
    else:
        if fala.ferramenta is not None:
            RAPIDO_USO["escaladas_haiku"] += 1
            res.escalou, res.motivo = True, "haiku"
        elif not res.frases:
            print("[rapido] falha (resposta vazia)", flush=True)
            RAPIDO_USO["falhas"] += 1
            res.escalou, res.motivo = True, "falha"
        else:
            RAPIDO_USO["rapidas"] += 1
            registrar(device, texto, " ".join(res.frases))
    res.total = time.perf_counter() - t0
    return res


def perf(res: Resultado) -> None:
    """Uma linha por turno, so com tempos e contagens (nunca o texto)."""
    def seg(v):
        return f"{v:.1f}s" if isinstance(v, (int, float)) else "-"
    chars = sum(len(f) for f in res.frases)
    print(f"[perf] rapido primeira_frase={seg(res.primeira_frase)} total={seg(res.total)} "
          f"escalou={res.motivo or 'nao'} frases={len(res.frases)} chars={chars}", flush=True)


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
