"""Modo conversa: tutor de idiomas, simulação de entrevista e qualquer conversa guiada, por voz.

O agente completo ativa o modo com a ferramenta iniciar_modo_conversa. Depois disso, as falas daquela
conexão do celular vão direto ao modelo (API de mensagens, sem ferramentas e sem o _lock do agente),
e a resposta sai frase por frase. O modelo encerra respondendo [[FIM]] (ou [[FIM]] [[OUTRO]] quando o
pedido é alheio à prática); o servidor pede então o feedback final e volta ao modo normal.

Nunca registrar o texto das falas, das respostas nem chaves: só tempos e contagens.
"""
import asyncio
import os
import re
import time
from dataclasses import dataclass, field

from claude_agent_sdk import tool, create_sdk_mcp_server

from . import perfil
from .toolkit import ok, err

MODEL = os.getenv("CONVERSA_MODEL", "claude-haiku-4-5-20251001")
MAX_TOKENS = int(os.getenv("CONVERSA_MAX_TOKENS", "250"))
MAX_TOKENS_FEEDBACK = int(os.getenv("CONVERSA_MAX_TOKENS_FEEDBACK", "500"))
TIMEOUT_S = float(os.getenv("CONVERSA_TIMEOUT_S", "15"))

MARCA_FIM = "[[FIM]]"
MARCA_OUTRO = "[[OUTRO]]"
NIVEIS = ("iniciante", "intermediário", "avançado")
ABERTURA = "[início da sessão] Comece a conversa agora, no seu papel, com uma fala curta."
PEDIDO_FEEDBACK = "[fim da sessão] Dê agora o feedback final, como combinado."


# ---------- divisor de frases (streaming) ----------

LIMITE_FRASE = 200
_ABREV = {"mr", "mrs", "ms", "dr", "drs", "prof", "sr", "sra", "srta", "st", "jr", "vs",
          "e.g", "i.e", "p.ex", "mme", "mlle", "hr", "fr", "z.b", "bzw", "sto", "sta", "av"}
_FECHA = "\"')]}»”’」』"
_ABRE = "¿¡\"“«‘(「『"
_FIM_CJK = "。！？"
_PALAVRA = re.compile(r"([^\W\d_][\w.]*)$")


def _fecha(buf: str, j: int) -> int:
    while j < len(buf) and buf[j] in _FECHA:
        j += 1
    return j


def _fim_da_frase(buf: str, final: bool) -> int | None:
    """Índice logo depois da primeira frase completa de buf, ou None se ainda não dá para saber."""
    n = len(buf)
    i = 0
    while i < n:
        c = buf[i]
        if c == "\n":
            return i + 1
        if c in _FIM_CJK:
            j = _fecha(buf, i + 1)
            while j < n and buf[j] in _FIM_CJK:
                j = _fecha(buf, j + 1)
            return j if (j < n or final) else None
        if c in "!?;":
            j = i + 1
            while j < n and buf[j] in "!?":
                j += 1
            j = _fecha(buf, j)
            return j if (j < n or final) else None
        if c == "…" or buf.startswith("...", i):
            k = i + 1 if c == "…" else i + 3
            while k < n and buf[k] in ".…":
                k += 1
            k = _fecha(buf, k)
            m = k
            while m < n and buf[m].isspace():
                m += 1
            if m >= n:
                if final:
                    return n
                return None
            if m > k and (buf[m].isupper() or buf[m] in _ABRE):
                return k
            i = k
            continue
        if c == ".":
            if i > 0 and buf[i - 1].isdigit():
                if i + 1 >= n and not final:
                    return None
                if i + 1 < n and buf[i + 1].isdigit():
                    i += 1
                    continue
            palavra = _PALAVRA.search(buf[:i])
            if palavra and palavra.group(1).lower() in _ABREV:
                i += 1
                continue
            j = _fecha(buf, i + 1)
            if j >= n:
                return n if final else None
            if buf[j].isspace():
                return j
            i = j
            continue
        i += 1
    return n if (final and buf.strip()) else None


