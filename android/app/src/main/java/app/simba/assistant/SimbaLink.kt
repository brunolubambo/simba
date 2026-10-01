package app.simba.assistant

import android.content.Context
import android.os.Handler
import android.os.Looper
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
    private val http = OkHttpClient.Builder().readTimeout(0, TimeUnit.MILLISECONDS).build()
    private var socket: WebSocket? = null
    private var pending: String? = null
    private var waiting = false

    fun connect() {
        if (socket != null) return
        val url = Prefs.url(app)
        val token = Prefs.token(app)
        if (url.isBlank() || token.isBlank()) return
        val req = Request.Builder().url(ws(url, token)).build()
        socket = http.newWebSocket(req, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                val text = pending ?: return
                pending = null
                webSocket.send(message(text))
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val event = try { JSONObject(text) } catch (_: Exception) { return }
                when (event.optString("type")) {
                    "text" -> if (waiting) ui { onText(event.optString("text")) }
                    "done" -> if (waiting) { waiting = false; ui { onDone() } }
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

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                socket = null
                if (waiting) {
                    waiting = false
                    ui { onError("Sem conexão com o SIMBA.") }
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                if (socket === webSocket) socket = null
            }
        })
    }

    fun ask(text: String) {
        waiting = true
        val payload = message(text)
        val open = socket
        if (open == null) {
            pending = text
            connect()
        } else if (!open.send(payload)) {
            pending = text
            socket = null
            connect()
        }
    }

    fun approve(id: String, ok: Boolean) {
        socket?.send(JSONObject().put("type", "approve").put("id", id).put("ok", ok).toString())
    }

    fun close() {
        waiting = false
        socket?.close(1000, null)
        socket = null
    }

    private fun message(text: String) = JSONObject().put("type", "message").put("text", text).toString()

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
}
