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

    private val restart = Runnable { listen() }

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}
        override fun onEvent(eventType: Int, params: Bundle?) {}
        override fun onError(error: Int) {
            if (active < 0) return
            if (phase == Phase.COMMAND || phase == Phase.YESNO) idle() else scheduleRestart()
        }
        override fun onResults(results: Bundle?) {
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
                if (approvalId == null && phase != Phase.YESNO) finishReply()
            },
            onError = { speaker.say(it.ifBlank { "Não consegui concluir." }, ::idle) },
            onApproval = { id, prompt -> askApproval(id, prompt) },
            onNotice = { text -> notice(text) },
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
        if (phase == Phase.HOTWORD) listen()
        return START_STICKY
    }

    override fun onDestroy() {
        main.removeCallbacks(restart)
        dropRecognizer()
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
            speaker.say("Pois não, senhor?") { arm() }
        }
    }

    private fun onCommand(text: String) {
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
        if (said.isBlank()) idle() else speaker.say(said, ::afterSpeech)
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
            ear.startListening(Speech.intent())
        } catch (_: Exception) {
            scheduleRestart()
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

    private fun notification(): Notification {
        val stop = PendingIntent.getService(
            this, 1,
            Intent(this, HotwordService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(getString(R.string.notification_text))
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
