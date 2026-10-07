package app.simba.assistant

/** Resposta curta por voz por padrão; longa só quando o usuário pede mais profundidade. */
object VoiceMode {
    /** Frases (sem acento, minúsculas) que pedem resposta longa. Edite aqui. */
    val DETAIL_TRIGGERS = listOf(
        "explique melhor",
        "explica melhor",
        "detalhe",
        "detalhado",
        "mais detalhes",
        "aprofunde",
        "explique em detalhes",
        "me conte mais",
        "fale mais",
    )

    private val detail = Regex(
        DETAIL_TRIGGERS.joinToString("|", prefix = "(?<![a-z])(?:", postfix = ")") { Regex.escape(it) }
    )

    /** true = enviar voice:true (resposta curta); false = o usuário pediu mais detalhe. */
    fun shortAnswer(spoken: String): Boolean = !detail.containsMatchIn(Wake.norm(spoken))
}
