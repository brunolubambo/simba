"""Via rapida com contexto: historico curto do Haiku (passo 1). Sem rede.

Frases e valores falsos de proposito.
"""
import asyncio
import contextlib
import io
import os
import types
import unittest

try:  # `discover -s tests` (modulo de topo) ou `unittest tests.test_rapido_contexto`
    from test_conversa import (_carregar, _ate, _fim_conversa, ClienteFalso, SimbaFalso, _Fluxo, VOZES, TOKEN)
    from test_rapido import _Ambiente
except ImportError:  # pragma: no cover
    from tests.test_conversa import (_carregar, _ate, _fim_conversa, ClienteFalso, SimbaFalso, _Fluxo, VOZES, TOKEN)
    from tests.test_rapido import _Ambiente

rapido = _carregar("simba.rapido")
conversa = _carregar("simba.conversa")
server = _carregar("simba.server")

CEL = rapido.DISPOSITIVO


def _responder(texto, device=CEL, **kw):
    """Roda rapido.responder com um `enviar` que so guarda os eventos. Devolve (resultado, eventos)."""
    eventos = []

    async def enviar(ev):
        eventos.append(ev)

    res = asyncio.run(rapido.responder(texto, enviar, "voz-falsa", device=device, **kw))
    return res, eventos


def _papeis(mensagens):
    return [m["role"] for m in mensagens]


class _Limpo(_Ambiente):
    def setUp(self):
        super().setUp()
        for d in (CEL, "outro", "tablet"):
            rapido.limpar(d)
        self._log = io.StringIO()
        self._redir = contextlib.redirect_stdout(self._log)
        self._redir.__enter__()

    def tearDown(self):
        self._redir.__exit__(None, None, None)
        conversa.definir_cliente(None)
        for d in (CEL, "outro", "tablet"):
            rapido.limpar(d)
        super().tearDown()


# ---------- passo 1: historico em memoria ----------

