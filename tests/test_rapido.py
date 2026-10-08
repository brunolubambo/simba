"""Via rapida: lista local, prompt minimo, variaveis de ambiente e contadores. Sem rede.

Frases e valores falsos de proposito.
"""
import contextlib
import io
import os
import types
import unittest

try:  # `discover -s tests` (modulo de topo) ou `unittest tests.test_rapido`
    from test_conversa import (_carregar, _ate, _fim_conversa, ClienteFalso, SimbaFalso, _Fluxo, VOZES, TOKEN)
except ImportError:  # pragma: no cover
    from tests.test_conversa import (_carregar, _ate, _fim_conversa, ClienteFalso, SimbaFalso, _Fluxo, VOZES, TOKEN)

rapido = _carregar("simba.rapido")
conversa = _carregar("simba.conversa")
server = _carregar("simba.server")

VARIAVEIS = ("RAPIDO_ATIVO", "RAPIDO_MODEL", "RAPIDO_MAX_TOKENS", "RAPIDO_TIMEOUT_S", "CONVERSA_MODEL")


class _Ambiente(unittest.TestCase):
    def setUp(self):
        self._env = {v: os.environ.get(v) for v in VARIAVEIS}
        for v in VARIAVEIS:
            os.environ.pop(v, None)

    def tearDown(self):
        for v, valor in self._env.items():
            if valor is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = valor


class ListaLocal(unittest.TestCase):
    VAO_AO_AGENTE = [
        "que horas são", "Que hora é agora?", "qual a data de hoje", "o que tem na minha agenda amanhã",
        "como está o clima", "vai chover? qual a previsão", "qual a temperatura", "me lembre de ligar pro João",
        "me lembra de comprar pão", "anota aí: comprar leite", "acorde-me às seis", "abra o telegram",
        "abre o WhatsApp", "feche a janela", "ligue o computador", "desligue a tela", "toca uma música",
        "mande uma mensagem pra Ana", "envie um e-mail pro chefe", "manda um email", "pesquise sobre Python",
        "busque o endereço", "procure o arquivo", "qual o preço do café", "quanto está o dólar", "cotação do euro",
        "últimas notícias", "minha rotina de hoje", "minhas tarefas", "tira uma foto", "abre a câmera",
        "quais os arquivos da pasta", "meu nome é Bruno", "meus compromissos", "você lembra que eu disse isso",
        "o que eu disse ontem", "tem reunião essa semana", "crie um alarme", "põe um timer de cinco minutos",
        "inicia o cronômetro", "tem algum evento", "qual o tempo", "que tempo faz lá fora",
        "vamos praticar inglês", "quero treinar francês", "simule uma entrevista", "vamos conversar em japonês",
        "QUE HORAS SAO", "AMANHÃ cedo", "preciso de um despertador", "olha o placar do jogo",
        "", "   ",
    ]
    FICAM_NA_VIA_RAPIDA = [
        "bom dia", "oi, tudo bem?", "obrigado", "como se diz obrigado em francês", "traduz where is the bathroom",
        "quanto é quinze vezes três", "me explica o que é inflação", "conta uma piada", "qual a capital da França",
        "o que significa a palavra efêmero", "fala mais devagar", "você é inteligente?", "boa noite",
        "dá uma dica de como estudar melhor", "ahora vamos a ver", "como se escreve exceção", "qual o plural de cidadão",
        "o que é um buraco negro", "rima com amor", "me diga um sinônimo de feliz",
    ]

    def test_pedidos_que_precisam_do_agente(self):
        for frase in self.VAO_AO_AGENTE:
            with self.subTest(frase=frase):
                self.assertTrue(rapido.vai_direto_ao_agente(frase))

    def test_pedidos_simples_ficam_na_via_rapida(self):
        for frase in self.FICAM_NA_VIA_RAPIDA:
            with self.subTest(frase=frase):
                self.assertFalse(rapido.vai_direto_ao_agente(frase))

    def test_palavra_inteira_nao_casa_dentro_de_outra(self):
        # "hora" dentro de "ahora", "pc" dentro de "pcs"-like e "data" dentro de "dados" nao contam
        self.assertFalse(rapido.vai_direto_ao_agente("ahora si"))
        self.assertFalse(rapido.vai_direto_ao_agente("nos dados do estudo"))
        self.assertFalse(rapido.vai_direto_ao_agente("agoraphobia"))

    def test_acento_e_caixa_nao_importam(self):
        for a, b in (("reunião", "reuniao"), ("REUNIÃO", "reuniao"), ("amanhã", "amanha"), ("Previsão", "previsao"),
                     ("câmera", "camera"), ("cotação", "cotacao"), ("e-mail", "E-MAIL")):
            self.assertTrue(rapido.vai_direto_ao_agente(a), a)
            self.assertTrue(rapido.vai_direto_ao_agente(b), b)

    def test_plural_simples(self):
        for frase in ("meus emails", "os lembretes", "tem alarmes", "as fotos", "os preços"):
            self.assertTrue(rapido.vai_direto_ao_agente(frase), frase)

    def test_lista_e_facil_de_editar(self):
        self.assertIsInstance(rapido.DIRETO_AO_AGENTE, tuple)
        self.assertIn("hora", rapido.DIRETO_AO_AGENTE)
        self.assertIn("o que eu disse", rapido.DIRETO_AO_AGENTE)


