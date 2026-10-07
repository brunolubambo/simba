"""O servidor repassa o detalhe do app ao modelo e registra hora e detalhe sem token.

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
import unittest
from pathlib import Path

os.environ["SIMBA_TOKEN"] = "token-de-teste-123"
os.environ["SIMBA_TOKEN_ANTERIOR"] = ""
os.environ["CELULAR_TOKEN"] = ""
os.environ["CELULAR_APP"] = "true"

RAIZ = Path(__file__).resolve().parents[1]


def _carregar(nome):
    if "simba" not in sys.modules:
        spec = importlib.machinery.ModuleSpec("simba", loader=None, is_package=True)
        pacote = importlib.util.module_from_spec(spec)
        pacote.__path__ = [str(RAIZ)]
        pacote.__package__ = "simba"
        sys.modules["simba"] = pacote
    return importlib.import_module(nome)


celular = _carregar("simba.celular")


async def _rodar(hora: str, sucesso: bool, detalhe: str):
    """Simula o app: pega o comando em /celular/proximo e responde em /celular/resultado."""
    tarefa = asyncio.create_task(celular.executar({"acao": "alarme", "hora": hora}))
    pedido = None
    for _ in range(50):
        await asyncio.sleep(0.01)
        pedido = celular.proximo()
        if pedido:
            break
    assert pedido, "o comando não chegou ao app"
    assert pedido["hora"] == hora
    assert celular.report(pedido["id"], sucesso, detalhe) is True
    return pedido, tarefa


class DetalheDoApp(unittest.TestCase):
    def _executar(self, hora, sucesso, detalhe):
        saida = io.StringIO()

        async def tudo():
            pedido, tarefa = await _rodar(hora, sucesso, detalhe)
            try:
                return pedido, await tarefa, None
            except RuntimeError as e:
                return pedido, None, str(e)

        with contextlib.redirect_stdout(saida):
            pedido, texto, erro = asyncio.run(tudo())
        return pedido, texto, erro, saida.getvalue()

    def test_sucesso_com_detalhe_chega_ao_modelo_e_ao_log(self):
        pedido, texto, erro, log = self._executar("10:41", True, "Relógio confirmou: alarme hoje 10:41")
        self.assertIsNone(erro)
        self.assertIn("criar alarme às 10:41", texto)
        self.assertIn("Relógio confirmou: alarme hoje 10:41", texto)
        self.assertIn("[celular] alarme: ok", log)
        self.assertIn(f"id={pedido['id']}", log)
        self.assertIn("hora='10:41'", log)
        self.assertIn("Relógio confirmou: alarme hoje 10:41", log)

    def test_falha_com_detalhe_chega_ao_modelo_inteira(self):
        detalhe = "o Relógio não confirmou o alarme (hoje 10:41); deixei uma notificação para tocar"
        _, texto, erro, log = self._executar("10:41", False, detalhe)
        self.assertIsNone(texto)
        self.assertIn(detalhe, erro)
        self.assertIn("[celular] alarme: erro", log)
        self.assertIn("hora='10:41'", log)
        self.assertIn("deixei uma notificação para tocar", log)

    def test_app_antigo_sem_detalhe_continua_funcionando(self):
        _, texto, erro, log = self._executar("07:30", True, "")
        self.assertIsNone(erro)
        self.assertEqual(texto, "Feito no celular: criar alarme às 07:30.")
        self.assertIn("[celular] alarme: ok", log)
        self.assertIn("detalhe: (nenhum)", log)

    def test_app_antigo_falha_sem_detalhe(self):
        _, _, erro, log = self._executar("07:30", False, "")
        self.assertIn("o app não disse o motivo", erro)
        self.assertIn("[celular] alarme: erro", log)

    def test_log_nao_leva_token_e_fica_em_uma_linha(self):
        _, _, _, log = self._executar("10:41", True, "linha 1\nlinha 2")
        self.assertNotIn("token-de-teste-123", log)
        self.assertNotIn("token=", log)
        linhas = [x for x in log.splitlines() if x.startswith("[celular]")]
        self.assertEqual(len(linhas), 1)
        self.assertIn("linha 1 linha 2", linhas[0])


if __name__ == "__main__":
    unittest.main()
