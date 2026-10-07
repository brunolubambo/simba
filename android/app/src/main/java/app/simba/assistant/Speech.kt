package app.simba.assistant

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.speech.RecognitionService
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

object Speech {
    /** Modo conversa: quem aprende um idioma pausa para pensar. Ajuste aqui. */
    const val CONVERSA_SILENCIO_COMPLETO_MS = 1500L
    const val CONVERSA_SILENCIO_POSSIVEL_MS = 1200L

    fun recognizer(context: Context): SpeechRecognizer? {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) return null
        val component = component(context)
        return if (component != null) SpeechRecognizer.createSpeechRecognizer(context, component)
        else SpeechRecognizer.createSpeechRecognizer(context)
    }

    fun intent(): Intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
        putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
        putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
    }

    /** Reconhecedor do modo conversa: idioma da prática e silêncio de fim de fala mais tolerante. */
    fun conversaIntent(language: String): Intent = intent().apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, language)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, language)
        putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, CONVERSA_SILENCIO_COMPLETO_MS)
        putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, CONVERSA_SILENCIO_POSSIVEL_MS)
    }

    private fun component(context: Context): ComponentName? {
        val found = context.packageManager.queryIntentServices(Intent(RecognitionService.SERVICE_INTERFACE), 0)
        val other = found.firstOrNull { it.serviceInfo.packageName != context.packageName } ?: return null
        return ComponentName(other.serviceInfo.packageName, other.serviceInfo.name)
    }
}
