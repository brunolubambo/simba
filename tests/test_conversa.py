"""Modo conversa: divisor de frases, marcador [[FIM]], voz por idioma, roteamento do ws, uso e /tts.

Sem rede: o cliente da API e a lista de vozes são simulados. Valores falsos de propósito.
"""
import asyncio
import importlib
import importlib.machinery
import importlib.util
import contextlib
import io
import os
import sys
import types
import unittest
from pathlib import Path

os.environ["SIMBA_TOKEN"] = "token-de-teste-123"
os.environ["SIMBA_TOKEN_ANTERIOR"] = ""
os.environ["CELULAR_TOKEN"] = ""
os.environ["PC_TOKEN"] = "p" * 40

RAIZ = Path(__file__).resolve().parents[1]
TOKEN = "token-de-teste-123"


def _carregar(nome):
    if "simba" not in sys.modules:
        spec = importlib.machinery.ModuleSpec("simba", loader=None, is_package=True)
        pacote = importlib.util.module_from_spec(spec)
        pacote.__path__ = [str(RAIZ)]
        pacote.__package__ = "simba"
        sys.modules["simba"] = pacote
    return importlib.import_module(nome)


server = _carregar("simba.server")
conversa = _carregar("simba.conversa")

VOZES = [
    {"ShortName": "pt-BR-AntonioNeural", "Locale": "pt-BR", "Gender": "Male"},
    {"ShortName": "pt-BR-FranciscaNeural", "Locale": "pt-BR", "Gender": "Female"},
    {"ShortName": "fr-FR-DeniseNeural", "Locale": "fr-FR", "Gender": "Female"},
    {"ShortName": "fr-FR-HenriNeural", "Locale": "fr-FR", "Gender": "Male"},
    {"ShortName": "en-US-AriaNeural", "Locale": "en-US", "Gender": "Female"},
    {"ShortName": "ja-JP-NanamiNeural", "Locale": "ja-JP", "Gender": "Female"},
]


# ---------- divisor de frases ----------

class Divisor(unittest.TestCase):
    def test_frases_simples(self):
        self.assertEqual(conversa.dividir("Hello there. How are you? Great!"),
                         ["Hello there.", "How are you?", "Great!"])

    def test_abreviacoes_nao_cortam(self):
        self.assertEqual(conversa.dividir("Mr. Smith met Dr. Jones. Then they left."),
                         ["Mr. Smith met Dr. Jones.", "Then they left."])
        self.assertEqual(conversa.dividir("Use verbs, e.g. run and jump. Okay?"),
                         ["Use verbs, e.g. run and jump.", "Okay?"])

    def test_decimais_nao_cortam(self):
        self.assertEqual(conversa.dividir("It costs 3.5 dollars. Cheap."), ["It costs 3.5 dollars.", "Cheap."])

    def test_reticencias_no_meio_nao_cortam(self):
        self.assertEqual(conversa.dividir("Well... maybe tomorrow. Sure."), ["Well... maybe tomorrow.", "Sure."])
        self.assertEqual(conversa.dividir("Hmm… je pense que oui. Et toi?"), ["Hmm… je pense que oui.", "Et toi?"])

    def test_pontuacao_cjk_e_espanhola(self):
        self.assertEqual(conversa.dividir("こんにちは。元気ですか？はい！"), ["こんにちは。", "元気ですか？", "はい！"])
        self.assertEqual(conversa.dividir("Hola. ¿Cómo estás? ¡Qué bien!"), ["Hola.", "¿Cómo estás?", "¡Qué bien!"])

    def test_quebra_de_linha_e_ponto_e_virgula(self):
        self.assertEqual(conversa.dividir("primeira linha\nsegunda; terceira"),
                         ["primeira linha", "segunda;", "terceira"])

    def test_frase_longa_sem_pontuacao_corta_na_virgula(self):
        texto = ("palavra " * 20).strip() + ", " + ("outra " * 30).strip()
        frases = conversa.dividir(texto)
        self.assertGreater(len(frases), 1)
        self.assertTrue(frases[0].endswith(","))
        self.assertTrue(all(len(f) <= conversa.LIMITE_FRASE + 20 for f in frases[:-1]))
        self.assertEqual(" ".join(frases).replace(" ,", ","), texto)

    def test_streaming_entrega_frase_assim_que_fecha(self):
        d = conversa.DivisorFrases()
        self.assertEqual(d.feed("Bonjour"), [])
        self.assertEqual(d.feed(" Bruno. Comment"), ["Bonjour Bruno."])
        self.assertEqual(d.feed(" ça va"), [])
        self.assertEqual(d.feed("? Moi"), ["Comment ça va?"])
        self.assertEqual(d.flush(), ["Moi"])

    def test_decimal_quebrado_entre_pedacos(self):
        d = conversa.DivisorFrases()
        self.assertEqual(d.feed("Pi is 3."), [])
        self.assertEqual(d.feed("14 roughly. Ok"), ["Pi is 3.14 roughly."])


