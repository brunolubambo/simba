package app.simba.assistant

/** Estado do modo conversa vindo do evento "modo" do servidor, já validado. */
data class ConversaModo(val ativo: Boolean, val stt: String, val voz: String?, val idioma: String) {
    companion object {
        const val PADRAO_STT = "pt-BR"
        val NORMAL = ConversaModo(false, PADRAO_STT, null, "")

        private val bcp47 = Regex("^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
        private val nomeVoz = Regex("^[A-Za-z]{2,3}(-[A-Za-z0-9]+)+Neural$")

        /** Desligado, ou ligado com idioma inválido, volta ao normal (pt-BR e voz padrão do servidor). */
        fun from(ativo: Boolean, stt: String?, voz: String?, idioma: String?): ConversaModo {
            if (!ativo) return NORMAL
            val lang = stt?.trim().orEmpty()
            if (!bcp47.matches(lang)) return NORMAL
            return ConversaModo(true, lang, voice(voz), idioma?.trim().orEmpty().ifBlank { lang })
        }

        /** Nome de voz do edge-tts (ex.: fr-FR-HenriNeural) ou null para a voz padrão do servidor. */
        fun voice(nome: String?): String? = nome?.trim()?.takeIf { nomeVoz.matches(it) }

        /** Voz de uma frase: a que veio na frase; senão a do modo; senão a padrão. */
        fun vozDaFrase(daFrase: String?, modo: ConversaModo): String? = voice(daFrase) ?: modo.voz

        /** Idioma de uma frase (para a voz local de reserva): o da frase, senão o do reconhecedor. */
        fun idiomaDaFrase(daFrase: String?, modo: ConversaModo): String =
            daFrase?.trim()?.takeIf { bcp47.matches(it) } ?: modo.stt
    }
}
