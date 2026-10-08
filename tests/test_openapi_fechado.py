"""Documentacao automatica do FastAPI (/docs, /redoc, /openapi.json) fechada por padrao.

Todos os valores aqui sao falsos de proposito. Nao usar codigo real.

O servidor decide isso na hora em que o app e criado (import). Por isso o teste de ponta a ponta
sobe um processo novo por cenario, com SIMBA_DOCS controlado: nao depende do que outro teste ja
importou nem do .env da maquina, e nao precisa recarregar modulo.
"""
import importlib
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

os.environ["SIMBA_TOKEN"] = "token-de-teste-123"
os.environ["SIMBA_TOKEN_ANTERIOR"] = ""
os.environ["CELULAR_TOKEN"] = ""
os.environ["PC_TOKEN"] = "p" * 40

RAIZ = Path(__file__).resolve().parents[1]
ROTAS_DOCS = ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect")


def _carregar(nome):
    if "simba" not in sys.modules:
        spec = importlib.machinery.ModuleSpec("simba", loader=None, is_package=True)
        pacote = importlib.util.module_from_spec(spec)
        pacote.__path__ = [str(RAIZ)]
        pacote.__package__ = "simba"
        sys.modules["simba"] = pacote
    return importlib.import_module(nome)


server = _carregar("simba.server")

# Roda num processo novo: importa o servidor de verdade e consulta o app sem rede (TestClient sem
# "with" nao dispara o lifespan, entao nada de Telegram, observador etc.).
_SONDA = r"""
import importlib, importlib.machinery, importlib.util, json, sys
spec = importlib.machinery.ModuleSpec("simba", loader=None, is_package=True)
pacote = importlib.util.module_from_spec(spec)
pacote.__path__ = [sys.argv[1]]
pacote.__package__ = "simba"
sys.modules["simba"] = pacote
server = importlib.import_module("simba.server")
from fastapi.testclient import TestClient
c = TestClient(server.app)
out = {}
for rota in sys.argv[2:]:
    r = c.get(rota)
    out[rota] = {"status": r.status_code, "corpo": r.text}
print("SONDA:" + json.dumps(out))
"""


def _sondar(simba_docs, rotas):
    env = dict(os.environ)
    env.update({
        "SIMBA_TOKEN": "token-de-teste-123",
        "SIMBA_TOKEN_ANTERIOR": "",
        "CELULAR_TOKEN": "",
        "PC_TOKEN": "p" * 40,
        "SIMBA_DOCS": simba_docs,  # definido (mesmo vazio): o .env nao sobrescreve
    })
    proc = subprocess.run(
        [sys.executable, "-c", _SONDA, str(RAIZ), *rotas],
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=180,
    )
    linhas = [l for l in proc.stdout.splitlines() if l.startswith("SONDA:")]
    if not linhas:
        raise AssertionError(f"sonda sem resultado (codigo {proc.returncode}): {proc.stderr[-800:]}")
    return json.loads(linhas[-1][len("SONDA:"):])


class ConfigDocs(unittest.TestCase):
    def test_padrao_desliga_os_tres(self):
        self.assertEqual(
            server.docs_config({}),
            {"docs_url": None, "redoc_url": None, "openapi_url": None},
        )

    def test_vazio_ou_false_continua_desligado(self):
        for valor in ("", "false", "False", "0", "nao", "yes", "1"):
            with self.subTest(valor=valor):
                self.assertIsNone(server.docs_config({"SIMBA_DOCS": valor})["openapi_url"])

    def test_true_liga_os_tres(self):
        for valor in ("true", "TRUE", " True "):
            with self.subTest(valor=valor):
                self.assertEqual(
                    server.docs_config({"SIMBA_DOCS": valor}),
                    {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"},
                )


class AppPadraoFechado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _sondar("", (*ROTAS_DOCS, "/naoexiste", "/health"))

    def test_rotas_de_documentacao_dao_404(self):
        for rota in ROTAS_DOCS:
            with self.subTest(rota=rota):
                self.assertEqual(self.r[rota]["status"], 404)

    def test_corpo_nao_lista_rotas_nem_cita_openapi(self):
        for rota in ROTAS_DOCS:
            corpo = self.r[rota]["corpo"].lower()
            for proibido in ("openapi", "swagger", "redoc", "paths", "/celular/proximo", "/upload", "/painel"):
                with self.subTest(rota=rota, proibido=proibido):
                    self.assertNotIn(proibido, corpo)

    def test_docs_respondem_igual_a_uma_rota_inexistente(self):
        esperado = self.r["/naoexiste"]
        for rota in ROTAS_DOCS:
            with self.subTest(rota=rota):
                self.assertEqual(self.r[rota]["status"], esperado["status"])
                self.assertEqual(self.r[rota]["corpo"], esperado["corpo"])

    def test_rota_real_continua_respondendo(self):
        self.assertEqual(self.r["/health"]["status"], 200)
        self.assertEqual(json.loads(self.r["/health"]["corpo"]), {"ok": True})


class AppComDocsLigadas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _sondar("true", ("/openapi.json", "/docs", "/redoc", "/health"))

    def test_as_tres_voltam_a_responder_200(self):
        for rota in ("/openapi.json", "/docs", "/redoc"):
            with self.subTest(rota=rota):
                self.assertEqual(self.r[rota]["status"], 200)

    def test_openapi_lista_as_rotas_reais(self):
        paths = json.loads(self.r["/openapi.json"]["corpo"])["paths"]
        self.assertIn("/health", paths)

    def test_rota_real_continua_respondendo(self):
        self.assertEqual(self.r["/health"]["status"], 200)


if __name__ == "__main__":
    unittest.main()