def _corte_longo(buf: str) -> int:
    """Frase longa sem pontuação: corta na vírgula mais próxima do limite (ou no último espaço)."""
    antes = buf.rfind(",", 0, LIMITE_FRASE)
    if antes > 0:
        return antes + 1
    depois = buf.find(",", LIMITE_FRASE)
    if depois > 0:
        return depois + 1
    espaco = buf.rfind(" ", 0, LIMITE_FRASE)
    return espaco + 1 if espaco > 0 else LIMITE_FRASE


class DivisorFrases:
    """Recebe pedaços do streaming e devolve frases completas assim que fecham."""

    def __init__(self):
        self._buf = ""

    def _extrair(self, final: bool) -> list[str]:
        frases = []
        while self._buf:
            j = _fim_da_frase(self._buf, final)
            if j is None:
                if len(self._buf) > LIMITE_FRASE:
                    j = _corte_longo(self._buf)
                else:
                    break
            frase, self._buf = self._buf[:j].strip(), self._buf[j:]
            if frase:
                frases.append(frase)
            if not final:
                self._buf = self._buf.lstrip(" \t")
        return frases

    def feed(self, pedaco: str) -> list[str]:
        self._buf += pedaco
        return self._extrair(final=False)

    def flush(self) -> list[str]:
        frases = self._extrair(final=True)
        self._buf = ""
        return frases


def dividir(texto: str) -> list[str]:
    d = DivisorFrases()
    return d.feed(texto) + d.flush()


# ---------- marcador [[FIM]] (pode chegar quebrado entre pedaços) ----------

class MarcadorFim:
    """Filtra o texto do streaming. Segura o pedaço que pode ser o começo de [[FIM]]."""

    def __init__(self):
        self._pendente = ""
        self.fim = False
        self.resto = ""

    def feed(self, pedaco: str) -> str:
        if self.fim:
            self.resto += pedaco
            return ""
        buf = self._pendente + pedaco
        i = buf.find(MARCA_FIM)
        if i >= 0:
            self.fim = True
            self.resto = buf[i + len(MARCA_FIM):]
            self._pendente = ""
            return buf[:i]
        k = next((t for t in range(min(len(buf), len(MARCA_FIM) - 1), 0, -1) if MARCA_FIM.startswith(buf[-t:])), 0)
        self._pendente = buf[len(buf) - k:] if k else ""
        return buf[:len(buf) - k] if k else buf

    def flush(self) -> str:
        p, self._pendente = self._pendente, ""
        return p

    @property
    def outro(self) -> bool:
        return MARCA_OUTRO in "".join(self.resto.split())


# ---------- vozes (edge-tts) ----------

_VOZES: list[dict] | None = None


async def vozes() -> list[dict]:
    """Lista de vozes do edge-tts, consultada uma vez e guardada em memória."""
    global _VOZES
    if _VOZES is None:
        import edge_tts
        _VOZES = await edge_tts.list_voices()
    return _VOZES


async def precarregar_vozes() -> None:
    """Na subida do servidor, em segundo plano: a primeira ativação do modo não espera a rede."""
    try:
        lista = await vozes()
    except Exception as e:
        print(f"[conversa] lista de vozes indisponível na subida ({type(e).__name__})", flush=True)
        return
    print(f"[conversa] lista de vozes carregada vozes={len(lista)}", flush=True)


def definir_vozes(lista: list[dict] | None) -> None:
    global _VOZES
    _VOZES = lista


def escolher_voz(lista: list[dict], bcp47: str) -> str | None:
    """Voz do Locale pedido: Neural masculina, senão qualquer Neural, senão a primeira. Sem região, vale o idioma."""
    alvo = (bcp47 or "").strip().lower()
    if not alvo:
        return None
    mesmas = [v for v in lista if str(v.get("Locale", "")).lower() == alvo]
    if not mesmas and "-" not in alvo:
        mesmas = [v for v in lista if str(v.get("Locale", "")).lower().split("-")[0] == alvo]
    if not mesmas:
        return None
    neural = [v for v in mesmas if "neural" in str(v.get("ShortName", "")).lower()]
    masc = [v for v in neural if str(v.get("Gender", "")).lower() == "male"]
    return str((masc or neural or mesmas)[0].get("ShortName"))


