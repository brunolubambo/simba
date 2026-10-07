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
import java.security.MessageDigest
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

    /** Voz do edge-tts para as frases do modo conversa; null = voz padrão do servidor. */
    var voice: String? = null

    // Fila do modo conversa (só na thread principal).
    private class Clip(val text: String, val file: File?, val lang: String)
    private val queue = PhraseQueue<Clip>()
    private var queuePlaying = false
    private var queueSpoken = 0
    private var generation = 0
    private val idle = mutableListOf<() -> Unit>()

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
        clearQueue()
        VozLog.i("fala: chars=${clean.length}")
        thread(name = "simba-tts") {
            val file = fetch(clean, null, File(app.cacheDir, "simba-say.mp3"))
            main.post {
                if (file != null) play(file, clean, done) else local(clean, done)
            }
        }
    }

    /** Fala fixa (ex.: "Pois não, senhor?") guardada em disco: toca na hora, sem rede, depois da primeira vez. */
    fun sayCached(text: String, done: () -> Unit) {
        val cached = cachedFile(text)
        if (cached.length() > 0) {
            clearQueue()
            VozLog.i("fala em cache: chars=${text.length}")
            play(cached, text, done)
            return
        }
        clearQueue()
        VozLog.i("fala sem cache ainda: chars=${text.length}")
        thread(name = "simba-tts") {
            val file = store(text, cached)
            main.post { if (file != null) play(file, text, done) else local(text, done) }
        }
    }

    /** Gera o áudio da fala fixa em segundo plano, se ainda não estiver no disco. */
    fun preload(text: String) {
        val cached = cachedFile(text)
        if (cached.length() > 0) return
        thread(name = "simba-tts-cache") { store(text, cached) }
    }

    /** Modo conversa: entra na fila; o áudio é buscado já, e toca em ordem, uma frase por vez. */
    fun enqueue(text: String, voz: String?, lang: String) {
        val clean = Wake.spoken(text)
        if (clean.isBlank()) return
        val id = queue.add()
        val gen = generation
        val target = File(app.cacheDir, "frase-$gen-$id.mp3")
        thread(name = "simba-frase") {
            val file = fetch(clean, voz ?: voice, target)
            main.post {
                if (gen != generation || !queue.ready(id, Clip(clean, file, lang))) {
                    file?.delete()
                    return@post
                }
                pump()
            }
        }
    }

    /** Roda quando a fila esvaziar (ou já, se estiver vazia). */
    fun afterQueue(block: () -> Unit) {
        if (!queuePlaying && queue.isEmpty()) block() else idle += block
    }

    /** Para a fila e descarta frases e callbacks pendentes. */
    fun clearQueue() {
        generation++
        queue.clear()
        idle.clear()
        if (queuePlaying) stop()
        queuePlaying = false
        queueSpoken = 0
    }

    private fun pump() {
        if (queuePlaying) return
        val clip = queue.pollReady()
        if (clip == null) {
            if (queue.isEmpty()) drained()
            return
        }
        queuePlaying = true
        queueSpoken++
        VozLog.i(if (queueSpoken == 1) "primeira frase falada (start) chars=${clip.text.length}" else "frase $queueSpoken falada (start) chars=${clip.text.length}")
        val gen = generation
        val next = {
            clip.file?.delete()
            if (gen == generation) {
                queuePlaying = false
                pump()
            }
        }
        if (clip.file != null) play(clip.file, clip.text, next, clip.lang) else local(clip.text, next, clip.lang)
    }

    private fun drained() {
        queueSpoken = 0
        val waiting = idle.toList()
        idle.clear()
        waiting.forEach { it() }
    }

    fun stop() {
        player?.run { runCatching { stop() }; release() }
        player = null
        if (ready) tts.stop()
    }

    fun shutdown() {
        clearQueue()
        stop()
        tts.shutdown()
    }

    /** Chave = texto + voz. As falas fixas usam a voz padrão do servidor. */
    private fun cachedFile(text: String, voz: String = DEFAULT_VOICE_KEY): File {
        val key = MessageDigest.getInstance("SHA-256").digest("$text|$voz".toByteArray())
            .joinToString("") { "%02x".format(it) }.take(24)
        return File(app.cacheDir, "fala-$key.mp3")
    }

    private fun store(text: String, cached: File): File? {
        val tmp = File(app.cacheDir, cached.name + ".tmp")
        val file = fetch(text, null, tmp) ?: return null
        return if (file.renameTo(cached)) cached else file
    }

    private fun fetch(text: String, voz: String?, target: File): File? {
        val base = Prefs.url(app)
        val token = Prefs.token(app)
        if (base.isBlank() || token.isBlank()) return null
        return try {
            val coded = URLEncoder.encode(token, "UTF-8")
            val json = JSONObject().put("text", text)
            if (voz != null) json.put("voz", voz)
            val body = json.toString().toRequestBody("application/json".toMediaType())
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
                    val bytes = clip.body?.bytes() ?: return null
                    VozLog.i("GET /tts/{id} último byte recebido bytes=${bytes.size}")
                    target.writeBytes(bytes)
                    target
                }
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun play(file: File, text: String, done: () -> Unit, lang: String? = null) {
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
            if (!started && once.compareAndSet(false, true)) local(text, done, lang) else finish.run()
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
            if (once.compareAndSet(false, true)) local(text, done, lang)
        }
    }

    private fun local(text: String, done: () -> Unit, lang: String? = null) {
        if (!ready) {
            done()
            return
        }
        VozLog.i("voz local de reserva chars=${text.length}")
        tts.language = if (lang.isNullOrBlank()) Locale("pt", "BR") else Locale.forLanguageTag(lang)
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}
            override fun onDone(utteranceId: String?) { main.post(done) }
            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) { main.post(done) }
        })
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "simba")
    }

    private companion object {
        const val DEFAULT_VOICE_KEY = "padrao"
    }
}
