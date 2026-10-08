"""Log [perf] "recebida" sem o texto falado, e lista de vozes carregada na subida sem derrubar o servidor.

Sem rede: o cliente do agente e o edge-tts são simulados. Valores falsos de propósito.
"""
import asyncio
import contextlib
import importlib
import importlib.machinery
import importlib.util
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


def _carregar(nome):
    if "simba" not in sys.modules:
        spec = importlib.machinery.ModuleSpec("simba", loader=None, is_package=True)
        pacote = importlib.util.module_from_spec(spec)
        pacote.__path__ = [str(RAIZ)]
        pacote.__package__ = "simba"
        sys.modules["simba"] = pacote
    return importlib.import_module(nome)


core = _carregar("simba.core")
conversa = _carregar("simba.conversa")


class ClienteSemResposta:
    def __init__(self):
        self.perguntas = []

    async def query(self, texto):
        self.perguntas.append(texto)

    async def receive_response(self):
        return
        yield


def _simba_falso():
    s = core.Simba.__new__(core.Simba)
    s.approve = None
    s.session_id = None
    s._lock = asyncio.Lock()
    s._connected = True
    s._turns = 0
    s._session_cost = 0.0
    s._last_user = ""
    s._last_answer = ""
    s._bridge = ""
    s._load = {"system": 10, "prompt": 5, "memory": 5, "agents": 1, "mcp": 2}
    s.client = ClienteSemResposta()
    return s


class LogRecebida(unittest.TestCase):
    def setUp(self):
        self._autorizadas = core.authorized
        core.authorized = lambda: []
        self._mudou = core.CHANGED["flag"]
        core.CHANGED["flag"] = False

    def tearDown(self):
        core.authorized = self._autorizadas
        core.CHANGED["flag"] = self._mudou

    def test_recebida_mostra_so_a_contagem(self):
        texto = "me lembra de ligar para a Joana amanhã"
        simba = _simba_falso()
        saida = io.StringIO()

        async def rodar():
            return [ev async for ev in simba.ask(texto)]

        with contextlib.redirect_stdout(saida):
            asyncio.run(rodar())
        log = saida.getvalue()
        linha = next(l for l in log.splitlines() if " recebida " in l)
        self.assertIn(f"chars={len(texto)}", linha)
        self.assertNotIn("Joana", log)
        self.assertNotIn("lembra", log)
        self.assertEqual(len(simba.client.perguntas), 1)


class VozesNaSubida(unittest.TestCase):
    def setUp(self):
        self._antes = sys.modules.get("edge_tts")
        conversa.definir_vozes(None)

    def tearDown(self):
        conversa.definir_vozes(None)
        if self._antes is None:
            sys.modules.pop("edge_tts", None)
        else:
            sys.modules["edge_tts"] = self._antes

    def _edge(self, resposta):
        async def list_voices():
            if isinstance(resposta, Exception):
                raise resposta
            return resposta
        sys.modules["edge_tts"] = types.SimpleNamespace(list_voices=list_voices)

    def test_carrega_a_lista(self):
        self._edge([{"ShortName": "pt-BR-AntonioNeural", "Locale": "pt-BR", "Gender": "Male"}])
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            asyncio.run(conversa.precarregar_vozes())
        self.assertIn("vozes=1", saida.getvalue())
        self.assertTrue(asyncio.run(conversa.voz_valida("pt-BR-AntonioNeural")))

    def test_rede_fora_nao_derruba(self):
        self._edge(OSError("sem rede"))
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            asyncio.run(conversa.precarregar_vozes())
        self.assertIn("indisponível na subida (OSError)", saida.getvalue())
        self.assertIsNone(conversa._VOZES, "falha não pode guardar lista vazia; a próxima ativação tenta de novo")


if __name__ == "__main__":
    unittest.main()
