package app.simba.assistant

import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionService
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

class SimbaRecognitionService : RecognitionService() {
    private var recognizer: SpeechRecognizer? = null

    override fun onStartListening(recognizerIntent: Intent, listener: Callback) {
        val ear = Speech.recognizer(this) ?: run {
            listener.error(SpeechRecognizer.ERROR_CLIENT)
            return
        }
        recognizer = ear
        ear.setRecognitionListener(object : android.speech.RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) { listener.readyForSpeech(params ?: Bundle()) }
            override fun onBeginningOfSpeech() { listener.beginningOfSpeech() }
            override fun onRmsChanged(rmsdB: Float) { listener.rmsChanged(rmsdB) }
            override fun onBufferReceived(buffer: ByteArray?) { if (buffer != null) listener.bufferReceived(buffer) }
            override fun onEndOfSpeech() { listener.endOfSpeech() }
            override fun onError(error: Int) { listener.error(error) }
            override fun onResults(results: Bundle?) { listener.results(results ?: Bundle()) }
            override fun onPartialResults(partialResults: Bundle?) { listener.partialResults(partialResults ?: Bundle()) }
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        val intent = Intent(recognizerIntent)
        if (!intent.hasExtra(RecognizerIntent.EXTRA_LANGUAGE)) {
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
        }
        ear.startListening(intent)
    }

    override fun onCancel(listener: Callback) {
        recognizer?.cancel()
    }

    override fun onStopListening(listener: Callback) {
        recognizer?.stopListening()
    }

    override fun onDestroy() {
        recognizer?.destroy()
        super.onDestroy()
    }
}
