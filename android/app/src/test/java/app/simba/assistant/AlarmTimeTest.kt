package app.simba.assistant

import java.time.ZoneId
import java.time.ZonedDateTime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AlarmTimeTest {
    private val sp = ZoneId.of("America/Sao_Paulo")

    private fun agora(h: Int, m: Int, s: Int = 0, nano: Int = 0) =
        ZonedDateTime.of(2026, 10, 7, h, m, s, nano, sp)

    @Test
    fun horarioNoFuturoContinuaHoje() {
        val alvo = AlarmTime.calcular(10, 41, agora(10, 40, 5))
        assertFalse(alvo.amanha)
        assertEquals("hoje 10:41", alvo.descricao())
        assertEquals("2026-10-07T10:41:00-03:00", alvo.iso())
    }

    @Test
    fun faltandoPoucosSegundosNaoViraAmanha() {
        // A regra antiga (agora + 15 s) mandava este caso para amanhã.
        val alvo = AlarmTime.calcular(10, 41, agora(10, 40, 50))
        assertFalse(alvo.amanha)
        assertEquals("2026-10-07T10:41:00-03:00", alvo.iso())
    }

    @Test
    fun horarioQueJaPassouViraAmanha() {
        val alvo = AlarmTime.calcular(10, 41, agora(10, 41, 20))
        assertTrue(alvo.amanha)
        assertEquals("amanhã 10:41", alvo.descricao())
        assertEquals("2026-10-08T10:41:00-03:00", alvo.iso())
    }

    @Test
    fun exatamenteAgoraJaPassou() {
        assertTrue(AlarmTime.calcular(10, 41, agora(10, 41, 0)).amanha)
        assertFalse(AlarmTime.calcular(10, 41, agora(10, 40, 59, 999_000_000)).amanha)
    }

    @Test
    fun viraDiaCruzandoMeiaNoite() {
        val alvo = AlarmTime.calcular(0, 30, agora(23, 50))
        assertTrue(alvo.amanha)
        assertEquals("2026-10-08T00:30:00-03:00", alvo.iso())
    }

    @Test
    fun codigoEUnicoPorHorarioAbsoluto() {
        val hoje = AlarmTime.calcular(10, 41, agora(10, 0))
        val amanha = AlarmTime.calcular(10, 41, agora(11, 0))
        val outroMinuto = AlarmTime.calcular(10, 42, agora(10, 0))
        assertNotEquals(hoje.codigo, amanha.codigo)
        assertNotEquals(hoje.codigo, outroMinuto.codigo)
        assertEquals(hoje.codigo, AlarmTime.calcular(10, 41, agora(10, 30)).codigo)
    }

    @Test
    fun confereUsaTolerancia() {
        val esperado = 1_000_000_000L
        assertTrue(AlarmTime.confere(esperado, esperado))
        assertTrue(AlarmTime.confere(esperado + 60_000L, esperado))
        assertTrue(AlarmTime.confere(esperado - 60_000L, esperado))
        assertFalse(AlarmTime.confere(esperado + 60_001L, esperado))
        assertFalse(AlarmTime.confere(null, esperado))
    }

    @Test
    fun avaliarConfirmaSoQuandoOAlarmeApareceu() {
        val esperado = 1_000_000_000L
        val outro = esperado + 3_600_000L
        // Antes outro alarme, depois o pedido: o Relógio criou.
        assertEquals(AlarmTime.Veredito.CONFIRMADO, AlarmTime.avaliar(outro, esperado, esperado))
        assertEquals(AlarmTime.Veredito.CONFIRMADO, AlarmTime.avaliar(null, esperado + 30_000L, esperado))
        // Nada mudou: não confirmou.
        assertEquals(AlarmTime.Veredito.NAO_CONFIRMADO, AlarmTime.avaliar(outro, outro, esperado))
        assertEquals(AlarmTime.Veredito.NAO_CONFIRMADO, AlarmTime.avaliar(null, null, esperado))
        // Outro alarme mais cedo continua sendo o próximo: sem prova.
        assertEquals(AlarmTime.Veredito.NAO_CONFIRMADO, AlarmTime.avaliar(null, esperado - 3_600_000L, esperado))
        // Já havia um alarme neste horário antes do pedido: não dá para provar que o Relógio criou outro.
        assertEquals(AlarmTime.Veredito.JA_EXISTIA, AlarmTime.avaliar(esperado, esperado, esperado))
    }
}