class Prompt(unittest.TestCase):
    def test_sem_notas_e_sem_memoria(self):
        p = {"nome_usuario": "Bruno", "idioma_nativo": "português", "fuso": "America/Sao_Paulo", "nome_tutor": "Simba"}
        texto = rapido.prompt_sistema(p, agora="quinta-feira, 08/10/2026 10:00")
        self.assertIn("Simba", texto)
        self.assertIn("Bruno", texto)
        self.assertIn("quinta-feira, 08/10/2026 10:00", texto)
        self.assertIn("escalar_para_agente", texto)
        self.assertIn("ANTES", texto)
        self.assertIn("NUNCA", texto)
        for proibido in ("Notas", "notas", "MEMORIA", "load_context"):
            self.assertNotIn(proibido, texto)

    def test_nao_consulta_memoria_do_agente(self):
        import simba.memory as memory
        chamou = []
        original = memory.load_context
        memory.load_context = lambda *a, **k: chamou.append(1) or "NOTAS SECRETAS"
        try:
            texto = rapido.prompt_sistema({"nome_usuario": "Ana", "nome_tutor": "Simba"}, agora="agora")
        finally:
            memory.load_context = original
        self.assertEqual(chamou, [])
        self.assertNotIn("NOTAS SECRETAS", texto)

    def test_sem_perfil_usa_padrao_e_hora_atual(self):
        texto = rapido.prompt_sistema({}, agora=None)
        self.assertIn("Simba", texto)
        self.assertIn("Agora:", texto)

    def test_ferramenta_sem_parametro_obrigatorio(self):
        f = rapido.FERRAMENTA
        self.assertEqual(f["name"], "escalar_para_agente")
        self.assertEqual(f["input_schema"]["type"], "object")
        self.assertEqual(f["input_schema"]["required"], [])
        self.assertIn("motivo", f["input_schema"]["properties"])


class Configuracao(_Ambiente):
    def test_desligada_por_padrao(self):
        self.assertFalse(rapido.ativo())

    def test_liga_e_desliga_pelo_ambiente_sem_recarregar(self):
        for valor, esperado in (("true", True), ("TRUE", True), ("1", True), ("sim", True), ("false", False),
                                ("", False), ("nao", False), ("talvez", False)):
            os.environ["RAPIDO_ATIVO"] = valor
            self.assertEqual(rapido.ativo(), esperado, valor)

    def test_modelo_cai_no_da_conversa(self):
        self.assertEqual(rapido.modelo(), conversa.MODEL)
        os.environ["CONVERSA_MODEL"] = "modelo-da-conversa"
        self.assertEqual(rapido.modelo(), "modelo-da-conversa")
        os.environ["RAPIDO_MODEL"] = "modelo-rapido"
        self.assertEqual(rapido.modelo(), "modelo-rapido")
        os.environ["RAPIDO_MODEL"] = "   "
        self.assertEqual(rapido.modelo(), "modelo-da-conversa")

    def test_limites_com_padrao_e_valor_invalido(self):
        self.assertEqual(rapido.max_tokens(), 200)
        self.assertEqual(rapido.timeout_s(), 6.0)
        os.environ["RAPIDO_MAX_TOKENS"] = "80"
        os.environ["RAPIDO_TIMEOUT_S"] = "2.5"
        self.assertEqual(rapido.max_tokens(), 80)
        self.assertEqual(rapido.timeout_s(), 2.5)
        os.environ["RAPIDO_MAX_TOKENS"] = "abc"
        os.environ["RAPIDO_TIMEOUT_S"] = "-1"
        self.assertEqual(rapido.max_tokens(), 200)
        self.assertEqual(rapido.timeout_s(), 6.0)