async def voz_valida(nome: str) -> bool:
    try:
        return any(v.get("ShortName") == nome for v in await vozes())
    except Exception:
        return False


# ---------- uso (por sessão e total desde que o servidor subiu) ----------

_CAMPOS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
USO_TOTAL = {"desde": time.time(), "sessoes": 0, "turnos": 0, "minutos": 0.0, **{c: 0 for c in _CAMPOS}}


def _somar_uso(destino: dict, usage) -> None:
    for c in _CAMPOS:
        valor = getattr(usage, c, None) if usage is not None else None
        if isinstance(valor, int):
            destino[c] = destino.get(c, 0) + valor


def uso_total(ativas: int = 0) -> dict:
    return {**USO_TOTAL, "minutos": round(USO_TOTAL["minutos"], 2), "ativas": ativas, "modelo": MODEL}


# ---------- sessão ----------

@dataclass
class Sessao:
    idioma_alvo: str
    bcp47: str
    voz: str
    idioma_aluno: str = "pt-BR"
    nivel: str = "intermediário"
    cenario: str = "conversa livre"
    papel: str = "parceiro de conversa"
    correcao: str = "final"
    historico: list = field(default_factory=list)
    turnos: int = 0
    uso: dict = field(default_factory=lambda: {c: 0 for c in _CAMPOS})
    inicio: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    fechada: bool = False

    def contar(self, usage) -> None:
        _somar_uso(self.uso, usage)
        _somar_uso(USO_TOTAL, usage)

    def minutos(self) -> float:
        return (time.monotonic() - self.inicio) / 60


def prompt_sistema(s: Sessao, p: dict | None = None) -> str:
    p = p or perfil.carregar()
    nome = f" O aluno se chama {p['nome_usuario']}." if p.get("nome_usuario") else ""
    return (
        f"Você é {p['nome_tutor']}, parceiro de conversa por voz para prática de idiomas e simulações.{nome}\n"
        f"Idioma da prática: {s.idioma_alvo} ({s.bcp47}). Idioma nativo do aluno: {s.idioma_aluno}. Nível: {s.nivel}.\n"
        f"Cenário: {s.cenario}. Seu papel: {s.papel}.\n\n"
        "Como falar:\n"
        f"- Responda sempre em {s.idioma_alvo}.\n"
        "- De 1 a 3 frases curtas por vez, naturais para serem ditas em voz alta.\n"
        "- Sem markdown, listas, emojis, símbolos ou abreviações difíceis de ler em voz alta.\n"
        "- Termine sempre com algo que mantenha o diálogo: uma pergunta ou uma deixa.\n"
        f"- Adapte o vocabulário e a complexidade ao nível {s.nivel}.\n"
        "- No papel do cenário, seja realista (por exemplo, um recrutador exigente, mas educado) e não saia do personagem.\n"
        f"- Se o aluno falar em {s.idioma_aluno} no meio da conversa, dê uma ajuda curta em {s.idioma_aluno} "
        f"e retome em {s.idioma_alvo}.\n\n"
        "Correção:\n"
        f"- Modo inicial: {'imediata' if s.correcao == 'imediata' else 'final'}.\n"
        "- final: NÃO interrompa nem corrija durante a conversa. Anote mentalmente os erros para o feedback final.\n"
        "- imediata: corrija cada erro em uma frase curta e siga a conversa.\n"
        "- Se o aluno pedir para ser corrigido na hora, passe para imediata; se pedir correção só no final, volte "
        "para final. Vale até ele pedir outra coisa.\n\n"
        "Encerramento:\n"
        f"- Se o aluno quiser parar a prática, do jeito que disser, responda apenas {MARCA_FIM}.\n"
        "- Se ele pedir algo claramente alheio à prática (agenda, lembrete, alarme, computador, e-mail etc.), "
        f"responda apenas {MARCA_FIM} {MARCA_OUTRO}.\n"
        f"- Nunca escreva {MARCA_FIM} em outra situação."
    )


