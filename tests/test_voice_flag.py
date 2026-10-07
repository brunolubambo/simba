"""voice:true acrescenta a instrução de voz; voice:false ou ausente envia o texto puro. O ack devolve o "t".

Todos os valores aqui são falsos de propósito. Não usar código real.
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
INSTRUCAO = "[por voz: 1 ou 2 frases, sem markdown, pronto para falar]\n"


def _carregar(nome):
    if "simba" not in sys.modules:
        spec = importlib.machinery.ModuleSpec("simba", loader=None, is_package=True)
        pacote = importlib.util.module_from_spec(spec)
        pacote.__path__ = [str(RAIZ)]
        pacote.__package__ = "simba"
        sys.modules["simba"] = pacote
    return importlib.import_module(nome)


server = _carregar("simba.server")


class FalsoSimba:
    def __init__(self):
        self.recebidos = []

    async def ask(self, text):
        self.recebidos.append(text)
        yield {"type": "text", "text": "ok"}
        yield {"type": "done", "cost_usd": 0}


class VozNoServidor(unittest.TestCase):
    def setUp(self):
        self.simba = FalsoSimba()
        self.antes = dict(server.state)
        server.state["simba"] = self.simba
        server.state["observer"] = types.SimpleNamespace(enabled=False, available=False)

    def tearDown(self):
        server.state.clear()
        server.state.update(self.antes)

    def _rodar(self, **kw):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            asyncio.run(server.run_and_broadcast("que horas são", "celular", **kw))
        return saida.getvalue()

    def test_voice_true_acrescenta_a_instrucao(self):
        self._rodar(voice=True)
        self.assertEqual(self.simba.recebidos, [INSTRUCAO + "que horas são"])

    def test_voice_false_envia_o_texto_puro(self):
        self._rodar(voice=False)
        self.assertEqual(self.simba.recebidos, ["que horas são"])

    def test_sem_voice_envia_o_texto_puro(self):
        self._rodar()
        self.assertEqual(self.simba.recebidos, ["que horas são"])

    def test_log_perf_do_primeiro_text_sem_conteudo(self):
        log = self._rodar(voice=True)
        self.assertIn("[perf]", log)
        self.assertIn("primeiro text enviado", log)
        self.assertNotIn("que horas", log)

    def test_websocket_le_voice_e_devolve_ack_com_t(self):
        from fastapi.testclient import TestClient

        cliente = TestClient(server.app)
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            with cliente.websocket_connect("/ws?token=token-de-teste-123&device=celular") as ws:
                for voice, esperado in ((True, INSTRUCAO + "oi"), (False, "oi"), (None, "oi")):
                    corpo = {"type": "message", "text": "oi", "t": 12345}
                    if voice is not None:
                        corpo["voice"] = voice
                    self.simba.recebidos.clear()
                    ws.send_json(corpo)
                    tipos = []
                    ack = None
                    while "done" not in tipos:
                        ev = ws.receive_json()
                        tipos.append(ev["type"])
                        if ev["type"] == "ack":
                            ack = ev
                    self.assertEqual(ack, {"type": "ack", "t": 12345})
                    self.assertEqual(self.simba.recebidos, [esperado])
        self.assertIn("voice=True", saida.getvalue())
        self.assertIn("voice=False", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