class Historico(_Limpo):
    def test_constantes_editaveis(self):
        self.assertEqual(rapido.HISTORICO_TROCAS, 3)
        self.assertEqual(rapido.HISTORICO_TEXTO_MAX, 300)
        self.assertEqual(rapido.HISTORICO_EXPIRA_S, 30 * 60)
        self.assertEqual(rapido.DISPOSITIVO, "celular")

    def test_guarda_na_ordem_de_chegada(self):
        rapido.registrar(CEL, "p1", "r1", agora=0)
        rapido.registrar(CEL, "p2", "r2", agora=1)
        self.assertEqual(rapido.recentes(CEL, agora=2), [("p1", "r1"), ("p2", "r2")])

    def test_sem_nada_devolve_lista_vazia(self):
        self.assertEqual(rapido.recentes(CEL, agora=0), [])
        self.assertEqual(rapido.recentes("nunca-visto", agora=0), [])

    def test_limitado_as_ultimas_tres_trocas(self):
        for i in range(1, 6):
            rapido.registrar(CEL, f"p{i}", f"r{i}", agora=i)
        self.assertEqual(rapido.recentes(CEL, agora=6), [("p3", "r3"), ("p4", "r4"), ("p5", "r5")])

    def test_limite_acompanha_a_constante(self):
        antes = rapido.HISTORICO_TROCAS
        rapido.HISTORICO_TROCAS = 1
        try:
            rapido.registrar(CEL, "p1", "r1", agora=0)
            rapido.registrar(CEL, "p2", "r2", agora=1)
            self.assertEqual(rapido.recentes(CEL, agora=2), [("p2", "r2")])
        finally:
            rapido.HISTORICO_TROCAS = antes

    def test_texto_longo_e_truncado(self):
        rapido.registrar(CEL, "p" * 1000, "palavra " * 200, agora=0)
        (pergunta, resposta), = rapido.recentes(CEL, agora=1)
        self.assertLessEqual(len(pergunta), rapido.HISTORICO_TEXTO_MAX)
        self.assertLessEqual(len(resposta), rapido.HISTORICO_TEXTO_MAX)
        self.assertTrue(pergunta.endswith("..."))
        self.assertTrue(resposta.endswith("..."))

    def test_texto_curto_fica_intacto_e_espacos_sao_normalizados(self):
        rapido.registrar(CEL, "  oi   tudo\nbem? ", "Tudo bem.", agora=0)
        self.assertEqual(rapido.recentes(CEL, agora=1), [("oi tudo bem?", "Tudo bem.")])

    def test_texto_no_limite_exato_nao_e_cortado(self):
        exato = "a" * rapido.HISTORICO_TEXTO_MAX
        rapido.registrar(CEL, exato, exato, agora=0)
        self.assertEqual(rapido.recentes(CEL, agora=1), [(exato, exato)])

    def test_expira_por_inatividade(self):
        rapido.registrar(CEL, "p1", "r1", agora=100)
        self.assertEqual(len(rapido.recentes(CEL, agora=100 + rapido.HISTORICO_EXPIRA_S - 1)), 1)
        self.assertEqual(rapido.recentes(CEL, agora=100 + rapido.HISTORICO_EXPIRA_S + 1), [])

    def test_nova_troca_renova_o_prazo_de_todas(self):
        rapido.registrar(CEL, "p1", "r1", agora=0)
        rapido.registrar(CEL, "p2", "r2", agora=rapido.HISTORICO_EXPIRA_S - 10)
        depois = rapido.HISTORICO_EXPIRA_S - 10 + rapido.HISTORICO_EXPIRA_S - 1
        self.assertEqual([p for p, _ in rapido.recentes(CEL, agora=depois)], ["p1", "p2"])

    def test_troca_depois_de_expirar_comeca_do_zero(self):
        rapido.registrar(CEL, "velha", "resposta velha", agora=0)
        rapido.registrar(CEL, "nova", "resposta nova", agora=rapido.HISTORICO_EXPIRA_S + 5)
        self.assertEqual(rapido.recentes(CEL, agora=rapido.HISTORICO_EXPIRA_S + 6), [("nova", "resposta nova")])

    def test_ler_nao_renova_o_prazo(self):
        rapido.registrar(CEL, "p1", "r1", agora=0)
        rapido.recentes(CEL, agora=rapido.HISTORICO_EXPIRA_S - 1)
        self.assertEqual(rapido.recentes(CEL, agora=rapido.HISTORICO_EXPIRA_S + 1), [])

    def test_dispositivos_nao_se_misturam(self):
        rapido.registrar(CEL, "do celular", "r1", agora=0)
        rapido.registrar("outro", "do outro", "r2", agora=0)
        self.assertEqual(rapido.recentes(CEL, agora=1), [("do celular", "r1")])
        self.assertEqual(rapido.recentes("outro", agora=1), [("do outro", "r2")])

    def test_limpar_so_apaga_o_dispositivo(self):
        rapido.registrar(CEL, "p1", "r1", agora=0)
        rapido.registrar("outro", "p2", "r2", agora=0)
        rapido.limpar(CEL)
        self.assertEqual(rapido.recentes(CEL, agora=1), [])
        self.assertEqual(rapido.recentes("outro", agora=1), [("p2", "r2")])
        rapido.limpar("nunca-visto")             # nao levanta

    def test_vazio_nao_entra(self):
        for p, r in (("", "r"), ("p", ""), ("   ", "r"), ("p", " \n "), (None, "r"), ("p", None)):
            rapido.registrar(CEL, p, r, agora=0)
        self.assertEqual(rapido.recentes(CEL, agora=1), [])

    def test_recentes_devolve_copia(self):
        rapido.registrar(CEL, "p1", "r1", agora=0)
        rapido.recentes(CEL, agora=1).clear()
        self.assertEqual(len(rapido.recentes(CEL, agora=1)), 1)

    def test_nada_vai_para_o_log(self):
        rapido.registrar(CEL, "pergunta secreta", "resposta secreta", agora=0)
        rapido.recentes(CEL, agora=1)
        rapido.limpar(CEL)
        self.assertEqual(self._log.getvalue(), "")


# ---------- passo 1: o Haiku recebe o historico como turnos reais ----------

