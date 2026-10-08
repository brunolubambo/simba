"""Via rapida: lista local, prompt minimo, variaveis de ambiente e contadores. Sem rede.

Frases e valores falsos de proposito.
"""
import os
import types
import unittest

try:  # `discover -s tests` (modulo de topo) ou `unittest tests.test_rapido`
    from test_conversa import _carregar
except ImportError:  # pragma: no cover
    from tests.test_conversa import _carregar

rapido = _carregar("simba.rapido")
conversa = _carregar("simba.conversa")

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


if __name__ == "__main__":
    unittest.main()
