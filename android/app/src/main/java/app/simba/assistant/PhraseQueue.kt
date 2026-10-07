package app.simba.assistant

/**
 * Fila de frases faladas em ordem. Cada frase entra com add() e fica pronta (áudio baixado) com ready(),
 * em qualquer ordem; pollReady() só entrega a próxima da fila, e só quando ela estiver pronta.
 */
class PhraseQueue<T> {
    private val order = ArrayDeque<Long>()
    private val done = HashMap<Long, T>()
    private var next = 0L

    fun add(): Long {
        val id = next++
        order.addLast(id)
        return id
    }

    /** false se a frase já saiu da fila (por exemplo, depois de clear()). */
    fun ready(id: Long, value: T): Boolean {
        if (id !in order) return false
        done[id] = value
        return true
    }

    fun pollReady(): T? {
        val head = order.firstOrNull() ?: return null
        val value = done.remove(head) ?: return null
        order.removeFirst()
        return value
    }

    fun isEmpty() = order.isEmpty()

    val size: Int get() = order.size

    fun clear() {
        order.clear()
        done.clear()
    }
}
