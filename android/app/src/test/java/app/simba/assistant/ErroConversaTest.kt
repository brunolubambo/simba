package app.simba.assistant

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ErroConversaTest {
    private fun seguir(vararg codigos: Int): List<Boolean> {
        var c = ErroConversa.Contagem()
        return codigos.map { codigo ->
            val d = ErroConversa.decidir(c, codigo)
            c = d.contagem
            d.parar
        }
    }

    @Test
    fun doisErrosDeIdiomaSeguidosParam() {
        assertEquals(listOf(false, true), seguir(12, 12))
        assertEquals(listOf(false, true), seguir(13, 12))
    }

    @Test
    fun umErroDeIdiomaSozinhoNaoPara() {
        assertEquals(listOf(false, false, false), seguir(12, 5, 13))
    }

    @Test
    fun cincoErrosQuaisquerSeguidosParam() {
        assertEquals(listOf(false, false, false, false, true), seguir(5, 8, 2, 1, 5))
    }

    @Test
    fun silencioENadaEntendidoNuncaParam() {
        assertTrue(seguir(*IntArray(50) { if (it % 2 == 0) 6 else 7 }).none { it })
    }

    @Test
    fun silencioNaoZeraNemSoma() {
        assertEquals(listOf(false, false, false, false, false, false, true), seguir(5, 6, 5, 7, 5, 5, 5))
        assertEquals(listOf(false, false, true), seguir(12, 6, 13))
    }

    @Test
    fun resultadoVazioNaConversaRearma() {
        assertTrue(ErroConversa.rearmarSemTexto(conversa = true, comando = true, sessao = 3, texto = ""))
        assertTrue(ErroConversa.rearmarSemTexto(conversa = true, comando = true, sessao = 3, texto = "   "))
        assertTrue(ErroConversa.rearmarSemTexto(conversa = true, comando = true, sessao = 3, texto = null))
    }

    @Test
    fun resultadoComTextoOuForaDaConversaNaoRearma() {
        assertFalse(ErroConversa.rearmarSemTexto(conversa = true, comando = true, sessao = 3, texto = "hello"))
        assertFalse(ErroConversa.rearmarSemTexto(conversa = false, comando = true, sessao = 3, texto = ""))
        assertFalse(ErroConversa.rearmarSemTexto(conversa = true, comando = false, sessao = 3, texto = ""))
        assertFalse("sessão cancelada de propósito", ErroConversa.rearmarSemTexto(conversa = true, comando = true, sessao = -1, texto = ""))
    }

    @Test
    fun contagemComecaZerada() {
        val d = ErroConversa.decidir(ErroConversa.Contagem(), 5)
        assertFalse(d.parar)
        assertEquals(ErroConversa.Contagem(seguidos = 1, idioma = 0), d.contagem)
    }
}