def prompt_feedback(s: Sessao, p: dict | None = None) -> str:
    return (
        prompt_sistema(s, p) + "\n\n"
        f"A prática terminou. Agora fale com o aluno em {s.idioma_aluno}, como feedback final falado: "
        "de 4 a 6 frases curtas, sem markdown, listas, emojis ou símbolos. Diga os principais erros que ele cometeu "
        "(com a forma certa, em poucas palavras), o que ele fez bem e 2 sugestões práticas para a próxima vez. "
        "Não faça pergunta no final."
    )


# ---------- pedido de ativação (ferramenta do agente) ----------

_PEDIDO: dict | None = None
_BCP47 = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


def _nivel(valor: str) -> str:
    v = (valor or "").strip().lower()
    if v.startswith("inic") or v.startswith("básic") or v.startswith("basic"):
        return "iniciante"
    if v.startswith("avan"):
        return "avançado"
    return "intermediário"


async def preparar(a: dict) -> dict:
    """Valida os parâmetros, escolhe a voz e deixa o pedido pronto para o servidor ativar."""
    global _PEDIDO
    p = perfil.carregar()
    idioma = str(a.get("idioma_alvo") or "").strip()
    bcp47 = str(a.get("idioma_bcp47") or "").strip()
    if not idioma or not _BCP47.match(bcp47):
        raise ValueError("Informe idioma_alvo e idioma_bcp47 válido (ex.: en-US, fr-FR, ja-JP).")
    try:
        voz = escolher_voz(await vozes(), bcp47)
    except Exception:
        raise ValueError("Não consegui consultar as vozes agora. O modo conversa não foi ativado.")
    if not voz:
        raise ValueError(f"Não há voz disponível para {idioma}. O modo conversa não foi ativado.")
    pedido = {
        "idioma_alvo": idioma, "bcp47": bcp47, "voz": voz,
        "idioma_aluno": str(a.get("idioma_aluno") or p["idioma_nativo"]).strip(),
        "nivel": _nivel(str(a.get("nivel") or "")),
        "cenario": str(a.get("cenario") or "conversa livre").strip()[:300],
        "papel": str(a.get("papel") or "parceiro de conversa").strip()[:200],
        "correcao": "imediata" if str(a.get("correcao") or "").strip().lower().startswith("imed") else "final",
    }
    _PEDIDO = {**pedido, "criado": time.monotonic()}
    return pedido


def tomar_pedido(max_idade: float = 120) -> dict | None:
    """Entrega (uma vez) o pedido feito durante a resposta atual do agente."""
    global _PEDIDO
    pedido, _PEDIDO = _PEDIDO, None
    if not pedido or time.monotonic() - pedido.pop("criado", 0) > max_idade:
        return None
    return pedido


def criar_sessao(pedido: dict) -> Sessao:
    return Sessao(**pedido)


@tool("iniciar_modo_conversa",
      "Inicia o modo conversa por voz no app do celular: um tutor ou parceiro que conversa em tempo real, frase a "
      "frase, sem passar pelas outras ferramentas. Use SEMPRE que o usuário pedir, de qualquer jeito, para praticar, "
      "treinar ou conversar em QUALQUER idioma (não só inglês), ou para simular uma situação: entrevista de emprego, "
      "negociação, debate, apresentação, atendimento ou qualquer conversa guiada. Interprete a intenção, não "
      "palavras exatas. Preencha o que o usuário disser e assuma o resto: nivel intermediário; correcao 'final' "
      "(corrigir só no fim), a não ser que ele peça correção na hora ('imediata'); idioma_aluno pt-BR. Simulação em "
      "português: idioma_alvo português, idioma_bcp47 pt-BR. Se a ferramenta devolver erro, diga o motivo ao usuário.",
      {"type": "object",
       "properties": {
           "idioma_alvo": {"type": "string", "description": "nome do idioma da prática, em português (ex.: inglês, francês, japonês)"},
           "idioma_bcp47": {"type": "string", "description": "código BCP 47 do idioma da prática (ex.: en-US, fr-FR, de-DE, ja-JP, es-ES)"},
           "idioma_aluno": {"type": "string", "description": "idioma em que o tutor explica; padrão pt-BR"},
           "nivel": {"type": "string", "description": "iniciante | intermediário | avançado; padrão intermediário"},
           "cenario": {"type": "string", "description": "texto livre: 'conversa livre', 'entrevista para vaga de product designer sênior'..."},
           "papel": {"type": "string", "description": "papel do tutor no cenário, texto livre (ex.: recrutador)"},
           "correcao": {"type": "string", "description": "final (padrão: corrige só no fim) | imediata (corrige na hora)"},
       },
       "required": ["idioma_alvo", "idioma_bcp47"]})
