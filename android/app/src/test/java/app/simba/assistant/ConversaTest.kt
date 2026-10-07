package app.simba.assistant

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PhraseQueueTest {
    @Test
    fun entregaNaOrdemMesmoQuandoOAudioChegaForaDeOrdem() {
        val q = PhraseQueue<String>()
        val a = q.add()
        val b = q.add()
        val c = q.add()
        assertTrue(q.ready(c, "terceira"))
        assertTrue(q.ready(b, "segunda"))
        assertNull("a primeira ainda não está pronta", q.pollReady())
        assertTrue(q.ready(a, "primeira"))
        assertEquals("primeira", q.pollReady())
        assertEquals("segunda", q.pollReady())
        assertEquals("terceira", q.pollReady())
        assertNull(q.pollReady())
        assertTrue(q.isEmpty())
    }

    @Test
    fun umaPorVez() {
        val q = PhraseQueue<String>()
        val a = q.add()
        q.ready(a, "a")
        val b = q.add()
        assertEquals(2, q.size)
        assertEquals("a", q.pollReady())
        assertNull(q.pollReady())
        assertFalse(q.isEmpty())
        q.ready(b, "b")
        assertEquals("b", q.pollReady())
    }

    @Test
    fun clearDescartaEAudioAtrasadoNaoVolta() {
        val q = PhraseQueue<String>()
        val a = q.add()
        q.add()
        q.clear()
        assertTrue(q.isEmpty())
        assertFalse(q.ready(a, "atrasada"))
        assertNull(q.pollReady())
        val c = q.add()
        q.ready(c, "nova")
        assertEquals("nova", q.pollReady())
    }
}

class ConversaModoTest {
    @Test
    fun ativoUsaIdiomaEVozDoEvento() {
        val m = ConversaModo.from(true, "fr-FR", "fr-FR-HenriNeural", "francês")
        assertTrue(m.ativo)
        assertEquals("fr-FR", m.stt)
        assertEquals("fr-FR-HenriNeural", m.voz)
        assertEquals("francês", m.idioma)
    }

    @Test
    fun desligadoVoltaAoPtBrEVozPadrao() {
        val m = ConversaModo.from(false, "fr-FR", "fr-FR-HenriNeural", "francês")
        assertEquals(ConversaModo.NORMAL, m)
        assertEquals("pt-BR", m.stt)
        assertNull(m.voz)
    }

    @Test
    fun idiomaInvalidoNaoAtiva() {
        assertFalse(ConversaModo.from(true, "", "x", "y").ativo)
        assertFalse(ConversaModo.from(true, "fr FR; drop", null, null).ativo)
    }

    @Test
    fun vozInvalidaViraPadrao() {
        val m = ConversaModo.from(true, "ja-JP", "../../etc", "japonês")
        assertTrue(m.ativo)
        assertNull(m.voz)
        assertEquals("ja-JP", ConversaModo.from(true, "ja-JP", null, "").idioma)
    }

    @Test
    fun vozEIdiomaDaFrase() {
        val m = ConversaModo.from(true, "en-US", "en-US-GuyNeural", "inglês")
        assertEquals("pt-BR-AntonioNeural", ConversaModo.vozDaFrase("pt-BR-AntonioNeural", m))
        assertEquals("en-US-GuyNeural", ConversaModo.vozDaFrase(null, m))
        assertEquals("en-US-GuyNeural", ConversaModo.vozDaFrase("inválida", m))
        assertNull(ConversaModo.vozDaFrase(null, ConversaModo.NORMAL))
        assertEquals("pt-BR", ConversaModo.idiomaDaFrase("pt-BR", m))
        assertEquals("en-US", ConversaModo.idiomaDaFrase(null, m))
    }
}
