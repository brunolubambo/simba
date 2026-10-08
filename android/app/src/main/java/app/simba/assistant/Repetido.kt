package app.simba.assistant

/**
 * Trava contra o mesmo pedido repetido enquanto o anterior não terminou.
 * O serviço guarda o último pedido enviado e o apaga no fim do turno: pedido guardado = turno pendente.
 */
object Repetido {
    const val JANELA_MS = 10_000L

    data class Pedido(val chave: String, val em: Long)

    fun chave(texto: String): String = Wake.norm(texto)

    fun pedido(texto: String, agora: Long) = Pedido(chave(texto), agora)

    /** true = não enviar de novo. Nunca vale no modo conversa: lá repetir é parte da prática. */
    fun ignorar(anterior: Pedido?, texto: String, agora: Long, conversa: Boolean): Boolean {
        if (conversa || anterior == null) return false
        val passou = agora - anterior.em
        return passou in 0 until JANELA_MS && chave(texto) == anterior.chave
    }
}
