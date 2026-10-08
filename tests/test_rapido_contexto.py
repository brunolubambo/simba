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


if __name__ == "__main__":
    unittest.main()
