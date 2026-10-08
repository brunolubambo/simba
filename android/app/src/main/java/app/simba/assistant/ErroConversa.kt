package app.simba.assistant

import android.speech.SpeechRecognizer

/**
 * Decide se o modo conversa continua ouvindo depois de um erro do reconhecedor.
 * Silêncio (6) e nada entendido (7) não contam: o aluno só não falou. Qualquer resultado zera tudo.
 */
object ErroConversa {
    /** Erros de idioma seguidos (12 ou 13) que desistem do modo. */
    const val MAX_IDIOMA = 2

    /** Erros seguidos de qualquer outro tipo, sem resultado entre eles, que desistem do modo. */
    const val MAX_SEGUIDOS = 5

    data class Contagem(val seguidos: Int = 0, val idioma: Int = 0)

    data class Decisao(val contagem: Contagem, val parar: Boolean)

    fun decidir(antes: Contagem, codigo: Int): Decisao {
        if (codigo == SpeechRecognizer.ERROR_SPEECH_TIMEOUT || codigo == SpeechRecognizer.ERROR_NO_MATCH) {
            return Decisao(antes, false)
        }
        val idioma = codigo == SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED ||
            codigo == SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE
        val depois = Contagem(seguidos = antes.seguidos + 1, idioma = if (idioma) antes.idioma + 1 else 0)
        return Decisao(depois, depois.idioma >= MAX_IDIOMA || depois.seguidos >= MAX_SEGUIDOS)
    }
}
