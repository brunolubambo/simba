package app.simba.assistant

import android.content.Context
import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.speech.RecognitionListener
import android.speech.SpeechRecognizer
import android.view.LayoutInflater
import android.view.View
import android.widget.TextView

class AssistantSession(private val app: Context) : VoiceInteractionSession(app) {
    private val speaker = Speaker(app)
    private val reply = StringBuilder()
    private var root: View? = null
    private var recognizer: SpeechRecognizer? = null
    private var approvalId: String? = null
    private val link = SimbaLink(
        app,
        onText = { reply.append(it).append("\n\n") },
        onDone = { speakAndClose() },
        onError = { say(it.ifBlank { "Não consegui concluir." }) { hide() } },
        onApproval = { id, prompt -> askApproval(id, prompt) },
        onNotice = { say(it) {} },
    )

    override fun onCreateContentView(): View {
        val view = LayoutInflater.from(app).inflate(R.layout.session, null)
        root = view
        return view
    }

    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        HotwordService.pause(app)
        link.connect()
        label("Ouvindo")
        listen(::onCommand)
    }

    override fun onHide() {
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
        speaker.stop()
        HotwordService.resume(app)
        super.onHide()
    }

    private fun onCommand(text: String) {
        val rest = Wake.rest(text)
        val command = if (rest != null) rest.ifBlank { text } else text
        if (command.isBlank()) {
            hide()
            return
        }
        label("Processando")
        reply.clear()
        link.ask(command)
    }

    private fun askApproval(id: String, prompt: String) {
        approvalId = id
        val line = prompt.lineSequence().firstOrNull { it.isNotBlank() }.orEmpty()
        say("Senhor, preciso da sua autorização. $line. Posso seguir?") {
            label("Diga sim ou não")
            listen(::onYesNo)
        }
    }

    private fun onYesNo(text: String) {
        val id = approvalId
        approvalId = null
        when {
            id == null -> hide()
            Wake.isYes(text) -> link.approve(id, true)
            Wake.isNo(text) -> link.approve(id, false)
            else -> say("Diga sim ou não.") { listen(::onYesNo) }
        }
    }

    private fun speakAndClose() {
        val said = reply.toString().trim()
        reply.clear()
        if (said.isBlank()) hide() else say(said) { hide() }
    }

    private fun say(text: String, done: () -> Unit) {
        label("Falando")
        speaker.say(text, done)
    }

    private fun listen(onText: (String) -> Unit) {
        val ear = Speech.recognizer(app) ?: run { hide(); return }
        recognizer = ear
        ear.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
            override fun onError(error: Int) { hide() }
            override fun onResults(results: Bundle?) {
                val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
                if (text.isEmpty()) hide() else onText(text)
            }
            override fun onPartialResults(partialResults: Bundle?) {}
        })
        ear.startListening(Speech.intent())
    }

    private fun label(text: String) {
        root?.findViewById<TextView>(R.id.sessionLabel)?.text = text
    }
}