class ResponderComHistorico(_Limpo):
    def test_primeira_pergunta_so_leva_a_mensagem_atual(self):
        api = ClienteFalso([["Boa tarde."]])
        conversa.definir_cliente(api)
        _responder("boa tarde")
        self.assertEqual(api.chamadas[0]["messages"], [{"role": "user", "content": "boa tarde"}])

    def test_troca_respondida_pelo_haiku_vira_turno_da_proxima(self):
        api = ClienteFalso([["Obrigado se diz thank you. Simples."], ["In English: thank you."]])
        conversa.definir_cliente(api)
        _responder("como se diz obrigado em ingles")
        _responder("e em frances")
        self.assertEqual(api.chamadas[1]["messages"], [
            {"role": "user", "content": "como se diz obrigado em ingles"},
            {"role": "assistant", "content": "Obrigado se diz thank you. Simples."},
            {"role": "user", "content": "e em frances"},
        ])

    def test_papeis_alternam_comecando_por_user(self):
        api = ClienteFalso([[f"Resposta {i}."] for i in range(5)])
        conversa.definir_cliente(api)
        for i in range(5):
            _responder(f"pergunta {i}")
        for chamada in api.chamadas:
            papeis = _papeis(chamada["messages"])
            self.assertEqual(papeis[0], "user")
            self.assertEqual(papeis[-1], "user")
            self.assertEqual(papeis, ["user", "assistant"] * (len(papeis) // 2) + ["user"])

    def test_so_as_ultimas_tres_trocas_chegam_ao_haiku(self):
        api = ClienteFalso([[f"Resposta {i}."] for i in range(5)])
        conversa.definir_cliente(api)
        for i in range(5):
            _responder(f"pergunta {i}")
        ultima = api.chamadas[4]["messages"]
        self.assertEqual(len(ultima), 7)
        self.assertEqual([m["content"] for m in ultima if m["role"] == "user"],
                         ["pergunta 1", "pergunta 2", "pergunta 3", "pergunta 4"])

    def test_resposta_com_varias_frases_vira_um_unico_turno(self):
        api = ClienteFalso([["Primeira frase. Segunda frase."], ["ok."]])
        conversa.definir_cliente(api)
        _responder("conta algo")
        _responder("mais")
        self.assertEqual(api.chamadas[1]["messages"][1],
                         {"role": "assistant", "content": "Primeira frase. Segunda frase."})

    def test_historico_enviado_e_truncado(self):
        api = ClienteFalso([["palavra " * 200 + "fim."], ["ok."]])
        conversa.definir_cliente(api)
        _responder("p" * 900)
        _responder("e agora")
        antigas = api.chamadas[1]["messages"][:2]
        for m in antigas:
            self.assertLessEqual(len(m["content"]), rapido.HISTORICO_TEXTO_MAX)

    def test_troca_que_escalou_pelo_haiku_nao_entra(self):
        api = ClienteFalso([_Fluxo(["Deixe-me ver."], ferramenta="escalar_para_agente"), ["Tudo bem."]])
        conversa.definir_cliente(api)
        res, _ = _responder("qual o melhor jeito de estudar")
        self.assertTrue(res.escalou)
        self.assertEqual(rapido.recentes(CEL), [])
        _responder("oi")
        self.assertEqual(api.chamadas[1]["messages"], [{"role": "user", "content": "oi"}])

    def test_troca_que_escalou_sem_frase_nao_entra(self):
        api = ClienteFalso([_Fluxo([], ferramenta="escalar_para_agente"), ["Tudo bem."]])
        conversa.definir_cliente(api)
        _responder("pergunta qualquer")
        _responder("oi")
        self.assertEqual(api.chamadas[1]["messages"], [{"role": "user", "content": "oi"}])

    def test_falha_nao_entra(self):
        for primeira in (RuntimeError("falha simulada"), []):      # excecao da API e resposta vazia
            rapido.limpar(CEL)
            conversa.definir_cliente(ClienteFalso([primeira]))
            res, _ = _responder("pergunta qualquer")
            self.assertTrue(res.escalou)
            self.assertEqual(rapido.recentes(CEL), [])

    def test_timeout_depois_de_uma_frase_nao_entra(self):
        os.environ["RAPIDO_TIMEOUT_S"] = "0.45"
        conversa.definir_cliente(ClienteFalso([_Fluxo(["Primeira frase. Segunda", " lenta"], demora=0.3)]))
        res, _ = _responder("pergunta qualquer")
        self.assertTrue(res.escalou)
        self.assertEqual(res.frases, ["Primeira frase."])
        self.assertEqual(rapido.recentes(CEL), [])

    def test_turno_que_escalou_no_meio_nao_apaga_o_que_ja_estava(self):
        api = ClienteFalso([["Oi, tudo bem."], _Fluxo([], ferramenta="escalar_para_agente"), ["Certo."]])
        conversa.definir_cliente(api)
        _responder("oi")
        _responder("quanto esta o dolar")
        _responder("obrigado")
        self.assertEqual(api.chamadas[2]["messages"], [
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "Oi, tudo bem."},
            {"role": "user", "content": "obrigado"},
        ])

    def test_limpar_zera_o_que_o_haiku_ve(self):
        api = ClienteFalso([["Oi."], ["Certo."]])
        conversa.definir_cliente(api)
        _responder("oi")
        rapido.limpar(CEL)
        _responder("e entao")
        self.assertEqual(api.chamadas[1]["messages"], [{"role": "user", "content": "e entao"}])

    def test_historico_por_dispositivo(self):
        api = ClienteFalso([["Oi."], ["Certo."]])
        conversa.definir_cliente(api)
        _responder("oi", device="outro")
        _responder("e entao")
        self.assertEqual(api.chamadas[1]["messages"], [{"role": "user", "content": "e entao"}])

    def test_log_nao_mostra_o_historico(self):
        api = ClienteFalso([["Resposta confidencial um."], ["Resposta confidencial dois."]])
        conversa.definir_cliente(api)
        res, _ = _responder("pergunta confidencial um")
        rapido.perf(res)
        res, _ = _responder("pergunta confidencial dois")
        rapido.perf(res)
        log = self._log.getvalue()
        self.assertIn("[perf] rapido", log)
        self.assertNotIn("confidencial", log)


class RotaBase(_Limpo):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        self.antes = dict(server.state)
        self.simba = SimbaFalso()
        server.state["simba"] = self.simba
        server.state["observer"] = types.SimpleNamespace(enabled=False, available=False)
        server.CONVERSAS.clear()
        conversa.definir_vozes(VOZES)
        conversa.tomar_pedido()
        os.environ["RAPIDO_ATIVO"] = "true"
        self.http = TestClient(server.app)

    def tearDown(self):
        server.CONVERSAS.clear()
        server.state.clear()
        server.state.update(self.antes)
        super().tearDown()

    def _ws(self, recursos="conversa", device="celular"):
        return self.http.websocket_connect(f"/ws?token={TOKEN}&device={device}&recursos={recursos}")

    def _perguntar(self, ws, texto, voice=True, t=1):
        ws.send_json({"type": "message", "text": texto, "voice": voice, "t": t})


class RotaHistorico(RotaBase):
    def test_pergunta_seguinte_leva_o_historico_ao_haiku(self):
        api = ClienteFalso([["Thank you."], ["Merci."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "como se diz obrigado em ingles")
            _ate(ws, _fim_conversa)
            self._perguntar(ws, "e em frances", t=2)
            _ate(ws, _fim_conversa)
        self.assertEqual(api.chamadas[1]["messages"], [
            {"role": "user", "content": "como se diz obrigado em ingles"},
            {"role": "assistant", "content": "Thank you."},
            {"role": "user", "content": "e em frances"},
        ])

    def test_historico_sobrevive_a_reconexao_do_app(self):
        api = ClienteFalso([["Thank you."], ["Merci."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "como se diz obrigado em ingles")
            _ate(ws, _fim_conversa)
        with self._ws() as ws:
            self._perguntar(ws, "e em frances", t=2)
            _ate(ws, _fim_conversa)
        self.assertEqual(len(api.chamadas[1]["messages"]), 3)

    def test_troca_que_foi_ao_agente_nao_entra_no_historico_do_haiku(self):
        api = ClienteFalso([["Oi."], _Fluxo(["Um instante."], ferramenta="escalar_para_agente"), ["Certo."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "oi")
            _ate(ws, _fim_conversa)
            self._perguntar(ws, "qual o melhor jeito de estudar", t=2)
            _ate(ws, lambda e: e.get("type") == "done" and not e.get("conversa"))
            self._perguntar(ws, "obrigado", t=3)
            _ate(ws, _fim_conversa)
        textos = [m["content"] for m in api.chamadas[2]["messages"]]
        self.assertEqual(textos, ["oi", "Oi.", "obrigado"])

    def test_lista_local_nao_mexe_no_historico(self):
        api = ClienteFalso([["Oi."], ["Certo."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "oi")
            _ate(ws, _fim_conversa)
            self._perguntar(ws, "que horas sao", t=2)
            _ate(ws, lambda e: e.get("type") == "done" and not e.get("conversa"))
            self._perguntar(ws, "obrigado", t=3)
            _ate(ws, _fim_conversa)
        self.assertEqual([m["content"] for m in api.chamadas[1]["messages"]], ["oi", "Oi.", "obrigado"])

    def test_rapido_desligado_nada_e_guardado(self):
        os.environ["RAPIDO_ATIVO"] = "false"
        conversa.definir_cliente(ClienteFalso([]))
        with self._ws() as ws:
            self._perguntar(ws, "oi")
            _ate(ws, lambda e: e.get("type") == "done" and not e.get("conversa"))
        self.assertEqual(rapido.recentes(CEL), [])


# ---------- passo 2a: via rapida -> agente (bloco entregue uma unica vez) ----------

def _bloco(*trocas):
    return "[conversa rapida recente: " + "; ".join(f"usuario: {p}; assistente: {r}" for p, r in trocas) + "]"


class PonteParaOAgente(_Limpo):
    def setUp(self):
        super().setUp()
        os.environ["RAPIDO_ATIVO"] = "true"

    def test_sem_trocas_nao_ha_bloco(self):
        self.assertEqual(rapido.tomar_para_agente(CEL, agora=0), "")

    def test_bloco_com_as_trocas_ainda_nao_entregues(self):
        rapido.registrar(CEL, "como se diz obrigado em ingles", "Thank you.", agora=0)
        rapido.registrar(CEL, "e em frances", "Merci.", agora=1)
        self.assertEqual(rapido.tomar_para_agente(CEL, agora=2),
                         _bloco(("como se diz obrigado em ingles", "Thank you."), ("e em frances", "Merci.")))

    def test_entrega_uma_unica_vez(self):
        rapido.registrar(CEL, "oi", "Oi.", agora=0)
        self.assertNotEqual(rapido.tomar_para_agente(CEL, agora=1), "")
        self.assertEqual(rapido.tomar_para_agente(CEL, agora=2), "")
        self.assertEqual(rapido.tomar_para_agente(CEL, agora=3), "")

    def test_troca_nova_depois_da_entrega_leva_so_a_nova(self):
        rapido.registrar(CEL, "oi", "Oi.", agora=0)
        rapido.tomar_para_agente(CEL, agora=1)
        rapido.registrar(CEL, "tudo bem", "Tudo.", agora=2)
        self.assertEqual(rapido.tomar_para_agente(CEL, agora=3), _bloco(("tudo bem", "Tudo.")))

    def test_entregar_ao_agente_nao_tira_do_historico_do_haiku(self):
        rapido.registrar(CEL, "oi", "Oi.", agora=0)
        rapido.tomar_para_agente(CEL, agora=1)
        self.assertEqual(rapido.recentes(CEL, agora=2), [("oi", "Oi.")])

    def test_limite_total_e_as_mais_novas_ficam(self):
        for i in range(3):
            rapido.registrar(CEL, f"pergunta {i} " + "x" * 280, f"resposta {i} " + "y" * 280, agora=i)
        bloco = rapido.tomar_para_agente(CEL, agora=5)
        self.assertLessEqual(len(bloco), rapido.PONTE_MAX)
        self.assertTrue(bloco.startswith("[conversa rapida recente: usuario: pergunta"))
        self.assertTrue(bloco.endswith("]"))
        self.assertIn("pergunta 2", bloco)
        self.assertNotIn("pergunta 0", bloco, "o que nao cabe e o mais antigo")

    def test_troca_unica_enorme_e_cortada_dentro_do_limite(self):
        rapido.registrar(CEL, "p" * 1000, "r" * 1000, agora=0)
        bloco = rapido.tomar_para_agente(CEL, agora=1)
        self.assertLessEqual(len(bloco), rapido.PONTE_MAX)
        self.assertTrue(bloco.endswith("...]"))

    def test_troca_que_nao_coube_conta_como_entregue(self):
        for i in range(3):
            rapido.registrar(CEL, f"pergunta {i} " + "x" * 280, f"resposta {i} " + "y" * 280, agora=i)
        rapido.tomar_para_agente(CEL, agora=5)
        self.assertEqual(rapido.tomar_para_agente(CEL, agora=6), "")

    def test_limite_total_acompanha_a_constante(self):
        antes = rapido.PONTE_MAX
        rapido.PONTE_MAX = 120
        try:
            rapido.registrar(CEL, "a" * 200, "b" * 200, agora=0)
            self.assertLessEqual(len(rapido.tomar_para_agente(CEL, agora=1)), 120)
        finally:
            rapido.PONTE_MAX = antes

    def test_desligada_nao_entrega_nem_marca(self):
        rapido.registrar(CEL, "oi", "Oi.", agora=0)
        os.environ["RAPIDO_ATIVO"] = "false"
        self.assertEqual(rapido.tomar_para_agente(CEL, agora=1), "")
        os.environ["RAPIDO_ATIVO"] = "true"
        self.assertEqual(rapido.tomar_para_agente(CEL, agora=2), _bloco(("oi", "Oi.")))

    def test_historico_expirado_nao_vira_bloco(self):
        rapido.registrar(CEL, "oi", "Oi.", agora=0)
        self.assertEqual(rapido.tomar_para_agente(CEL, agora=rapido.HISTORICO_EXPIRA_S + 1), "")

    def test_dispositivos_nao_se_misturam(self):
        rapido.registrar("outro", "oi", "Oi.", agora=0)
        self.assertEqual(rapido.tomar_para_agente(CEL, agora=1), "")

    def test_troca_que_escalou_nao_entra_no_bloco(self):
        conversa.definir_cliente(ClienteFalso([["Oi."], _Fluxo(["Deixe-me ver."], ferramenta="escalar_para_agente")]))
        _responder("oi")
        _responder("qual o melhor jeito de estudar")
        bloco = rapido.tomar_para_agente(CEL)
        self.assertIn("oi", bloco)
        self.assertNotIn("Deixe-me ver", bloco)
        self.assertNotIn("estudar", bloco)

    def test_nada_vai_para_o_log(self):
        rapido.registrar(CEL, "pergunta secreta", "resposta secreta", agora=0)
        rapido.tomar_para_agente(CEL, agora=1)
        self.assertEqual(self._log.getvalue(), "")


# ---------- passo 2a: o Simba (core.py) injeta o bloco em _compose ----------

core = _carregar("simba.core")
claude_agent_sdk = __import__("claude_agent_sdk")


def _resultado(subtype="success", custo=0.01):
    return claude_agent_sdk.ResultMessage(subtype=subtype, duration_ms=1, duration_api_ms=1, is_error=False,
                                          num_turns=1, session_id="sessao-falsa", total_cost_usd=custo)


def _resposta(texto):
    return claude_agent_sdk.AssistantMessage(content=[claude_agent_sdk.TextBlock(texto)], model="modelo-falso")


class ClienteDoAgente:
    """Faz o papel do ClaudeSDKClient: guarda o que o Simba pergunta e responde com o roteiro (uma lista de
    mensagens por pergunta)."""

    def __init__(self, roteiro=None):
        self.perguntas = []
        self.roteiro = list(roteiro or [])

    async def query(self, texto):
        self.perguntas.append(texto)

    async def receive_response(self):
        for msg in (self.roteiro.pop(0) if self.roteiro else [_resposta("ok"), _resultado()]):
            yield msg


def _simba_real(cliente=None):
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
    s.client = cliente or ClienteDoAgente()

    async def _parar():
        s._connected = False

    s._build = lambda: None
    s.stop = _parar
    s.start = lambda: asyncio.sleep(0)
    return s


class AgenteRecebeABonte(_Limpo):
    def setUp(self):
        super().setUp()
        os.environ["RAPIDO_ATIVO"] = "true"
        self._autorizadas, self._mudou = core.authorized, core.CHANGED["flag"]
        core.authorized = lambda: []
        core.CHANGED["flag"] = False

    def tearDown(self):
        core.authorized = self._autorizadas
        core.CHANGED["flag"] = self._mudou
        super().tearDown()

    def _perguntar(self, simba, texto="que horas sao"):
        async def rodar():
            return [ev async for ev in simba.ask(texto)]
        return asyncio.run(rodar())

    def test_proximo_ask_recebe_o_bloco_uma_vez(self):
        rapido.registrar(CEL, "como se diz obrigado em ingles", "Thank you.")
        simba = _simba_real()
        self._perguntar(simba)
        self._perguntar(simba)
        bloco = _bloco(("como se diz obrigado em ingles", "Thank you."))
        primeira, segunda = simba.client.perguntas
        self.assertEqual(primeira.count(bloco), 1)
        self.assertTrue(primeira.endswith("que horas sao"), "o pedido do usuario continua por ultimo")
        self.assertNotIn("conversa rapida", segunda)

    def test_sem_trocas_rapidas_nao_injeta_nada(self):
        simba = _simba_real()
        self._perguntar(simba)
        self.assertNotIn("conversa rapida", simba.client.perguntas[0])

    def test_o_bloco_e_uma_linha_propria_antes_do_pedido(self):
        rapido.registrar(CEL, "oi", "Oi.")
        simba = _simba_real()
        self._perguntar(simba)
        linhas = simba.client.perguntas[0].splitlines()
        self.assertTrue(linhas[0].startswith("[agora:"))
        self.assertEqual(linhas[1], _bloco(("oi", "Oi.")))
        self.assertEqual(linhas[-1], "que horas sao")

    def test_convive_com_o_assunto_anterior_do_reset_de_sessao(self):
        rapido.registrar(CEL, "oi", "Oi.")
        simba = _simba_real()
        simba._bridge = "Pergunta: a Resposta: b"
        self._perguntar(simba)
        pergunta = simba.client.perguntas[0]
        self.assertIn("[assunto anterior: Pergunta: a Resposta: b]", pergunta)
        self.assertIn(_bloco(("oi", "Oi.")), pergunta)

    def test_rapido_desligado_nada_muda_no_agente(self):
        rapido.registrar(CEL, "oi", "Oi.")
        os.environ["RAPIDO_ATIVO"] = "false"
        simba = _simba_real()
        self._perguntar(simba)
        self.assertNotIn("conversa rapida", simba.client.perguntas[0])
        self.assertEqual(simba.client.perguntas[0].count("\n"), 1, "so a linha [agora] e o pedido, como antes")

    def test_reenvio_depois_do_teto_de_custo_leva_o_bloco_de_novo(self):
        rapido.registrar(CEL, "oi", "Oi.")
        cliente = ClienteDoAgente([[_resultado("error_max_budget_usd", custo=99.0)], [_resposta("ok"), _resultado()]])
        simba = _simba_real(cliente)
        self._perguntar(simba)
        self.assertEqual(len(cliente.perguntas), 2)
        for pergunta in cliente.perguntas:
            self.assertEqual(pergunta.count(_bloco(("oi", "Oi."))), 1)
        self.assertEqual(rapido.tomar_para_agente(CEL), "", "e continua entregue so uma vez")

    def test_bloco_nao_vaza_para_o_ultimo_assunto_do_agente(self):
        # _last_user alimenta o assunto anterior e o resumo que o Haiku le: so o pedido do usuario entra.
        rapido.registrar(CEL, "oi", "Oi.")
        simba = _simba_real()
        self._perguntar(simba, "que horas sao")
        self.assertEqual(simba._last_user, "que horas sao")
        self.assertNotIn("conversa rapida", simba._topic_summary())


# ---------- passo 2b: agente -> Haiku (resumo curto no prompt) ----------

class ResumoDoAgenteNoPrompt(_Limpo):
    P = {"nome_usuario": "Bruno", "nome_tutor": "Simba"}

    def test_sem_resumo_nao_ha_bloco(self):
        for vazio in ("", None, "   \n "):
            texto = rapido.prompt_sistema(self.P, agora="agora", contexto_agente=vazio)
            self.assertNotIn("Contexto recente do agente", texto)
        self.assertEqual(rapido.prompt_sistema(self.P, agora="agora"),
                         rapido.prompt_sistema(self.P, agora="agora", contexto_agente=""))

    def test_com_resumo_entra_no_bloco(self):
        texto = rapido.prompt_sistema(self.P, agora="agora", contexto_agente="Pergunta: a Resposta: b")
        self.assertIn("Contexto recente do agente: Pergunta: a Resposta: b", texto)

    def test_resumo_e_truncado(self):
        texto = rapido.prompt_sistema(self.P, agora="agora", contexto_agente="palavra " * 200)
        bloco = texto.split("Contexto recente do agente: ", 1)[1]
        self.assertLessEqual(len(bloco.splitlines()[0]), rapido.CONTEXTO_AGENTE_MAX)
        self.assertIn("...", bloco.splitlines()[0])

    def test_resumo_vira_uma_linha(self):
        texto = rapido.prompt_sistema(self.P, agora="agora", contexto_agente="linha um\n\nlinha  dois")
        self.assertIn("Contexto recente do agente: linha um linha dois", texto)

    def test_regras_de_antes_continuam(self):
        texto = rapido.prompt_sistema(self.P, agora="agora", contexto_agente="x")
        for pedaco in ("escalar_para_agente", "NUNCA", "ANTES", "Bruno"):
            self.assertIn(pedaco, texto)
        for proibido in ("Notas", "notas", "MEMORIA", "load_context"):
            self.assertNotIn(proibido, texto)

    def test_responder_manda_o_resumo_no_prompt_do_haiku(self):
        api = ClienteFalso([["Oi."]])
        conversa.definir_cliente(api)
        _responder("e em ingles", contexto_agente="Pergunta: a Resposta: b")
        self.assertIn("Contexto recente do agente: Pergunta: a Resposta: b", api.chamadas[0]["system"][0]["text"])

    def test_responder_sem_resumo_nao_tem_bloco(self):
        api = ClienteFalso([["Oi."]])
        conversa.definir_cliente(api)
        _responder("e em ingles")
        self.assertNotIn("Contexto recente do agente", api.chamadas[0]["system"][0]["text"])


class SimbaComResumo(SimbaFalso):
    """SimbaFalso que sabe resumir o ultimo assunto, como o Simba real (_topic_summary)."""

    def __init__(self, resumo=""):
        super().__init__()
        self.resumo = resumo

    def _topic_summary(self):
        return self.resumo


class RotaPonte(RotaBase):
    def _agente(self, simba):
        server.state["simba"] = simba
        return simba

    def _prompt_do_haiku(self, api):
        return api.chamadas[-1]["system"][0]["text"]

    # --- agente -> Haiku ---

    def test_prompt_do_haiku_leva_o_resumo_do_agente(self):
        self._agente(SimbaComResumo("Pergunta: agenda de sexta Resposta: tres reunioes"))
        api = ClienteFalso([["Certo."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "e depois dela")
            _ate(ws, _fim_conversa)
        self.assertIn("Contexto recente do agente: Pergunta: agenda de sexta Resposta: tres reunioes",
                      self._prompt_do_haiku(api))

    def test_resumo_vazio_omite_o_bloco(self):
        self._agente(SimbaComResumo(""))
        api = ClienteFalso([["Certo."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "e depois dela")
            _ate(ws, _fim_conversa)
        self.assertNotIn("Contexto recente do agente", self._prompt_do_haiku(api))

    def test_simba_sem_resumo_ou_com_erro_nao_derruba_a_via_rapida(self):
        class SimbaQuebrado(SimbaFalso):
            def _topic_summary(self):
                raise RuntimeError("falha simulada")

        for simba in (SimbaFalso(), SimbaQuebrado()):
            self._agente(simba)
            api = ClienteFalso([["Certo."]])
            conversa.definir_cliente(api)
            with self._ws() as ws:
                self._perguntar(ws, "e depois dela")
                eventos = _ate(ws, _fim_conversa)
            self.assertEqual([e["text"] for e in eventos if e["type"] == "frase"], ["Certo."])
            self.assertNotIn("Contexto recente do agente", self._prompt_do_haiku(api))

    def test_resumo_e_limitado_e_sem_a_marca_de_voz(self):
        bruto = "Pergunta: [por voz: 1 ou 2 frases, sem markdown, pronto para falar] " + "assunto " * 100
        self._agente(SimbaComResumo(bruto[:400]))
        api = ClienteFalso([["Certo."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "e depois")
            _ate(ws, _fim_conversa)
        linha = next(l for l in self._prompt_do_haiku(api).splitlines() if "Contexto recente do agente" in l)
        resumo = linha.split("Contexto recente do agente: ", 1)[1]
        self.assertLessEqual(len(resumo), rapido.CONTEXTO_AGENTE_MAX)
        self.assertNotIn("por voz", resumo)
        self.assertIn("assunto", resumo)

    def test_haiku_nunca_le_a_memoria_nem_as_notas(self):
        import simba.memory as memory
        chamou = []
        original = memory.load_context
        memory.load_context = lambda *a, **k: chamou.append(1) or "NOTAS SECRETAS"
        try:
            self._agente(SimbaComResumo("Pergunta: a Resposta: b"))
            api = ClienteFalso([["Certo."]])
            conversa.definir_cliente(api)
            with self._ws() as ws:
                self._perguntar(ws, "e depois")
                _ate(ws, _fim_conversa)
        finally:
            memory.load_context = original
        self.assertEqual(chamou, [])
        self.assertNotIn("NOTAS SECRETAS", self._prompt_do_haiku(api))

    def test_resumo_nao_aparece_no_log(self):
        self._agente(SimbaComResumo("Pergunta: assunto sigiloso Resposta: dado sigiloso"))
        conversa.definir_cliente(ClienteFalso([["Certo."]]))
        with self._ws() as ws:
            self._perguntar(ws, "e depois")
            _ate(ws, _fim_conversa)
        self.assertNotIn("sigiloso", self._log.getvalue())

    # --- via rapida -> agente, pelo caminho normal do servidor ---

    def _ate_o_agente(self, ws):
        return _ate(ws, lambda e: e.get("type") == "done" and not e.get("conversa"))

    def _agente_real(self, roteiro=None):
        cliente = ClienteDoAgente(roteiro)
        simba = _simba_real(cliente)
        server.state["simba"] = simba
        return cliente

    def test_agente_recebe_o_bloco_uma_vez_e_o_hud_nao_ve(self):
        cliente = self._agente_real()
        conversa.definir_cliente(ClienteFalso([["Thank you."]]))
        with self._ws() as ws:
            self._perguntar(ws, "como se diz obrigado em ingles")
            _ate(ws, _fim_conversa)
            self._perguntar(ws, "que horas sao", t=2)
            eventos = self._ate_o_agente(ws)
            self._perguntar(ws, "que horas sao de novo", t=3)
            eventos2 = self._ate_o_agente(ws)
        bloco = _bloco(("como se diz obrigado em ingles", "Thank you."))
        self.assertEqual(len(cliente.perguntas), 2)
        self.assertEqual(cliente.perguntas[0].count(bloco), 1)
        self.assertNotIn("conversa rapida", cliente.perguntas[1])
        for evs, texto in ((eventos, "que horas sao"), (eventos2, "que horas sao de novo")):
            user = next(e for e in evs if e["type"] == "user")
            self.assertEqual(user["text"], texto, "o HUD ve so o que o usuario disse")
            self.assertNotIn("conversa rapida", json_texto(evs))

    def test_escalada_leva_o_bloco_e_a_linha_do_que_ja_foi_dito_sem_repetir(self):
        cliente = self._agente_real()
        conversa.definir_cliente(ClienteFalso([["Oi, tudo bem."],
                                               _Fluxo(["Deixe-me ver."], ferramenta="escalar_para_agente")]))
        with self._ws() as ws:
            self._perguntar(ws, "oi")
            _ate(ws, _fim_conversa)
            self._perguntar(ws, "qual o melhor jeito de estudar para uma prova", t=2)
            eventos = self._ate_o_agente(ws)
        recebido, = cliente.perguntas
        self.assertEqual(recebido.count(_bloco(("oi", "Oi, tudo bem."))), 1)
        self.assertEqual(recebido.count("Deixe-me ver."), 1, "o que a via rapida acabou de dizer aparece so na linha propria")
        self.assertTrue(recebido.endswith("[o assistente ja disse: Deixe-me ver.]"))
        user = next(e for e in eventos if e["type"] == "user")
        self.assertEqual(user["text"], "qual o melhor jeito de estudar para uma prova")

    def test_escalada_sem_trocas_anteriores_nao_injeta_bloco(self):
        cliente = self._agente_real()
        conversa.definir_cliente(ClienteFalso([_Fluxo(["Deixe-me ver."], ferramenta="escalar_para_agente")]))
        with self._ws() as ws:
            self._perguntar(ws, "qual o melhor jeito de estudar para uma prova")
            self._ate_o_agente(ws)
        self.assertNotIn("conversa rapida", cliente.perguntas[0])

    def test_via_rapida_depois_do_agente_enxerga_o_que_o_agente_fez(self):
        cliente = self._agente_real([[_resposta("Sua agenda de sexta tem tres reunioes."), _resultado()]])
        api = ClienteFalso([["Certo."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "o que tem na minha agenda", t=1)       # lista local -> agente
            self._ate_o_agente(ws)
            self._perguntar(ws, "e depois dela", t=2)                    # via rapida
            _ate(ws, _fim_conversa)
        resumo = next(l for l in self._prompt_do_haiku(api).splitlines() if "Contexto recente do agente" in l)
        self.assertIn("o que tem na minha agenda", resumo)
        self.assertIn("tres reunioes", resumo)
        self.assertNotIn("por voz", resumo)
        self.assertLessEqual(len(resumo.split(": ", 1)[1]), rapido.CONTEXTO_AGENTE_MAX)


def json_texto(eventos) -> str:
    import json
    return json.dumps(eventos, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
