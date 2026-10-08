package app.simba.assistant

import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class PedidoDiretoTest {
    @Test
    fun parcialCurtoNaoEnviaNaHora() {
        val e = PedidoDireto.parcial(null, "que", 1_000L)
        assertEquals(PedidoDireto.Envio.ESPERAR, PedidoDireto.decidir(e, final = false, agora = 1_000L))
    }

    @Test
    fun parcialQueMudaRecomecaORelogio() {
        var e = PedidoDireto.parcial(null, "que", 1_000L)
        e = PedidoDireto.parcial(e, "que horas", 1_500L)
        assertEquals(PedidoDireto.Envio.ESPERAR, PedidoDireto.decidir(e, final = false, agora = 2_000L))
        assertEquals(PedidoDireto.Envio.ESTAVEL, PedidoDireto.decidir(e, final = false, agora = 1_500L + PedidoDireto.ESTAVEL_MS))
    }

    @Test
    fun mesmoParcialMantemORelogio() {
        val e = PedidoDireto.parcial(null, "que horas são", 1_000L)
        assertSame(e, PedidoDireto.parcial(e, " que horas são ", 1_400L))
        assertEquals(PedidoDireto.Envio.ESTAVEL, PedidoDireto.decidir(e, final = false, agora = 1_000L + PedidoDireto.ESTAVEL_MS))
        assertEquals(PedidoDireto.Envio.ESPERAR, PedidoDireto.decidir(e, final = false, agora = 1_000L + PedidoDireto.ESTAVEL_MS - 1))
    }

    @Test
    fun finalEnviaNaHora() {
        val e = PedidoDireto.parcial(null, "que horas são", 1_000L)
        assertEquals(PedidoDireto.Envio.FINAL, PedidoDireto.decidir(e, final = true, agora = 1_001L))
    }

    @Test
    fun semComandoNuncaEnvia() {
        assertEquals(PedidoDireto.Envio.ESPERAR, PedidoDireto.decidir(null, final = true, agora = 9_000L))
        val vazio = PedidoDireto.parcial(null, "   ", 1_000L)
        assertEquals(PedidoDireto.Envio.ESPERAR, PedidoDireto.decidir(vazio, final = true, agora = 9_000L))
        assertEquals(PedidoDireto.Envio.ESPERAR, PedidoDireto.decidir(vazio, final = false, agora = 9_000L))
    }

    @Test
    fun faltaParaFicarEstavel() {
        val e = PedidoDireto.parcial(null, "que horas", 1_000L)
        assertEquals(PedidoDireto.ESTAVEL_MS, PedidoDireto.falta(e, 1_000L))
        assertEquals(200L, PedidoDireto.falta(e, 1_000L + PedidoDireto.ESTAVEL_MS - 200))
        assertEquals(0L, PedidoDireto.falta(e, 5_000L))
    }
}
