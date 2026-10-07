package app.simba.assistant

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.net.URLEncoder
import java.util.Locale
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

class Speaker(context: Context) : TextToSpeech.OnInitListener {
    private val app = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val http = OkHttpClient.Builder().callTimeout(60, TimeUnit.SECONDS).build()
    private val tts = TextToSpeech(app, this)
    private var ready = false
    private var player: MediaPlayer? = null

    override fun onInit(status: Int) {
        ready = status == TextToSpeech.SUCCESS
        if (ready) tts.language = Locale("pt", "BR")
    }

    fun say(text: String, done: () -> Unit) {
        val clean = Wake.spoken(text)
        if (clean.isBlank()) {
            done()
            return
        }
        VozLog.i("fala: chars=${clean.length}")
        thread(name = "simba-tts") {
            val file = fetch(clean)
            main.post {
                if (file != null) play(file, clean, done) else local(clean, done)
            }
        }
    }

    fun stop() {
        player?.run { runCatching { stop() }; release() }
        player = null
        if (ready) tts.stop()
    }

    fun shutdown() {
        stop()
        tts.shutdown()
    }

    private fun fetch(text: String): File? {
        val base = Prefs.url(app)
        val token = Prefs.token(app)
        if (base.isBlank() || token.isBlank()) return null
        return try {
            val coded = URLEncoder.encode(token, "UTF-8")
            val body = JSONObject().put("text", text).toString().toRequestBody("application/json".toMediaType())
            VozLog.i("POST /tts início")
            val created = http.newCall(Request.Builder().url("$base/tts?token=$coded").post(body).build()).execute()
            VozLog.i("POST /tts cabeçalho recebido código=${created.code}")
            created.use { response ->
                if (!response.isSuccessful) return null
                val id = JSONObject(response.body?.string().orEmpty()).optString("id")
                if (id.isBlank()) return null
                val audio = http.newCall(Request.Builder().url("$base/tts/$id?token=$coded").build()).execute()
                VozLog.i("GET /tts/{id} cabeçalho recebido código=${audio.code}")
                audio.use { clip ->
                    if (!clip.isSuccessful) return null
                    val file = File(app.cacheDir, "simba-say.mp3")
                    val bytes = clip.body?.bytes() ?: return null
                    VozLog.i("GET /tts/{id} último byte recebido bytes=${bytes.size}")
                    file.writeBytes(bytes)
                    file
                }
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun play(file: File, text: String, done: () -> Unit) {
        stop()
        val once = java.util.concurrent.atomic.AtomicBoolean(false)
        val finish = Runnable { if (once.compareAndSet(false, true)) done() }
        val media = MediaPlayer()
        player = media
        media.setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
        )
        media.setOnCompletionListener {
            it.release()
            if (player === it) player = null
            finish.run()
        }
        var started = false
        media.setOnErrorListener { mp, _, _ ->
            mp.release()
            if (player === mp) player = null
            if (!started && once.compareAndSet(false, true)) local(text, done) else finish.run()
            true
        }
        try {
            media.setDataSource(file.absolutePath)
            VozLog.i("áudio prepare() início")
            media.prepare()
            VozLog.i("áudio prepare() fim")
            media.start()
            VozLog.i("áudio start() chamado chars=${text.length}")
            started = true
        } catch (_: Exception) {
            if (player === media) player = null
            runCatching { media.release() }
            if (once.compareAndSet(false, true)) local(text, done)
        }
    }

    private fun local(text: String, done: () -> Unit) {
        if (!ready) {
            done()
            return
        }
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}
            override fun onDone(utteranceId: String?) { main.post(done) }
            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) { main.post(done) }
        })
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "simba")
    }
}
