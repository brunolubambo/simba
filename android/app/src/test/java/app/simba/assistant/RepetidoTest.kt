package app.simba.assistant

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RepetidoTest {
    private val anterior = Repetido.pedido("Que horas são", 1_000L)

    @Test
    fun mesmoPedidoDentroDaJanelaEIgnorado() {
        assertTrue(Repetido.ignorar(anterior, "Que horas são", 5_000L, conversa = false))
    }

    @Test
    fun comparaPeloTextoNormalizado() {
        assertTrue(Repetido.ignorar(anterior, "  que horas SAO ", 5_000L, conversa = false))
    }

    @Test
    fun depoisDaJanelaSegue() {
        assertFalse(Repetido.ignorar(anterior, "Que horas são", 1_000L + Repetido.JANELA_MS, conversa = false))
        assertTrue(Repetido.ignorar(anterior, "Que horas são", 1_000L + Repetido.JANELA_MS - 1, conversa = false))
    }

    @Test
    fun pedidoDiferenteSegue() {
        assertFalse(Repetido.ignorar(anterior, "Que dia é hoje", 2_000L, conversa = false))
    }

    @Test
    fun semPedidoPendenteSegue() {
        assertFalse(Repetido.ignorar(null, "Que horas são", 2_000L, conversa = false))
    }

    @Test
    fun modoConversaNuncaTrava() {
        assertFalse(Repetido.ignorar(anterior, "Que horas são", 2_000L, conversa = true))
    }

    @Test
    fun relogioParaTrasNaoTrava() {
        assertFalse(Repetido.ignorar(anterior, "Que horas são", 500L, conversa = false))
    }
}