async def iniciar_modo_conversa(a):
    try:
        pedido = await preparar(a)
    except ValueError as e:
        return err(str(e))
    return ok(f"Modo conversa pronto ({pedido['idioma_alvo']}, nível {pedido['nivel']}). Ele começa sozinho no app do "
              "celular assim que esta resposta terminar, e o tutor abre a conversa. Responda só com uma frase curta "
              "em português, como 'Vamos lá.'. Funciona apenas no app do celular.")


conversa_server = create_sdk_mcp_server(name="conversa", version="1.0.0", tools=[iniciar_modo_conversa])


# ---------- chamadas ao modelo ----------

_CLIENTE = None


def cliente():
    """Cliente da API de mensagens. A chave vem de ANTHROPIC_API_KEY, a mesma do agente."""
    global _CLIENTE
    if _CLIENTE is None:
        import anthropic
        _CLIENTE = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY") or None, max_retries=1)
    return _CLIENTE


def definir_cliente(c) -> None:
    global _CLIENTE
    _CLIENTE = c


def _sistema(texto: str) -> list[dict]:
    return [{"type": "text", "text": texto, "cache_control": {"type": "ephemeral"}}]


@dataclass
class Fala:
    """Resultado de um streaming de fala: as frases enviadas, os tempos e a ferramenta chamada (se houve)."""
    faladas: list[str] = field(default_factory=list)
    tempos: dict = field(default_factory=dict)
    ferramenta: str | None = None
    ferramenta_entrada: dict = field(default_factory=dict)


def _ferramenta_chamada(final) -> tuple[str | None, dict]:
    """Ferramenta (tool_use) pedida na mensagem final: blocos tool_use ou stop_reason == "tool_use"."""
    for bloco in getattr(final, "content", None) or []:
        if getattr(bloco, "type", None) == "tool_use":
            entrada = getattr(bloco, "input", None)
            return str(getattr(bloco, "name", "") or ""), entrada if isinstance(entrada, dict) else {}
    if getattr(final, "stop_reason", None) == "tool_use":
        return "", {}
    return None, {}


async def falar_stream(*, modelo: str, sistema, mensagens: list, max_tokens: int, idioma: str, voz: str, enviar,
                       marcador: MarcadorFim | None = None, contar=None, timeout: float = TIMEOUT_S,
                       ferramentas: list | None = None) -> Fala:
    """Streaming do modelo para frases, sem depender de Sessao. `contar(usage)` recebe o uso da resposta.
    Se o modelo pedir uma ferramenta, o texto que ele ja escreveu e enviado e `Fala.ferramenta` diz qual
    (a ferramenta nunca e executada aqui). Se a chamada falhar, a excecao sobe; as frases ja enviadas ficam
    com quem passou `enviar`."""
    t0 = time.perf_counter()
    tempos = {"token": None, "frase": None}
    divisor = DivisorFrases()
    faladas: list[str] = []

    async def emitir(frases):
        for f in frases:
            if tempos["frase"] is None:
                tempos["frase"] = time.perf_counter() - t0
            faladas.append(f)
            await enviar({"type": "frase", "text": f, "idioma": idioma, "voz": voz})

    extra = {"tools": ferramentas} if ferramentas else {}
    async with asyncio.timeout(timeout):
        async with cliente().messages.stream(model=modelo, max_tokens=max_tokens,
                                             system=sistema if isinstance(sistema, list) else _sistema(sistema),
                                             messages=mensagens, **extra) as stream:
            async for pedaco in stream.text_stream:
                if tempos["token"] is None:
                    tempos["token"] = time.perf_counter() - t0
                if marcador is not None:
                    if marcador.fim:
                        marcador.feed(pedaco)
                        continue
                    pedaco = marcador.feed(pedaco)
                await emitir(divisor.feed(pedaco))
            final = await stream.get_final_message()
    if contar is not None:
        contar(getattr(final, "usage", None))
    if marcador is not None and not marcador.fim:
        await emitir(divisor.feed(marcador.flush()))
    await emitir(divisor.flush())
    tempos["total"] = time.perf_counter() - t0
    nome, entrada = _ferramenta_chamada(final) if ferramentas else (None, {})
    return Fala(faladas=faladas, tempos=tempos, ferramenta=nome, ferramenta_entrada=entrada)


