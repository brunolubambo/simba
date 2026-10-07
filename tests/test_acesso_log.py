"""Log sem o código de acesso, e janela com dois códigos.

Todos os valores aqui são falsos de propósito. Não usar código real.
"""
import asyncio
import importlib
import importlib.machinery
import importlib.util
import io
import logging
import os
import sys
import unittest
from pathlib import Path

# Antes de importar o servidor: o .env real não pode substituir estes falsos.
os.environ["SIMBA_TOKEN"] = "token-de-teste-123"
os.environ["SIMBA_TOKEN_ANTERIOR"] = ""
os.environ["CELULAR_TOKEN"] = ""
os.environ["PC_TOKEN"] = "p" * 40

RAIZ = Path(__file__).resolve().parents[1]
ATUAL = "token-de-teste-123"
ANTERIOR = "token-anterior-de-teste"
OUTRO = "token-errado-de-teste"


def _carregar(nome):
    if "simba" not in sys.modules:
        spec = importlib.machinery.ModuleSpec("simba", loader=None, is_package=True)
        pacote = importlib.util.module_from_spec(spec)
        pacote.__path__ = [str(RAIZ)]
        pacote.__package__ = "simba"
        sys.modules["simba"] = pacote
    return importlib.import_module(nome)


server = _carregar("simba.server")
celular = _carregar("simba.celular")
pc = _carregar("simba.pc")


def _registro(msg, args):
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


class FiltroLog(unittest.TestCase):
    def _filtro(self):
        # Quebra se o filtro sumir do servidor ou deixar de redigir a linha.
        cls = getattr(server, "RedactTokenFilter", None)
        self.assertIsNotNone(cls)
        return cls()

    def test_linha_http_esconde_o_codigo_e_preserva_o_resto(self):
        bruto = '10.0.0.8:443 - "GET /celular/proximo?token=token-de-teste-123 HTTP/1.1" 200'
        registro = _registro(
            '%s - "%s %s HTTP/%s" %d',
            ("10.0.0.8:443", "GET", "/celular/proximo?token=token-de-teste-123", "1.1", 200),
        )
        self.assertTrue(self._filtro().filter(registro))
        self.assertEqual(
            registro.getMessage(),
            '10.0.0.8:443 - "GET /celular/proximo?token=*** HTTP/1.1" 200',
        )
        self.assertNotIn(ATUAL, registro.getMessage())
        self.assertNotIn(ATUAL, str(registro.args))
        self.assertEqual(registro.getMessage().replace("token=***", "token=token-de-teste-123"), bruto)

    def test_linha_websocket_esconde_o_codigo_e_preserva_device(self):
        registro = _registro(
            '%s - "WebSocket %s" [accepted]',
            ("10.0.0.8:443", "/ws?token=token-de-teste-123&device=celular"),
        )
        self.assertTrue(self._filtro().filter(registro))
        self.assertEqual(
            registro.getMessage(),
            '10.0.0.8:443 - "WebSocket /ws?token=***&device=celular" [accepted]',
        )
        self.assertNotIn(ATUAL, str(registro.args))

    def test_mensagem_ja_formatada_tambem_e_redigida(self):
        registro = _registro(
            '10.0.0.8:443 - "GET /celular/proximo?token=token-de-teste-123" extra',
            None,
        )
        self.assertTrue(self._filtro().filter(registro))
        self.assertEqual(
            registro.getMessage(),
            '10.0.0.8:443 - "GET /celular/proximo?token=***" extra',
        )

    def test_aspas_interrompem_o_valor_e_o_resto_fica(self):
        registro = _registro('prefixo "token=token-de-teste-123" device=celular', None)
        self.assertTrue(self._filtro().filter(registro))
        self.assertEqual(registro.getMessage(), 'prefixo "token=***" device=celular')

    def test_formatter_de_acesso_do_uvicorn_recebe_args_intactos(self):
        # Quebra se o filtro achatar args: o formatter do uvicorn desempacota 5 campos.
        from uvicorn.logging import AccessFormatter

        registro = _registro(
            '%s - "%s %s HTTP/%s" %d',
            ("10.0.0.8:443", "GET", "/celular/proximo?token=token-de-teste-123&n=1", "1.1", 200),
        )
        self.assertTrue(self._filtro().filter(registro))
        texto = AccessFormatter(
            '%(client_addr)s - "%(request_line)s" %(status_code)s',
            use_colors=False,
        ).format(registro)
        self.assertEqual(
            texto,
            '10.0.0.8:443 - "GET /celular/proximo?token=***&n=1 HTTP/1.1" 200 OK',
        )
        self.assertNotIn(ATUAL, texto)

    def test_logger_uvicorn_access_ja_redige(self):
        # Quebra se o filtro não estiver instalado no logger que o uvicorn usa no Dockerfile.
        log = logging.getLogger("uvicorn.access")
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        try:
            log.info(
                '%s - "%s %s HTTP/%s" %d',
                "10.0.0.8:443",
                "GET",
                "/celular/proximo?token=token-de-teste-123",
                "1.1",
                200,
            )
        finally:
            log.removeHandler(handler)
        texto = buf.getvalue()
        self.assertIn("token=***", texto)
        self.assertNotIn(ATUAL, texto)
        self.assertIn("/celular/proximo?", texto)

    def test_logger_da_linha_websocket_tambem_redige(self):
        # No uvicorn deste projeto a linha WebSocket sai em uvicorn.error, não em access.
        log = logging.getLogger("uvicorn.error")
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        nivel = log.level
        log.setLevel(logging.INFO)
        try:
            log.info(
                '%s - "WebSocket %s" [accepted]',
                "10.0.0.8:443",
                "/ws?token=token-de-teste-123&device=celular",
            )
        finally:
            log.removeHandler(handler)
            log.setLevel(nivel)
        texto = buf.getvalue()
        self.assertIn('WebSocket /ws?token=***&device=celular', texto)
        self.assertNotIn(ATUAL, texto)