# ---------- marcador [[FIM]] ----------

class Marcador(unittest.TestCase):
    def _passar(self, pedacos):
        m = conversa.MarcadorFim()
        saida = "".join(m.feed(p) for p in pedacos)
        if not m.fim:
            saida += m.flush()
        return m, saida

    def test_marcador_inteiro(self):
        m, saida = self._passar(["[[FIM]]"])
        self.assertTrue(m.fim)
        self.assertEqual(saida, "")

    def test_marcador_quebrado_em_varios_pedacos(self):
        for pedacos in (["[[", "FIM]]"], ["[", "[F", "I", "M]", "]"], ["[[FI", "M]] [[OUT", "RO]]"]):
            m, saida = self._passar(pedacos)
            self.assertTrue(m.fim, pedacos)
            self.assertEqual(saida.strip(), "")
        self.assertTrue(self._passar(["[[FI", "M]] [[OUT", "RO]]"])[0].outro)
        self.assertFalse(self._passar(["[[", "FIM]]"])[0].outro)

    def test_texto_normal_passa_inteiro(self):
        m, saida = self._passar(["Very [", "good [[x]] ", "indeed["])
        self.assertFalse(m.fim)
        self.assertEqual(saida, "Very [good [[x]] indeed[")


# ---------- voz por idioma ----------

class Vozes(unittest.TestCase):
    def test_prefere_neural_masculina(self):
        self.assertEqual(conversa.escolher_voz(VOZES, "fr-FR"), "fr-FR-HenriNeural")
        self.assertEqual(conversa.escolher_voz(VOZES, "pt-br"), "pt-BR-AntonioNeural")

    def test_sem_masculina_usa_a_primeira_neural(self):
        self.assertEqual(conversa.escolher_voz(VOZES, "ja-JP"), "ja-JP-NanamiNeural")

    def test_idioma_sem_voz(self):
        self.assertIsNone(conversa.escolher_voz(VOZES, "sw-KE"))
        self.assertIsNone(conversa.escolher_voz(VOZES, ""))

    def test_ferramenta_recusa_idioma_sem_voz(self):
        conversa.definir_vozes(VOZES)
        r = asyncio.run(conversa.iniciar_modo_conversa.handler({"idioma_alvo": "suaíli", "idioma_bcp47": "sw-KE"}))
        self.assertTrue(r.get("is_error"))
        self.assertIn("Não há voz disponível para suaíli", r["content"][0]["text"])
        self.assertIsNone(conversa.tomar_pedido())

    def test_ferramenta_assume_padroes(self):
        conversa.definir_vozes(VOZES)
        asyncio.run(conversa.iniciar_modo_conversa.handler({"idioma_alvo": "inglês", "idioma_bcp47": "en-US"}))
        p = conversa.tomar_pedido()
        self.assertEqual((p["nivel"], p["correcao"], p["idioma_aluno"], p["voz"]),
                         ("intermediário", "final", "pt-BR", "en-US-AriaNeural"))
        self.assertIsNone(conversa.tomar_pedido())


# ---------- cliente da API simulado ----------

class _Fluxo:
    def __init__(self, pedacos, demora=0.0):
        self.pedacos, self.demora = pedacos, demora

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    @property
    def text_stream(self):
        async def gerar():
            for p in self.pedacos:
                if self.demora:
                    await asyncio.sleep(self.demora)
                yield p
        return gerar()

    async def get_final_message(self):
        return types.SimpleNamespace(stop_reason="end_turn", usage=types.SimpleNamespace(
            input_tokens=100, output_tokens=20, cache_creation_input_tokens=0, cache_read_input_tokens=80))


