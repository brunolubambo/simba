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

    /** Serviço de reconhecimento preferido no modo conversa: o do Google aceita mais idiomas. */
    private const val GOOGLE_PACKAGE = "com.google.android.googlequicksearchbox"

    /** [conversa]: tenta o serviço do Google antes do escolhido de sempre. */
    fun recognizer(context: Context, conversa: Boolean = false): SpeechRecognizer? {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            VozLog.i("reconhecedor serviço indisponível")
            return null
        }
        if (conversa) {
            val google = google(context)
            if (google != null) {
                VozLog.i("reconhecedor serviço conversa=google pacote=${google.packageName}")
                return SpeechRecognizer.createSpeechRecognizer(context, google)
            }
            VozLog.i("reconhecedor serviço conversa=google ausente, usando o padrão")
        }
        val component = component(context)
        if (component == null) {
            VozLog.i("reconhecedor serviço pacote=padrão")
            return SpeechRecognizer.createSpeechRecognizer(context)
        }
        VozLog.i("reconhecedor serviço pacote=${component.packageName}")
        return SpeechRecognizer.createSpeechRecognizer(context, component)
    }

    /** Nome legível do código de [SpeechRecognizer], para o log. Sem texto falado. */
    fun nomeErro(code: Int): String {
        val nome = when (code) {
            SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "ERROR_NETWORK_TIMEOUT"
            SpeechRecognizer.ERROR_NETWORK -> "ERROR_NETWORK"
            SpeechRecognizer.ERROR_AUDIO -> "ERROR_AUDIO"
            SpeechRecognizer.ERROR_SERVER -> "ERROR_SERVER"
            SpeechRecognizer.ERROR_CLIENT -> "ERROR_CLIENT"
            SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "ERROR_SPEECH_TIMEOUT"
            SpeechRecognizer.ERROR_NO_MATCH -> "ERROR_NO_MATCH"
            SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "ERROR_RECOGNIZER_BUSY"
            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "ERROR_INSUFFICIENT_PERMISSIONS"
            SpeechRecognizer.ERROR_TOO_MANY_REQUESTS -> "ERROR_TOO_MANY_REQUESTS"
            SpeechRecognizer.ERROR_SERVER_DISCONNECTED -> "ERROR_SERVER_DISCONNECTED"
            SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED -> "ERROR_LANGUAGE_NOT_SUPPORTED"
            SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE -> "ERROR_LANGUAGE_UNAVAILABLE"
            else -> "ERROR_DESCONHECIDO"
        }
        return "$nome=$code"
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

    private fun google(context: Context): ComponentName? {
        val found = context.packageManager.queryIntentServices(Intent(RecognitionService.SERVICE_INTERFACE), 0)
        val service = found.firstOrNull { it.serviceInfo.packageName == GOOGLE_PACKAGE } ?: return null
        return ComponentName(service.serviceInfo.packageName, service.serviceInfo.name)
    }
}
