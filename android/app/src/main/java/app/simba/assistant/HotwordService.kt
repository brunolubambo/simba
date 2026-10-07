package app.simba.assistant

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.speech.RecognitionListener
import android.speech.SpeechRecognizer
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

class HotwordService : Service() {
    private val main = Handler(Looper.getMainLooper())
    private lateinit var speaker: Speaker
    private lateinit var link: SimbaLink
    private var recognizer: SpeechRecognizer? = null
    private var phase = Phase.HOTWORD
    private var woke = false
    private var session = 0
    private var active = -1
    private var approvalId: String? = null
    private val reply = StringBuilder()
    private var notice: String? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var modo = ConversaModo.NORMAL
    private var turnStart = 0L

    private val restart = Runnable { listen() }
    private val rearm = Runnable { if (modo.ativo && phase == Phase.COMMAND) arm() }

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) { VozLog.start("reconhecedor pronto (onReadyForSpeech) fase=$phase") }
        override fun onBeginningOfSpeech() { VozLog.i("início da fala (onBeginningOfSpeech)") }
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() { VozLog.i("fim da fala (onEndOfSpeech)") }
        override fun onEvent(eventType: Int, params: Bundle?) {}
        override fun onError(error: Int) {
            if (active < 0) return
            if (modo.ativo && phase == Phase.COMMAND) {
                // Silêncio ou nada entendido no modo conversa: continua ouvindo, sem sair do modo.
                main.removeCallbacks(rearm)
                main.postDelayed(rearm, REARM_MS)
                return
            }
            if (phase == Phase.COMMAND || phase == Phase.YESNO) idle() else scheduleRestart()
        }
        override fun onResults(results: Bundle?) {
            val chars = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim()?.length ?: 0
            VozLog.i("resultado final do reconhecedor chars=$chars fase=$phase")
            take(results, partial = false)
            if (phase == Phase.HOTWORD && !woke) scheduleRestart()
        }
        override fun onPartialResults(partialResults: Bundle?) {
            take(partialResults, partial = true)
        }
    }

    override fun onCreate() {
        super.onCreate()
        running = true
        speaker = Speaker(this)
        link = SimbaLink(
            this,
            onText = { reply.append(it).append("\n\n") },
            onDone = {
                // No modo conversa a resposta do agente (a que ligou o modo) não é falada: o tutor abre a conversa.
                if (!modo.ativo && approvalId == null && phase != Phase.YESNO) finishReply()
            },
            onError = { speaker.say(it.ifBlank { "Não consegui concluir." }, ::idle) },
            onApproval = { id, prompt -> askApproval(id, prompt) },
            onNotice = { text -> notice(text) },
            onFrase = { text, idioma, voz -> onFrase(text, idioma, voz) },
            onModo = { onModo(it) },
            onTurnDone = { onTurnDone(it) },
            onReset = { onReset() },
            conversa = true,
        )
        channel()
        val power = getSystemService(PowerManager::class.java)
        wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "simba:ear").apply { setReferenceCounted(false) }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startInForeground()
        when (intent?.action) {
            ACTION_STOP -> {
                Prefs.setListening(this, false)
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_PAUSE -> {
                phase = Phase.PAUSED
                woke = false
                dropRecognizer()
                return START_STICKY
            }
            ACTION_RESUME -> {
                if (phase == Phase.PAUSED) idle()
                return START_STICKY
            }
        }
        if (!Prefs.listening(this) || Prefs.url(this).isBlank() || Prefs.token(this).isBlank()) {
            stopSelf()
            return START_NOT_STICKY
        }
        wakeLock?.acquire(4 * 60 * 60 * 1000L)
        link.connect()
        speaker.preload(GREETING)
        Phone.start(this)
        if (phase == Phase.HOTWORD) listen()
        return START_STICKY
    }

    override fun onDestroy() {
        main.removeCallbacks(restart)
        main.removeCallbacks(rearm)
        dropRecognizer()
        Phone.stop()
        link.close()
        speaker.shutdown()
        if (wakeLock?.isHeld == true) wakeLock?.release()
        running = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun take(results: Bundle?, partial: Boolean) {
        if (active < 0) return
        val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
        if (text.isEmpty()) return
        when (phase) {
            Phase.HOTWORD -> {
                val rest = Wake.rest(text) ?: return
                if (partial && rest.isBlank()) return
                onWake(text)
            }
            Phase.COMMAND -> if (!partial) onCommand(text)
            Phase.YESNO -> if (!partial) onYesNo(text)
            else -> {}
        }
    }

    private fun onWake(raw: String) {
        if (woke) return
        woke = true
        main.removeCallbacks(restart)
        hush()
        val rest = Wake.rest(raw).orEmpty()
        if (rest.isNotBlank()) {
            phase = Phase.BUSY
            reply.clear()
            link.ask(rest)
        } else {
            phase = Phase.COMMAND
            speaker.sayCached(GREETING) { arm() }
        }
    }

    private fun onCommand(text: String) {
        if (modo.ativo) {
            turnStart = SystemClock.elapsedRealtime()
            VozLog.i("modo conversa: fala do usuário enviada chars=${text.length}")
        }
        phase = Phase.BUSY
        hush()
        reply.clear()
        link.ask(text)
    }

    private fun onYesNo(text: String) {
        val id = approvalId
        phase = Phase.BUSY
        hush()
        when {
            id == null -> idle()
            Wake.isYes(text) -> link.approve(id, true)
            Wake.isNo(text) -> link.approve(id, false)
            else -> {
                phase = Phase.YESNO
                speaker.say("Diga sim ou não.") { arm() }
            }
        }
    }

    private fun askApproval(id: String, prompt: String) {
        approvalId = id
        phase = Phase.BUSY
        hush()
        val line = prompt.lineSequence().firstOrNull { it.isNotBlank() }.orEmpty()
        speaker.say("Senhor, preciso da sua autorização. $line. Posso seguir?") {
            phase = Phase.YESNO
            arm()
        }
    }

    private fun finishReply() {
        approvalId = null
        val said = reply.toString().trim()
        reply.clear()
        if (said.isBlank()) idle() else speaker.afterQueue { speaker.say(said, ::afterSpeech) }
    }

    private fun onFrase(text: String, idioma: String?, voz: String?) {
        if (phase == Phase.COMMAND) {
            phase = Phase.BUSY
            hush()
        }
        speaker.enqueue(text, ConversaModo.vozDaFrase(voz, modo), ConversaModo.idiomaDaFrase(idioma, modo))
    }

    private fun onModo(next: ConversaModo) {
        if (next.ativo) {
            modo = next
            speaker.voice = next.voz
            reply.clear()
            VozLog.i("modo conversa início stt=${next.stt}")
        } else {
            if (!modo.ativo) return
            modo = ConversaModo.NORMAL
            main.removeCallbacks(rearm)
            speaker.clearQueue()
            speaker.voice = null
            VozLog.i("modo conversa fim")
        }
        refreshNotification()
    }

    /** Fim de um turno do modo conversa (ou do feedback final): espera a fila tocar e reabre o microfone. */
    private fun onTurnDone(encaminhado: Boolean) {
        if (encaminhado) {
            phase = Phase.BUSY
            reply.clear()
            link.expect()
        }
        speaker.afterQueue {
            if (turnStart > 0) VozLog.i("modo conversa: turno total ${SystemClock.elapsedRealtime() - turnStart}ms")
            turnStart = 0
            when {
                modo.ativo -> listenConversa()
                encaminhado -> {}
                else -> idle()
            }
        }
    }

    private fun onReset() {
        if (!modo.ativo) return
        onModo(ConversaModo.NORMAL)
        hush()
        idle()
    }

    /** Modo conversa: microfone direto em modo comando, sem precisar de "ei, Simba". */
    private fun listenConversa() {
        main.removeCallbacks(restart)
        woke = false
        approvalId = null
        phase = Phase.COMMAND
        if (recognizer == null) {
            recognizer = Speech.recognizer(this)?.also { it.setRecognitionListener(listener) } ?: return
        }
        arm()
    }

    private fun afterSpeech() {
        val queued = notice
        notice = null
        if (queued != null) speaker.say(queued, ::idle) else idle()
    }

    private fun notice(text: String) {
        if (phase == Phase.HOTWORD && !woke) {
            phase = Phase.BUSY
            hush()
            speaker.say(text, ::idle)
        } else {
            notice = text
        }
    }

    private fun idle() {
        if (modo.ativo) {
            listenConversa()
            return
        }
        woke = false
        approvalId = null
        phase = Phase.HOTWORD
        listen()
    }

    private fun hush() {
        active = -1
        recognizer?.cancel()
    }

    private fun arm() {
        val ear = recognizer ?: return
        active = ++session
        try {
            ear.startListening(if (modo.ativo) Speech.conversaIntent(modo.stt) else Speech.intent())
        } catch (_: Exception) {
            if (modo.ativo) main.postDelayed(rearm, REARM_MS) else scheduleRestart()
        }
    }

    private fun listen() {
        if (phase != Phase.HOTWORD || woke) return
        val ear = recognizer ?: Speech.recognizer(this)?.also {
            it.setRecognitionListener(listener)
            recognizer = it
        } ?: return
        try {
            active = ++session
            ear.startListening(Speech.intent())
        } catch (_: Exception) {
            scheduleRestart()
        }
    }

    private fun scheduleRestart() {
        main.removeCallbacks(restart)
        if (phase == Phase.HOTWORD && !woke) main.postDelayed(restart, 500)
    }

    private fun dropRecognizer() {
        main.removeCallbacks(restart)
        active = -1
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
    }

    private fun startInForeground() {
        val notification = notification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            startForeground(NOTE_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTE_ID, notification)
        }
    }

    private fun channel() {
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(CHANNEL, getString(R.string.channel_name), NotificationManager.IMPORTANCE_LOW)
        manager.createNotificationChannel(channel)
    }

    private fun refreshNotification() {
        getSystemService(NotificationManager::class.java).notify(NOTE_ID, notification())
    }

    private fun notification(): Notification {
        val stop = PendingIntent.getService(
            this, 1,
            Intent(this, HotwordService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE
        )
        val text = if (modo.ativo) getString(R.string.notification_conversa, modo.idioma) else getString(R.string.notification_text)
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(text)
            .setOngoing(true)
            .addAction(0, getString(R.string.notification_stop), stop)
            .build()
    }

    private enum class Phase { HOTWORD, COMMAND, YESNO, BUSY, PAUSED }

    companion object {
        @Volatile
        private var running = false

        private const val CHANNEL = "simba-ear"
        private const val NOTE_ID = 7
        private const val ACTION_PAUSE = "app.simba.assistant.PAUSE"
        private const val ACTION_RESUME = "app.simba.assistant.RESUME"
        private const val ACTION_STOP = "app.simba.assistant.STOP"
        private const val GREETING = "Pois não, senhor?"
        private const val REARM_MS = 300L

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, HotwordService::class.java))
        }

        fun pause(context: Context) {
            if (!running) return
            context.startService(Intent(context, HotwordService::class.java).setAction(ACTION_PAUSE))
        }

        fun resume(context: Context) {
            if (!running) return
            context.startService(Intent(context, HotwordService::class.java).setAction(ACTION_RESUME))
        }
    }
}