class ClienteFalso:
    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.chamadas = []
        self.messages = self

    def stream(self, **kw):
        self.chamadas.append(kw)
        item = self.roteiro.pop(0)
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, _Fluxo) else _Fluxo(item)


class SimbaFalso:
    def __init__(self):
        self.recebidos = []

    async def ask(self, text):
        self.recebidos.append(text)
        if "praticar" in text:
            await conversa.iniciar_modo_conversa.handler({"idioma_alvo": "francês", "idioma_bcp47": "fr-FR"})
            yield {"type": "text", "text": "Vamos lá."}
        else:
            yield {"type": "text", "text": "ok"}
        yield {"type": "done", "cost_usd": 0}


def _ate(ws, condicao, limite=40):
    eventos = []
    for _ in range(limite):
        ev = ws.receive_json()
        eventos.append(ev)
        if condicao(ev):
            return eventos
    raise AssertionError(f"evento esperado não chegou: {[e.get('type') for e in eventos]}")


def _fim_conversa(ev):
    return ev.get("type") == "done" and ev.get("conversa")


class Roteamento(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        self.antes = dict(server.state)
        self.simba = SimbaFalso()
        server.state["simba"] = self.simba
        server.state["observer"] = types.SimpleNamespace(enabled=False, available=False)
        server.CONVERSAS.clear()
        conversa.definir_vozes(VOZES)
        conversa.tomar_pedido()
        self.cliente_http = TestClient(server.app)
        self.saida = io.StringIO()
        self._log = contextlib.redirect_stdout(self.saida)
        self._log.__enter__()

    def tearDown(self):
        self._log.__exit__(None, None, None)
        conversa.definir_cliente(None)
        server.CONVERSAS.clear()
        server.state.clear()
        server.state.update(self.antes)

    def _ws(self, recursos="conversa"):
        return self.cliente_http.websocket_connect(f"/ws?token={TOKEN}&device=celular&recursos={recursos}")

    def _ativar(self, ws):
        ws.send_json({"type": "message", "text": "quero praticar francês", "voice": True, "t": 1})
        eventos = _ate(ws, _fim_conversa)
        tipos = [e["type"] for e in eventos]
        modo = next(e for e in eventos if e["type"] == "modo")
        self.assertEqual(modo, {"type": "modo", "ativo": True, "stt": "fr-FR", "voz": "fr-FR-HenriNeural", "idioma": "francês"})
        self.assertLess(tipos.index("modo"), tipos.index("done"))
        return eventos

    def test_sessao_ativa_vai_pelo_caminho_rapido(self):
        api = ClienteFalso([["Bonjour ! Comment", " ça va ?"], ["Très bien. Et", " toi ?"]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            eventos = self._ativar(ws)
            frases = [e for e in eventos if e["type"] == "frase"]
            self.assertEqual([f["text"] for f in frases], ["Bonjour !", "Comment ça va ?"])
            self.assertEqual({(f["idioma"], f["voz"]) for f in frases}, {("fr-FR", "fr-FR-HenriNeural")})
            self.assertEqual(len(self.simba.recebidos), 1)

            ws.send_json({"type": "message", "text": "Ça va bien", "voice": True, "t": 2})
            eventos = _ate(ws, _fim_conversa)
            self.assertEqual(eventos[0], {"type": "ack", "t": 2})
            self.assertEqual([e["text"] for e in eventos if e["type"] == "frase"], ["Très bien.", "Et toi ?"])
            self.assertEqual(len(self.simba.recebidos), 1, "o agente completo não pode ser chamado no modo conversa")

        chamada = api.chamadas[1]
        self.assertEqual(chamada["model"], conversa.MODEL)
        self.assertEqual(chamada["max_tokens"], conversa.MAX_TOKENS)
        self.assertNotIn("tools", chamada)
        self.assertEqual(chamada["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(chamada["messages"][-1], {"role": "user", "content": "Ça va bien"})
        self.assertEqual(chamada["messages"][-2]["role"], "assistant")
        log = self.saida.getvalue()
        self.assertIn("conversa turno primeiro token", log)
        self.assertIn("[uso] conversa encerrada motivo=desconectou", log)
        self.assertNotIn("Ça va", log)
        self.assertNotIn("Bonjour", log)

    def test_fim_quebrado_da_feedback_e_volta_ao_normal(self):
        api = ClienteFalso([["Salut ! Tu vas bien ?"], ["[[FI", "M]]"], ["Você foi bem. Treine o passado."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._ativar(ws)
            ws.send_json({"type": "message", "text": "chega por hoje", "t": 3})
            eventos = _ate(ws, _fim_conversa)
            tipos = [e["type"] for e in eventos]
            modo = next(e for e in eventos if e["type"] == "modo")
            self.assertEqual(modo["ativo"], False)
            self.assertEqual(modo["stt"], "pt-BR")
            self.assertEqual(modo["voz"], server.VOICE)
            frases = [e for e in eventos if e["type"] == "frase"]
            self.assertLess(tipos.index("modo"), tipos.index("frase"))
            self.assertEqual([f["text"] for f in frases], ["Você foi bem.", "Treine o passado."])
            self.assertEqual({(f["idioma"], f["voz"]) for f in frases}, {("pt-BR", server.VOICE)})
            self.assertFalse(eventos[-1]["encaminhado"])
            self.assertNotIn("[[", " ".join(f["text"] for f in frases))
            self.assertEqual(api.chamadas[2]["max_tokens"], conversa.MAX_TOKENS_FEEDBACK)

            ws.send_json({"type": "message", "text": "que horas são", "voice": True, "t": 4})
            _ate(ws, lambda e: e.get("type") == "done" and not e.get("conversa"))
            self.assertEqual(len(self.simba.recebidos), 2)
            self.assertFalse(server.CONVERSAS)
        self.assertIn("[uso] conversa encerrada motivo=fim", self.saida.getvalue())

    def test_pedido_alheio_vai_ao_agente_depois_do_feedback(self):
        api = ClienteFalso([["Salut !"], ["[[FIM]] [[OUT", "RO]]"], ["Bom treino."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._ativar(ws)
            ws.send_json({"type": "message", "text": "me lembra amanhã de ligar", "t": 5})
            eventos = _ate(ws, _fim_conversa)
            self.assertTrue(eventos[-1]["encaminhado"])
            _ate(ws, lambda e: e.get("type") == "done" and not e.get("conversa"))
        self.assertEqual(len(self.simba.recebidos), 2)
        self.assertTrue(self.simba.recebidos[1].endswith("me lembra amanhã de ligar"))

    def test_falha_do_modelo_volta_ao_normal(self):
        api = ClienteFalso([["Salut !"], RuntimeError("falha simulada")])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._ativar(ws)
            ws.send_json({"type": "message", "text": "bonjour", "t": 6})
            eventos = _ate(ws, _fim_conversa)
            self.assertFalse(next(e for e in eventos if e["type"] == "modo")["ativo"])
            self.assertIn("voltei ao modo normal", next(e for e in eventos if e["type"] == "frase")["text"])
            self.assertFalse(server.CONVERSAS)

    def test_tempo_estourado_volta_ao_normal(self):
        api = ClienteFalso([["Salut !"], _Fluxo(["lento"], demora=1.0)])
        conversa.definir_cliente(api)
        antes = conversa.TIMEOUT_S
        conversa.TIMEOUT_S = 0.2
        try:
            with self._ws() as ws:
                self._ativar(ws)
                ws.send_json({"type": "message", "text": "bonjour", "t": 7})
                eventos = _ate(ws, _fim_conversa)
                self.assertFalse(next(e for e in eventos if e["type"] == "modo")["ativo"])
        finally:
            conversa.TIMEOUT_S = antes
        self.assertIn("TimeoutError", self.saida.getvalue())

    def test_sem_sessao_o_fluxo_e_o_de_sempre(self):
        api = ClienteFalso([])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            for i in range(2):
                ws.send_json({"type": "message", "text": "que horas são", "voice": True, "t": i})
                eventos = _ate(ws, lambda e: e.get("type") == "done")
                self.assertFalse([e for e in eventos if e["type"] in ("frase", "modo")])
        self.assertEqual(len(self.simba.recebidos), 2)
        self.assertEqual(api.chamadas, [])

    def test_app_antigo_nao_entra_no_modo(self):
        api = ClienteFalso([])
        conversa.definir_cliente(api)
        with self._ws(recursos="") as ws:
            ws.send_json({"type": "message", "text": "quero praticar francês", "voice": True, "t": 1})
            eventos = _ate(ws, lambda e: e.get("type") == "done")
            self.assertFalse([e for e in eventos if e["type"] in ("frase", "modo")])
            self.assertTrue(any("só funciona no app" in e.get("text", "") for e in eventos if e["type"] == "text"))
            ws.send_json({"type": "message", "text": "bonjour", "voice": True, "t": 2})
            _ate(ws, lambda e: e.get("type") == "done")
        self.assertEqual(len(self.simba.recebidos), 2)
        self.assertEqual(api.chamadas, [])

    def test_sessoes_isoladas_por_conexao(self):
        api = ClienteFalso([["Salut !"], ["Oui."]])
        conversa.definir_cliente(api)
        with self._ws() as ws1:
            self._ativar(ws1)
            with self._ws() as ws2:
                ws2.send_json({"type": "message", "text": "que horas são", "voice": True, "t": 9})
                eventos = _ate(ws2, lambda e: e.get("type") == "done")
                self.assertFalse([e for e in eventos if e["type"] in ("frase", "modo")])
                self.assertEqual(len(server.CONVERSAS), 1)
        self.assertEqual(len(self.simba.recebidos), 2)


# ---------- uso ----------

class Uso(unittest.TestCase):
    def test_contadores_da_sessao_e_do_total(self):
        antes = dict(conversa.USO_TOTAL)
        s = conversa.Sessao(idioma_alvo="inglês", bcp47="en-US", voz="en-US-AriaNeural")
        u = types.SimpleNamespace(input_tokens=10, output_tokens=5, cache_creation_input_tokens=None, cache_read_input_tokens=7)
        s.contar(u)
        s.contar(u)
        self.assertEqual(s.uso, {"input_tokens": 20, "output_tokens": 10, "cache_creation_input_tokens": 0,
                                 "cache_read_input_tokens": 14})
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            conversa.fechar(s, "fim")
            conversa.fechar(s, "fim")
        self.assertEqual(conversa.USO_TOTAL["sessoes"], antes["sessoes"] + 1)
        self.assertEqual(conversa.USO_TOTAL["input_tokens"], antes["input_tokens"] + 20)
        self.assertEqual(conversa.USO_TOTAL["cache_read_input_tokens"], antes["cache_read_input_tokens"] + 14)
        self.assertEqual(saida.getvalue().count("[uso]"), 1)

    def test_endpoint_uso_protegido(self):
        from fastapi.testclient import TestClient
        c = TestClient(server.app)
        self.assertEqual(c.get("/uso").status_code, 401)
        self.assertEqual(c.get("/uso?token=errado").status_code, 401)
        r = c.get(f"/uso?token={TOKEN}")
        self.assertEqual(r.status_code, 200)
        for campo in ("sessoes", "turnos", "minutos", "input_tokens", "output_tokens",
                      "cache_creation_input_tokens", "cache_read_input_tokens", "ativas", "modelo"):
            self.assertIn(campo, r.json())


# ---------- /tts com voz ----------

class TtsVoz(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        conversa.definir_vozes(VOZES)
        self.c = TestClient(server.app)

    def test_sem_voz_usa_a_padrao(self):
        r = self.c.post(f"/tts?token={TOKEN}", json={"text": "Olá"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(server.TTS_JOBS[r.json()["id"]], ("Olá", server.VOICE))

    def test_voz_da_lista_e_aceita(self):
        r = self.c.post(f"/tts?token={TOKEN}", json={"text": "Bonjour", "voz": "fr-FR-HenriNeural"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(server.TTS_JOBS[r.json()["id"]], ("Bonjour", "fr-FR-HenriNeural"))

    def test_voz_fora_da_lista_e_recusada(self):
        for voz in ("fr-FR-Inventada", "../../etc", "pt-BR-AntonioNeural; rm"):
            r = self.c.post(f"/tts?token={TOKEN}", json={"text": "x", "voz": voz})
            self.assertEqual(r.status_code, 400, voz)

    def test_lista_indisponivel_so_aceita_a_padrao(self):
        async def falha():
            raise OSError("sem rede")
        original = conversa.vozes
        conversa.vozes = falha
        try:
            self.assertEqual(self.c.post(f"/tts?token={TOKEN}", json={"text": "x", "voz": "fr-FR-HenriNeural"}).status_code, 400)
            self.assertEqual(self.c.post(f"/tts?token={TOKEN}", json={"text": "x"}).status_code, 200)
        finally:
            conversa.vozes = original


if __name__ == "__main__":
    unittest.main()