class _Socket:
    def __init__(self):
        self.code = None
        self.accepted = False

    async def close(self, code=1000):
        self.code = code

    async def accept(self):
        self.accepted = True
        raise RuntimeError("parada-apos-aceitar")


class Codigos(unittest.TestCase):
    def setUp(self):
        self._token = server.TOKEN
        self._anterior = getattr(server, "TOKEN_ANTERIOR", "")
        server.TOKEN = ATUAL
        if hasattr(server, "TOKEN_ANTERIOR"):
            server.TOKEN_ANTERIOR = ""

    def tearDown(self):
        server.TOKEN = self._token
        if hasattr(server, "TOKEN_ANTERIOR"):
            server.TOKEN_ANTERIOR = self._anterior

    def _ws(self, token):
        socket = _Socket()
        try:
            asyncio.run(server.ws(socket, token=token))
        except RuntimeError as e:
            if str(e) != "parada-apos-aceitar":
                raise
        return socket

    def test_check_aceita_o_atual(self):
        server.check(ATUAL)

    def test_check_aceita_o_anterior_quando_definido(self):
        server.TOKEN_ANTERIOR = ANTERIOR
        try:
            server.check(ANTERIOR)
        except server.HTTPException:
            self.fail("check() recusou o código anterior")

    def test_check_recusa_outro_e_vazio(self):
        server.TOKEN_ANTERIOR = ANTERIOR
        with self.assertRaises(server.HTTPException) as outro:
            server.check(OUTRO)
        self.assertEqual(outro.exception.status_code, 401)
        with self.assertRaises(server.HTTPException) as vazio:
            server.check("")
        self.assertEqual(vazio.exception.status_code, 401)

    def test_check_ignora_anterior_vazio(self):
        server.TOKEN_ANTERIOR = ""
        with self.assertRaises(server.HTTPException):
            server.check(ANTERIOR)

    def test_websocket_aceita_o_atual(self):
        socket = self._ws(ATUAL)
        self.assertTrue(socket.accepted)
        self.assertIsNone(socket.code)

    def test_websocket_aceita_o_anterior_quando_definido(self):
        server.TOKEN_ANTERIOR = ANTERIOR
        socket = self._ws(ANTERIOR)
        self.assertTrue(socket.accepted)
        self.assertIsNone(socket.code)

    def test_websocket_recusa_outro_e_vazio(self):
        server.TOKEN_ANTERIOR = ANTERIOR
        outro = self._ws(OUTRO)
        self.assertFalse(outro.accepted)
        self.assertEqual(outro.code, 4401)
        vazio = self._ws("")
        self.assertFalse(vazio.accepted)
        self.assertEqual(vazio.code, 4401)


