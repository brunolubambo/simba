package app.simba.assistant

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Handler
import android.os.Looper
import android.provider.AlarmClock
import androidx.core.app.NotificationCompat
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Busca comandos no servidor (sem Tasker) e executa no aparelho. */
object Phone {
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val loop = AtomicBoolean(false)
    private val seen = LinkedHashSet<String>()

    fun start(context: Context) {
        if (!loop.compareAndSet(false, true)) return
        val app = context.applicationContext
        worker.execute {
            while (loop.get()) {
                try {
                    poll(app)
                } catch (_: Exception) {
                    // Sem rede: tenta de novo no próximo ciclo.
                }
                try {
                    Thread.sleep(2000)
                } catch (_: InterruptedException) {
                    break
                }
            }
        }
    }

    fun stop() {
        loop.set(false)
    }

    fun sendPhoto(context: Context, cmd: String, jpeg: ByteArray) {
        worker.execute {
            val url = Prefs.url(context)
            val token = Prefs.token(context)
            if (url.isBlank() || token.isBlank() || cmd.isBlank()) return@execute
            val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                .addFormDataPart("file", "foto.jpg", jpeg.toRequestBody("image/jpeg".toMediaType()))
                .build()
            val req = Request.Builder()
                .url("$url/celular/foto?token=${enc(token)}&id=${enc(cmd)}")
                .post(body)
                .build()
            try {
                http.newCall(req).execute().use { r ->
                    if (!r.isSuccessful) report(context, cmd, false, "nao enviou a foto")
                }
            } catch (_: Exception) {
                report(context, cmd, false, "nao enviou a foto")
            }
        }
    }

    private fun poll(context: Context) {
        val url = Prefs.url(context)
        val token = Prefs.token(context)
        if (url.isBlank() || token.isBlank()) return
        val req = Request.Builder()
            .url("$url/celular/proximo?token=${enc(token)}")
            .get()
            .build()
        http.newCall(req).execute().use { r ->
            if (r.code == 204 || r.body == null) return
            if (!r.isSuccessful) return
            val text = r.body!!.string()
            if (text.isBlank()) return
            val json = JSONObject(text)
            val id = json.optString("id")
            if (id.isBlank() || !seen.add(id)) return
            while (seen.size > 30) seen.remove(seen.first())
            main.post { run(context, json) }
        }
    }

    private fun run(context: Context, json: JSONObject) {
        val id = json.optString("id")
        when (json.optString("acao")) {
            "alarme" -> alarme(context, id, json.optString("hora"), json.optString("etiqueta"))
            "abrir_app" -> abrir(context, id, json.optString("app"))
            "foto" -> {
                val camera = json.optString("camera").ifBlank { "traseira" }
                context.startActivity(
                    Intent(context, CaptureActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        .putExtra(CaptureActivity.EXTRA_CMD, id)
                        .putExtra(CaptureActivity.EXTRA_CAMERA, camera)
                )
            }
            else -> report(context, id, false, "acao desconhecida")
        }
    }

    private fun alarme(context: Context, id: String, hora: String, etiqueta: String) {
        val parts = hora.split(":")
        if (parts.size < 2) {
            report(context, id, false, "hora invalida")
            return
        }
        val intent = Intent(AlarmClock.ACTION_SET_ALARM)
            .putExtra(AlarmClock.EXTRA_HOUR, parts[0].toIntOrNull() ?: -1)
            .putExtra(AlarmClock.EXTRA_MINUTES, parts[1].toIntOrNull() ?: -1)
            .putExtra(AlarmClock.EXTRA_MESSAGE, etiqueta)
            .putExtra(AlarmClock.EXTRA_SKIP_UI, true)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (intent.getIntExtra(AlarmClock.EXTRA_HOUR, -1) !in 0..23 ||
            intent.getIntExtra(AlarmClock.EXTRA_MINUTES, -1) !in 0..59
        ) {
            report(context, id, false, "hora invalida")
            return
        }
        try {
            context.startActivity(intent)
            report(context, id, true, "")
        } catch (_: Exception) {
            report(context, id, false, "nao criou o alarme")
        }
    }

    private fun abrir(context: Context, id: String, nome: String) {
        val wanted = nome.trim().lowercase()
        if (wanted.isEmpty()) {
            report(context, id, false, "app nao encontrado")
            return
        }
        val pm = context.packageManager
        val launch = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val hit = pm.queryIntentActivities(launch, PackageManager.MATCH_ALL).firstOrNull {
            it.loadLabel(pm).toString().trim().lowercase() == wanted ||
                it.activityInfo.packageName.lowercase() == wanted
        }
        if (hit == null) {
            report(context, id, false, "app nao encontrado")
            return
        }
        val intent = pm.getLaunchIntentForPackage(hit.activityInfo.packageName)
        if (intent == null) {
            report(context, id, false, "app nao encontrado")
            return
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            context.startActivity(intent)
            report(context, id, true, "")
        } catch (_: Exception) {
            ping(context, intent, nome)
            report(context, id, false, "o Android bloqueou abrir o app em segundo plano")
        }
    }

    private fun ping(context: Context, target: Intent, nome: String) {
        val manager = context.getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel("simba-cmd", "Comandos do SIMBA", NotificationManager.IMPORTANCE_HIGH)
        manager.createNotificationChannel(channel)
        val pi = PendingIntent.getActivity(context, nome.hashCode(), target, PendingIntent.FLAG_IMMUTABLE)
        manager.notify(
            71,
            NotificationCompat.Builder(context, "simba-cmd")
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle("SIMBA")
                .setContentText("Toque para abrir $nome")
                .setContentIntent(pi)
                .setAutoCancel(true)
                .build()
        )
    }

    fun report(context: Context, id: String, ok: Boolean, detalhe: String) {
        worker.execute {
            val url = Prefs.url(context)
            val token = Prefs.token(context)
            if (url.isBlank() || token.isBlank() || id.isBlank()) return@execute
            val json = JSONObject()
                .put("id", id)
                .put("ok", if (ok) "true" else "false")
                .put("detalhe", detalhe)
                .toString()
                .toRequestBody("application/json; charset=utf-8".toMediaType())
            val req = Request.Builder()
                .url("$url/celular/resultado?token=${enc(token)}")
                .post(json)
                .build()
            try {
                http.newCall(req).execute().close()
            } catch (_: Exception) {
            }
        }
    }

    private fun enc(v: String) = URLEncoder.encode(v, "UTF-8")
}