async def _falar(sessao: Sessao, sistema: str, mensagens: list, max_tokens: int, idioma: str, voz: str,
                 enviar, marcador: MarcadorFim | None) -> tuple[list[str], dict]:
    """Streaming do modelo do tutor. Devolve as frases enviadas e os tempos."""
    fala = await falar_stream(modelo=MODEL, sistema=sistema, mensagens=mensagens, max_tokens=max_tokens,
                              idioma=idioma, voz=voz, enviar=enviar, marcador=marcador, contar=sessao.contar,
                              timeout=TIMEOUT_S)
    return fala.faladas, fala.tempos


def _perf(rotulo: str, tempos: dict, frases: int) -> None:
    def fmt(v):
        return f"+{v:.2f}s" if isinstance(v, (int, float)) else "-"
    print(f"[perf] {time.strftime('%H:%M:%S')} conversa {rotulo} primeiro token {fmt(tempos.get('token'))} "
          f"primeira frase {fmt(tempos.get('frase'))} total {fmt(tempos.get('total'))} frases={frases}", flush=True)


async def turno(sessao: Sessao, texto: str | None, enviar) -> dict:
    """Uma fala do aluno (ou a abertura, com texto None). Devolve {"fim": bool, "outro": bool}."""
    async with sessao.lock:
        fala = texto if texto is not None else ABERTURA
        mensagens = sessao.historico + [{"role": "user", "content": fala}]
        marcador = MarcadorFim()
        faladas, tempos = await _falar(sessao, prompt_sistema(sessao), mensagens, MAX_TOKENS,
                                       sessao.bcp47, sessao.voz, enviar, marcador)
        _perf("turno", tempos, len(faladas))
        if marcador.fim:
            return {"fim": True, "outro": marcador.outro}
        sessao.historico = mensagens + [{"role": "assistant", "content": " ".join(faladas) or "..."}]
        sessao.turnos += 1
        USO_TOTAL["turnos"] += 1
        await enviar({"type": "done", "conversa": True})
        return {"fim": False, "outro": False}


async def feedback(sessao: Sessao, ultima_fala: str, enviar, voz: str, encaminhado: bool) -> None:
    """Feedback final falado no idioma do aluno, depois do [[FIM]]."""
    async with sessao.lock:
        mensagens = sessao.historico + [
            {"role": "user", "content": ultima_fala},
            {"role": "assistant", "content": MARCA_FIM},
            {"role": "user", "content": PEDIDO_FEEDBACK},
        ]
        faladas, tempos = await _falar(sessao, prompt_feedback(sessao), mensagens, MAX_TOKENS_FEEDBACK,
                                       sessao.idioma_aluno, voz, enviar, None)
        _perf("feedback", tempos, len(faladas))
        await enviar({"type": "done", "conversa": True, "encaminhado": encaminhado})


def fechar(sessao: Sessao, motivo: str) -> None:
    """Fecha a contagem da sessão e registra o [uso]. Sem texto da conversa."""
    if sessao.fechada:
        return
    sessao.fechada = True
    minutos = sessao.minutos()
    USO_TOTAL["sessoes"] += 1
    USO_TOTAL["minutos"] += minutos
    u = sessao.uso
    print(f"[uso] conversa encerrada motivo={motivo} idioma={sessao.bcp47} turnos={sessao.turnos} "
          f"minutos={minutos:.1f} entrada={u['input_tokens']} saida={u['output_tokens']} "
          f"cache_criacao={u['cache_creation_input_tokens']} cache_leitura={u['cache_read_input_tokens']} "
          f"modelo={MODEL}", flush=True)