class CelularCodigos(unittest.TestCase):
    def test_celular_aceita_atual_anterior_e_recusa_outro_e_vazio(self):
        anterior_env = {
            "CELULAR_TOKEN": "",
            "SIMBA_TOKEN": ATUAL,
            "SIMBA_TOKEN_ANTERIOR": ANTERIOR,
        }
        guardados = {k: os.environ.get(k) for k in anterior_env}
        try:
            os.environ.update(anterior_env)
            self.assertTrue(celular.token_ok(ATUAL))
            self.assertTrue(celular.token_ok(ANTERIOR))
            self.assertFalse(celular.token_ok(OUTRO))
            self.assertFalse(celular.token_ok(""))
        finally:
            for k, v in guardados.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_celular_sem_anterior_so_aceita_o_fallback(self):
        chaves = ("CELULAR_TOKEN", "SIMBA_TOKEN", "SIMBA_TOKEN_ANTERIOR")
        guardados = {k: os.environ.get(k) for k in chaves}
        try:
            os.environ["CELULAR_TOKEN"] = ""
            os.environ["SIMBA_TOKEN"] = ATUAL
            os.environ["SIMBA_TOKEN_ANTERIOR"] = ""
            self.assertTrue(celular.token_ok(ATUAL))
            self.assertFalse(celular.token_ok(ANTERIOR))
            self.assertFalse(celular.token_ok(""))
        finally:
            for k, v in guardados.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_celular_com_token_proprio_tambem_aceita_o_anterior(self):
        chaves = ("CELULAR_TOKEN", "SIMBA_TOKEN", "SIMBA_TOKEN_ANTERIOR")
        guardados = {k: os.environ.get(k) for k in chaves}
        try:
            os.environ["CELULAR_TOKEN"] = "celular-token-de-teste"
            os.environ["SIMBA_TOKEN"] = ATUAL
            os.environ["SIMBA_TOKEN_ANTERIOR"] = ANTERIOR
            self.assertTrue(celular.token_ok("celular-token-de-teste"))
            self.assertTrue(celular.token_ok(ANTERIOR))
            self.assertFalse(celular.token_ok(ATUAL))
            self.assertFalse(celular.token_ok(OUTRO))
            self.assertFalse(celular.token_ok(""))
        finally:
            for k, v in guardados.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class PcInalterado(unittest.TestCase):
    def test_pc_nao_aceita_o_codigo_anterior_do_simba(self):
        chaves = ("PC_TOKEN", "SIMBA_TOKEN", "SIMBA_TOKEN_ANTERIOR")
        guardados = {k: os.environ.get(k) for k in chaves}
        try:
            os.environ["PC_TOKEN"] = "p" * 40
            os.environ["SIMBA_TOKEN"] = ATUAL
            os.environ["SIMBA_TOKEN_ANTERIOR"] = ANTERIOR
            self.assertTrue(pc.token_ok("p" * 40))
            self.assertFalse(pc.token_ok(ANTERIOR))
            self.assertFalse(pc.token_ok(ATUAL))
            self.assertFalse(pc.token_ok(""))
        finally:
            for k, v in guardados.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
