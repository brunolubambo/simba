package app.simba.assistant

/**
 * Pedido direto ("ei, Simba, que horas são"): depois do wake word, junta os parciais e decide quando enviar.
 * Envia no resultado final ou quando o parcial fica [ESTAVEL_MS] sem mudar, o que vier primeiro.
 */
object PedidoDireto {
    /** Tempo sem mudança no parcial para considerar o comando completo. Ajuste aqui. */
    const val ESTAVEL_MS = 700L

    /** O comando ouvido até agora (já sem o wake word) e quando ele mudou pela última vez. */
    data class Escuta(val resto: String, val mudouEm: Long)

    enum class Envio { ESPERAR, FINAL, ESTAVEL }

    /** Novo parcial: o mesmo texto mantém o relógio; texto diferente recomeça a contagem. */
    fun parcial(antes: Escuta?, resto: String, agora: Long): Escuta {
        val limpo = resto.trim()
        return if (antes != null && antes.resto == limpo) antes else Escuta(limpo, agora)
    }

    fun decidir(escuta: Escuta?, final: Boolean, agora: Long): Envio {
        if (escuta == null || escuta.resto.isBlank()) return Envio.ESPERAR
        if (final) return Envio.FINAL
        return if (agora - escuta.mudouEm >= ESTAVEL_MS) Envio.ESTAVEL else Envio.ESPERAR
    }

    /** Quanto falta para o parcial atual ficar estável (0 se já está). */
    fun falta(escuta: Escuta, agora: Long): Long = (ESTAVEL_MS - (agora - escuta.mudouEm)).coerceAtLeast(0)
}
