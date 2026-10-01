package app.simba.assistant

import java.text.Normalizer

object Wake {
    private val wake = Regex(
        """\b(?:(?:ei|hey)[, ]+)?(?:simba|samba|sinba|zimba|cimba|simbah|sim[, ]+ba)\b[\s,.!?:-]*""",
        RegexOption.IGNORE_CASE
    )
    private val yes = Regex("""^(sim|pode|autorizo|confirmo|confirma|manda|envia|ok|claro|isso|positivo|faca|faz|segue)\b""")
    private val no = Regex("""^(nao|cancela|negado|nega|para|pare|espera|negativo)\b""")

    fun norm(text: String) = Normalizer.normalize(text, Normalizer.Form.NFD)
        .replace(Regex("\\p{Mn}+"), "")
        .lowercase()
        .trim()

    /** Texto depois de "ei, Simba", ou null se a frase de ativação não foi dita. */
    fun rest(text: String): String? {
        val src = text.trim()
        val n = norm(src)
        val m = wake.find(n) ?: return null
        val cut = m.range.last + 1
        var seen = 0
        var i = 0
        while (i < src.length && seen < cut) {
            val piece = norm(src[i].toString())
            seen += if (piece.isEmpty()) 1 else piece.length
            i++
        }
        return src.substring(i).trim()
    }

    fun fired(text: String) = rest(text) != null
    fun isYes(text: String) = yes.containsMatchIn(norm(text))
    fun isNo(text: String) = no.containsMatchIn(norm(text))

    fun spoken(text: String) = text
        .replace(Regex("```[a-zA-Z0-9_-]*\\n?"), " ")
        .replace(Regex("`([^`]+)`"), "$1")
        .replace(Regex("https?://\\S+"), " ")
        .replace(Regex("(?m)^#{1,6}\\s+"), "")
        .replace(Regex("[*_>#|]"), "")
        .replace(Regex("\\s+"), " ")
        .trim()
}
