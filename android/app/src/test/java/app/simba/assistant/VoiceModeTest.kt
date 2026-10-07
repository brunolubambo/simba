package app.simba.assistant

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceModeTest {
    @Test
    fun perguntaComumFicaCurta() {
        assertTrue(VoiceMode.shortAnswer("que horas são"))
        assertTrue(VoiceMode.shortAnswer("qual é a previsão do tempo para amanhã"))
        assertTrue(VoiceMode.shortAnswer(""))
    }

    @Test
    fun cadaGatilhoPedeRespostaLonga() {
        for (trigger in VoiceMode.DETAIL_TRIGGERS) {
            assertFalse(trigger, VoiceMode.shortAnswer(trigger))
        }
    }

    @Test
    fun maiusculasEAcentosFuncionam() {
        assertFalse(VoiceMode.shortAnswer("EXPLIQUE MELHOR"))
        assertFalse(VoiceMode.shortAnswer("Explique Melhor isso"))
        assertFalse(VoiceMode.shortAnswer("me conte mais"))
        assertFalse(VoiceMode.shortAnswer("Me Conte Mais"))
        assertFalse(VoiceMode.shortAnswer("quero uma resposta detalhado, por favor"))
        assertFalse(VoiceMode.shortAnswer("explique em detalhés"))
    }

    @Test
    fun gatilhoNoMeioDaFrase() {
        assertFalse(VoiceMode.shortAnswer("por favor, explique melhor o que é um buraco negro"))
        assertFalse(VoiceMode.shortAnswer("sobre a reunião, me dê mais detalhes"))
        assertFalse(VoiceMode.shortAnswer("pode aprofundar? não, aprofunde esse assunto"))
        assertFalse(VoiceMode.shortAnswer("ei, fale mais sobre isso"))
        assertFalse(VoiceMode.shortAnswer("quais os detalhes do compromisso"))
    }

    @Test
    fun palavraParecidaNaoDisparaNoMeioDeOutra() {
        assertTrue(VoiceMode.shortAnswer("o prédio tem um bom desdetalhe"))
        assertTrue(VoiceMode.shortAnswer("fale devagar"))
        assertTrue(VoiceMode.shortAnswer("me conte uma piada"))
    }

    @Test
    fun listaTemSoTextoNormalizado() {
        for (trigger in VoiceMode.DETAIL_TRIGGERS) assertEquals(Wake.norm(trigger), trigger)
    }
}