class Contadores(_Ambiente):
    def test_contar_soma_tokens_e_ignora_lixo(self):
        antes = dict(rapido.RAPIDO_USO)
        rapido.contar(types.SimpleNamespace(input_tokens=10, output_tokens=5, cache_creation_input_tokens=None,
                                            cache_read_input_tokens=7))
        rapido.contar(None)
        rapido.contar(types.SimpleNamespace(input_tokens="x", output_tokens=True))
        self.assertEqual(rapido.RAPIDO_USO["tokens_entrada"], antes["tokens_entrada"] + 17)
        self.assertEqual(rapido.RAPIDO_USO["tokens_saida"], antes["tokens_saida"] + 5)

    def test_uso_tem_todos_os_campos(self):
        u = rapido.uso()
        for campo in ("rapidas", "escaladas_haiku", "escaladas_lista", "falhas", "tokens_entrada", "tokens_saida",
                      "ativo", "modelo"):
            self.assertIn(campo, u)
        self.assertFalse(u["ativo"])


# ---------- rota do websocket ----------

def _fim_do_agente(ev):
    return ev.get("type") == "done" and not ev.get("conversa")


class Rota(_Ambiente):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        self.antes = dict(server.state)
        self.contadores = dict(rapido.RAPIDO_USO)
        rapido.limpar(rapido.DISPOSITIVO)        # historico da via rapida e estado do processo: cada teste comeca limpo
        self.simba = SimbaFalso()
        server.state["simba"] = self.simba
        server.state["observer"] = types.SimpleNamespace(enabled=False, available=False)
        server.CONVERSAS.clear()
        conversa.definir_vozes(VOZES)
        conversa.tomar_pedido()
        os.environ["RAPIDO_ATIVO"] = "true"
        self.http = TestClient(server.app)
        self.saida = io.StringIO()
        self._log = contextlib.redirect_stdout(self.saida)
        self._log.__enter__()

    def tearDown(self):
        self._log.__exit__(None, None, None)
        conversa.definir_cliente(None)
        server.CONVERSAS.clear()
        server.state.clear()
        server.state.update(self.antes)
        super().tearDown()

    def _ws(self, recursos="conversa", device="celular"):
        return self.http.websocket_connect(f"/ws?token={TOKEN}&device={device}&recursos={recursos}")

    def _delta(self, campo):
        return rapido.RAPIDO_USO[campo] - self.contadores[campo]

    def _perguntar(self, ws, texto, voice=True, t=1):
        ws.send_json({"type": "message", "text": texto, "voice": voice, "t": t})

    # --- via rapida ---

    def test_so_texto_responde_frase_a_frase_sem_chamar_o_agente(self):
        api = ClienteFalso([["Boa tarde. Em que", " posso ajudar?"]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "boa tarde")
            eventos = _ate(ws, _fim_conversa)
        self.assertIn({"type": "ack", "t": 1}, eventos)
        eventos = [e for e in eventos if e["type"] != "status"]
        frases = [e for e in eventos if e["type"] == "frase"]
        self.assertEqual([f["text"] for f in frases], ["Boa tarde.", "Em que posso ajudar?"])
        self.assertEqual({(f["idioma"], f["voz"]) for f in frases}, {("pt-BR", server.VOICE)})
        self.assertEqual(eventos[-1], {"type": "done", "conversa": True})
        self.assertNotIn("encaminhado", eventos[-1])
        self.assertEqual(self.simba.recebidos, [], "o agente completo nao pode ser chamado")
        self.assertEqual({e["type"] for e in eventos}, {"ack", "frase", "done"})
        self.assertEqual(self._delta("rapidas"), 1)
        chamada = api.chamadas[0]
        self.assertEqual(chamada["model"], rapido.modelo())
        self.assertEqual(chamada["max_tokens"], 200)
        self.assertEqual([t["name"] for t in chamada["tools"]], ["escalar_para_agente"])
        self.assertEqual(chamada["messages"], [{"role": "user", "content": "boa tarde"}])
        self.assertNotIn("Notas", chamada["system"][0]["text"])

    def test_resposta_vai_so_para_o_socket_que_perguntou(self):
        conversa.definir_cliente(ClienteFalso([["Tudo bem."]]))
        with self._ws() as ws1, self._ws(recursos="", device="pc") as ws2:
            self._perguntar(ws1, "tudo bem?")
            _ate(ws1, _fim_conversa)
            ws2.send_json({"type": "ping", "t": 9})
            eventos = _ate(ws2, lambda e: e.get("type") == "pong")
        self.assertFalse([e for e in eventos if e["type"] in ("frase", "done", "text", "user")])

    def test_lista_local_vai_ao_agente_sem_chamar_o_haiku(self):
        api = ClienteFalso([])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "que horas são")
            eventos = _ate(ws, _fim_do_agente)
        self.assertFalse([e for e in eventos if e["type"] == "frase"])
        self.assertEqual(len(self.simba.recebidos), 1)
        self.assertEqual(api.chamadas, [])
        self.assertEqual(self._delta("escaladas_lista"), 1)

    def test_sem_o_recurso_conversa_nunca_entra(self):
        api = ClienteFalso([])
        conversa.definir_cliente(api)
        for recursos, device in (("", "celular"), ("conversa", "pc"), ("", "pc")):
            with self._ws(recursos=recursos, device=device) as ws:
                self._perguntar(ws, "boa tarde")
                eventos = _ate(ws, _fim_do_agente)
            self.assertFalse([e for e in eventos if e["type"] == "frase"], (recursos, device))
        self.assertEqual(len(self.simba.recebidos), 3)
        self.assertEqual(api.chamadas, [])
        self.assertEqual(self._delta("escaladas_lista"), 0, "so conta quando o celular com conversa poderia usar a via")

    def test_desligada_nada_muda(self):
        for valor in (None, "false"):
            if valor is None:
                os.environ.pop("RAPIDO_ATIVO", None)
            else:
                os.environ["RAPIDO_ATIVO"] = valor
            api = ClienteFalso([])
            conversa.definir_cliente(api)
            with self._ws() as ws:
                self._perguntar(ws, "boa tarde")
                eventos = _ate(ws, _fim_do_agente)
            self.assertFalse([e for e in eventos if e["type"] == "frase"])
            self.assertEqual(api.chamadas, [])
        self.assertEqual(len(self.simba.recebidos), 2)
        self.assertEqual(self._delta("escaladas_lista"), 0)
        self.assertEqual(self._delta("rapidas"), 0)

    def test_pedido_detalhado_voice_false_vai_ao_agente(self):
        api = ClienteFalso([])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "explique a revolucao francesa", voice=False)
            _ate(ws, _fim_do_agente)
        self.assertEqual(len(self.simba.recebidos), 1)
        self.assertEqual(api.chamadas, [])

    def test_modo_conversa_continua_igual(self):
        api = ClienteFalso([["Bonjour !"], ["Oui."]])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._perguntar(ws, "quero praticar francês")
            _ate(ws, _fim_conversa)
            self._perguntar(ws, "bonjour", t=2)
            eventos = _ate(ws, _fim_conversa)
        self.assertEqual([e["text"] for e in eventos if e["type"] == "frase"], ["Oui."])
        self.assertNotIn("tools", api.chamadas[1])
        self.assertEqual(self._delta("rapidas"), 0)

    # --- escalada e falhas ---

    def _escalada(self, ws, texto="qual o melhor jeito de estudar para uma prova"):
        self._perguntar(ws, texto)
        eventos = [e for e in _ate(ws, _fim_do_agente) if e["type"] != "status"]
        return eventos, [e["type"] for e in eventos]

    def test_haiku_chama_a_ferramenta_antes_do_texto(self):
        api = ClienteFalso([_Fluxo([], ferramenta=("escalar_para_agente", {"motivo": "precisa de dado"}))])
        conversa.definir_cliente(api)
        pedido = "qual o melhor jeito de estudar para uma prova"
        with self._ws() as ws:
            eventos, tipos = self._escalada(ws, pedido)
        frases = [e for e in eventos if e["type"] == "frase"]
        self.assertEqual([f["text"] for f in frases], ["Um momento, vou verificar."])
        self.assertEqual((frases[0]["idioma"], frases[0]["voz"]), ("pt-BR", server.VOICE))
        dones = [e for e in eventos if e["type"] == "done"]
        self.assertEqual(dones[0], {"type": "done", "conversa": True, "encaminhado": True})
        self.assertNotIn("conversa", dones[1])
        self.assertLess(tipos.index("frase"), tipos.index("done"))
        self.assertLess(tipos.index("done"), tipos.index("text"))
        self.assertEqual(len(self.simba.recebidos), 1)
        self.assertTrue(self.simba.recebidos[0].startswith("[por voz:"))
        self.assertTrue(self.simba.recebidos[0].endswith(pedido), "sem frase dita, nao ha o que avisar ao agente")
        self.assertEqual(self._delta("escaladas_haiku"), 1)
        self.assertEqual(self._delta("falhas"), 0)
        self.assertEqual(self._delta("rapidas"), 0)

    def test_escalada_depois_de_uma_frase_mantem_a_frase_e_avisa_o_agente(self):
        api = ClienteFalso([_Fluxo(["Deixe-me ver. Um instante"], ferramenta="escalar_para_agente")])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            eventos, _ = self._escalada(ws)
        self.assertEqual([e["text"] for e in eventos if e["type"] == "frase"], ["Deixe-me ver.", "Um instante"])
        self.assertNotIn("Um momento", " ".join(e.get("text", "") for e in eventos))
        self.assertEqual([e for e in eventos if e["type"] == "done"][0],
                         {"type": "done", "conversa": True, "encaminhado": True})
        recebido = self.simba.recebidos[0]
        self.assertIn("qual o melhor jeito de estudar para uma prova", recebido)
        self.assertTrue(recebido.endswith("[o assistente ja disse: Deixe-me ver. Um instante]"))
        user = next(e for e in eventos if e["type"] == "user")
        self.assertEqual(user["text"], "qual o melhor jeito de estudar para uma prova", "o HUD nao ve a linha de contexto")

    def test_contexto_repassado_e_truncado(self):
        longa = ("palavra " * 60).strip() + "."
        api = ClienteFalso([_Fluxo([longa, " resto"], ferramenta="escalar_para_agente")])
        conversa.definir_cliente(api)
        with self._ws() as ws:
            self._escalada(ws)
        linha = self.simba.recebidos[0].splitlines()[-1]
        self.assertTrue(linha.startswith("[o assistente ja disse: palavra"))
        self.assertTrue(linha.endswith("...]"))
        self.assertLessEqual(len(linha), len("[o assistente ja disse: ") + rapido.CONTEXTO_MAX + len("...]"))

    def test_excecao_da_api_escala_sem_travar(self):
        conversa.definir_cliente(ClienteFalso([RuntimeError("falha simulada SEGREDO-NA-EXCECAO")]))
        with self._ws() as ws:
            eventos, _ = self._escalada(ws)
        self.assertEqual([e["text"] for e in eventos if e["type"] == "frase"], ["Um momento, vou verificar."])
        self.assertTrue([e for e in eventos if e["type"] == "done"][0]["encaminhado"])
        self.assertEqual(len(self.simba.recebidos), 1)
        self.assertEqual(self._delta("falhas"), 1)
        log = self.saida.getvalue()
        self.assertIn("[rapido] falha (RuntimeError)", log)
        self.assertNotIn("SEGREDO-NA-EXCECAO", log)

    def test_timeout_escala(self):
        os.environ["RAPIDO_TIMEOUT_S"] = "0.2"
        conversa.definir_cliente(ClienteFalso([_Fluxo(["lento"], demora=1.0)]))
        with self._ws() as ws:
            eventos, _ = self._escalada(ws)
        self.assertEqual([e["text"] for e in eventos if e["type"] == "frase"], ["Um momento, vou verificar."])
        self.assertEqual(len(self.simba.recebidos), 1)
        self.assertEqual(self._delta("falhas"), 1)
        self.assertIn("[rapido] falha (TimeoutError)", self.saida.getvalue())

    def test_timeout_depois_de_uma_frase_mantem_a_frase(self):
        os.environ["RAPIDO_TIMEOUT_S"] = "0.45"
        conversa.definir_cliente(ClienteFalso([_Fluxo(["Primeira frase. Segunda", " lenta"], demora=0.3)]))
        with self._ws() as ws:
            eventos, _ = self._escalada(ws)
        self.assertEqual([e["text"] for e in eventos if e["type"] == "frase"], ["Primeira frase."])
        self.assertTrue(self.simba.recebidos[0].endswith("[o assistente ja disse: Primeira frase.]"))
        self.assertEqual(self._delta("falhas"), 1)

    def test_resposta_vazia_escala(self):
        conversa.definir_cliente(ClienteFalso([[]]))
        with self._ws() as ws:
            eventos, _ = self._escalada(ws)
        self.assertEqual([e["text"] for e in eventos if e["type"] == "frase"], ["Um momento, vou verificar."])
        self.assertEqual(len(self.simba.recebidos), 1)
        self.assertEqual(self._delta("falhas"), 1)

    def test_sem_chave_da_api_escala(self):
        conversa.definir_cliente(None)
        antes = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self._ws() as ws:
                eventos, _ = self._escalada(ws)
        finally:
            if antes is not None:
                os.environ["ANTHROPIC_API_KEY"] = antes
        self.assertEqual([e["text"] for e in eventos if e["type"] == "frase"], ["Um momento, vou verificar."])
        self.assertEqual(len(self.simba.recebidos), 1)
        self.assertEqual(self._delta("falhas"), 1)

    def test_app_desconectado_no_meio_nao_chama_o_agente(self):
        class SocketMorto:
            async def send_json(self, ev):
                raise RuntimeError("socket fechado")

        import asyncio
        for roteiro in ([["Oi."]], [_Fluxo([], ferramenta="escalar_para_agente")], [RuntimeError("x")]):
            conversa.definir_cliente(ClienteFalso(roteiro))
            asyncio.run(server.via_rapida(SocketMorto(), "celular", "boa tarde"))
        self.assertEqual(self.simba.recebidos, [])

    # --- logs ---

    def test_log_por_turno_sem_texto(self):
        conversa.definir_cliente(ClienteFalso([["Boa tarde, doutor. Em que posso ajudar?"]]))
        with self._ws() as ws:
            self._perguntar(ws, "boa tarde, preciso de uma resposta secreta")
            _ate(ws, _fim_conversa)
        log = self.saida.getvalue()
        linhas = [l for l in log.splitlines() if "rapido" in l]
        self.assertTrue(any(l.startswith("[perf] rapido primeira_frase=") and "escalou=nao frases=2 chars=" in l
                            for l in linhas), linhas)
        for texto in ("Boa tarde", "doutor", "posso ajudar", "secreta", "preciso"):
            self.assertNotIn(texto, log)

    def test_log_da_escalada_informa_o_motivo_sem_texto(self):
        conversa.definir_cliente(ClienteFalso([_Fluxo(["Deixe-me ver."], ferramenta="escalar_para_agente")]))
        with self._ws() as ws:
            self._escalada(ws)
        log = self.saida.getvalue()
        self.assertIn("escalou=haiku frases=1 chars=13", log)
        self.assertNotIn("Deixe-me ver", log)
        self.assertNotIn("estudar para uma prova", log)

    def test_uso_mostra_o_bloco_rapido(self):
        conversa.definir_cliente(ClienteFalso([["Oi."]]))
        with self._ws() as ws:
            self._perguntar(ws, "oi")
            _ate(ws, _fim_conversa)
        self.assertEqual(self.http.get("/uso").status_code, 401)
        r = self.http.get(f"/uso?token={TOKEN}")
        self.assertEqual(r.status_code, 200)
        corpo = r.json()
        self.assertIn("modelo", corpo)
        bloco = corpo["rapido"]
        for campo in ("rapidas", "escaladas_haiku", "escaladas_lista", "falhas", "tokens_entrada", "tokens_saida"):
            self.assertIn(campo, bloco)
        self.assertGreaterEqual(bloco["rapidas"], 1)
        self.assertGreaterEqual(bloco["tokens_entrada"], 180)


if __name__ == "__main__":
    unittest.main()
