package app.simba.assistant

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

class SimbaLink(
    context: Context,
    private val onText: (String) -> Unit,
    private val onDone: () -> Unit,
    private val onError: (String) -> Unit,
    private val onApproval: (String, String) -> Unit,
    private val onNotice: (String) -> Unit,
) {
    private val app = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val http = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(PING_SECONDS, TimeUnit.SECONDS)
        .build()
    private val lock = Any()
    private var socket: WebSocket? = null
    private var pending: String? = null
    @Volatile private var waiting = false

    // Pergunta em andamento (para reenviar uma vez se a conexão cair antes de qualquer resposta).
    private var question: String? = null
    private var retried = false
    @Volatile private var gotReply = false
    @Volatile private var firstTextLogged = false

    // Reconexão automática; só some quando o serviço manda fechar de propósito.
    private var closedByUs = false
    private var attempt = 0
    private val reconnect = Runnable { open() }

    fun connect() {
        synchronized(lock) { closedByUs = false }
        open()
    }

    private fun open() {
        val url = Prefs.url(app)
        val token = Prefs.token(app)
        if (url.isBlank() || token.isBlank()) return
        synchronized(lock) {
            if (socket != null || closedByUs) return
            main.removeCallbacks(reconnect)
            val req = Request.Builder().url(ws(url, token)).build()
            socket = http.newWebSocket(req, listener())
        }
    }

    private fun listener() = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            val text: String?
            synchronized(lock) {
                if (socket !== webSocket) return
                attempt = 0
                text = pending
                pending = null
            }
            if (text == null) return
            if (!send(webSocket, text, reopened = true)) dropped(webSocket)
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val event = try { JSONObject(text) } catch (_: Exception) { return }
            when (event.optString("type")) {
                "ack" -> {
                    val sent = event.optLong("t", -1L)
                    if (sent > 0) VozLog.i("ack rtt=${SystemClock.elapsedRealtime() - sent}ms")
                }
                "text" -> if (waiting) {
                    gotReply = true
                    if (!firstTextLogged) {
                        firstTextLogged = true
                        VozLog.i("primeiro text recebido chars=${event.optString("text").length}")
                    }
                    ui { onText(event.optString("text")) }
                }
                "done" -> if (waiting) {
                    waiting = false
                    VozLog.i("done recebido")
                    ui { onDone() }
                }
                "error" -> if (waiting) { waiting = false; ui { onError(event.optString("text")) } }
                "approval" -> ui { onApproval(event.optString("id"), event.optString("prompt")) }
                "reminder" -> ui { onNotice(event.optString("motivo")) }
                "suggestion" -> ui {
                    val title = event.optString("titulo")
                    val extra = if (event.optBoolean("auto")) " Já estou cuidando disso." else ""
                    onNotice("Senhor, $title.$extra")
                }
            }
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(1000, null)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            VozLog.i("socket falhou (${t.javaClass.simpleName})")
            dropped(webSocket)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            dropped(webSocket)
        }
    }

    /** O socket atual caiu: reenvia a pergunta uma vez e agenda a reconexão com recuo. */
    private fun dropped(webSocket: WebSocket) {
        var resend = false
        var fail = false
        synchronized(lock) {
            if (socket !== webSocket) return
            socket = null
            if (closedByUs) return
            if (waiting) {
                if (!retried && !gotReply && question != null) {
                    retried = true
                    pending = question
                    resend = true
                } else {
                    waiting = false
                    pending = null
                    fail = true
                }
            }
        }
        if (resend) {
            VozLog.i("socket caiu com pergunta em andamento: reconectando para reenviar")
            open()
            return
        }
        if (fail) ui { onError("Sem conexão com o SIMBA.") }
        scheduleReconnect()
    }

    private fun scheduleReconnect() {
        val wait: Long
        synchronized(lock) {
            if (closedByUs) return
            wait = backoffMs(attempt++)
        }
        VozLog.i("reconexão em ${wait}ms")
        main.removeCallbacks(reconnect)
        main.postDelayed(reconnect, wait)
    }

    fun ask(text: String) {
        val current: WebSocket?
        synchronized(lock) {
            waiting = true
            question = text
            retried = false
            gotReply = false
            firstTextLogged = false
            current = socket
            if (current == null) pending = text
        }
        if (current == null) {
            open()
            return
        }
        if (!send(current, text, reopened = false)) {
            synchronized(lock) {
                if (socket === current) socket = null
                pending = text
                retried = true
            }
            current.cancel()
            open()
        }
    }

    private fun send(webSocket: WebSocket, text: String, reopened: Boolean): Boolean {
        val voice = VoiceMode.shortAnswer(text)
        val payload = JSONObject()
            .put("type", "message")
            .put("text", text)
            .put("voice", voice)
            .put("t", SystemClock.elapsedRealtime())
            .toString()
        val ok = webSocket.send(payload)
        VozLog.i("pergunta enviada socket=${if (reopened) "reaberto" else "aberto"} ok=$ok chars=${text.length} voice=$voice")
        return ok
    }

    fun approve(id: String, ok: Boolean) {
        synchronized(lock) { socket }?.send(JSONObject().put("type", "approve").put("id", id).put("ok", ok).toString())
    }

    fun close() {
        val old: WebSocket?
        synchronized(lock) {
            closedByUs = true
            waiting = false
            pending = null
            old = socket
            socket = null
        }
        main.removeCallbacks(reconnect)
        old?.close(1000, null)
    }

    private fun ui(block: () -> Unit) {
        main.post(block)
    }

    private fun ws(base: String, token: String): String {
        val root = when {
            base.startsWith("https://") -> "wss://" + base.removePrefix("https://")
            base.startsWith("http://") -> "ws://" + base.removePrefix("http://")
            else -> "wss://$base"
        }
        val coded = URLEncoder.encode(token, "UTF-8")
        return "$root/ws?token=$coded&device=celular"
    }

    companion object {
        private const val PING_SECONDS = 20L
        private val BACKOFF_MS = longArrayOf(1_000, 2_000, 5_000, 15_000)

        /** Espera antes da tentativa número [attempt] (0, 1, 2...): 1 s, 2 s, 5 s, depois 15 s. */
        fun backoffMs(attempt: Int): Long = BACKOFF_MS[attempt.coerceIn(0, BACKOFF_MS.lastIndex)]
    }
}
