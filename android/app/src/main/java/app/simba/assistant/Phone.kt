package app.simba.assistant

import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import androidx.core.app.NotificationCompat
import java.util.Calendar
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Busca comandos no servidor e executa no aparelho. */
object Phone {
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()
    private val main = Handler(Looper.getMainLooper())
    private val loop = AtomicBoolean(false)
    private val seen = LinkedHashSet<String>()
    private var thread: HandlerThread? = null
    private var worker: Handler? = null
    @Volatile private var app: Context? = null

    fun start(context: Context) {
        app = context.applicationContext
        loop.set(true)
        val handler = ensureWorker()
        handler.removeCallbacksAndMessages(null)
        handler.post { ping(app!!) }
        handler.post(tick)
    }

    fun stop() {
        loop.set(false)
        worker?.removeCallbacksAndMessages(null)
    }

    fun sendPhoto(context: Context, cmd: String, jpeg: ByteArray) {
        val ctx = context.applicationContext
        ensureWorker().post {
            val url = Prefs.url(ctx)
            val token = Prefs.token(ctx)
            if (url.isBlank() || token.isBlank() || cmd.isBlank()) return@post
            val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                .addFormDataPart("file", "foto.jpg", jpeg.toRequestBody("image/jpeg".toMediaType()))
                .build()
            val req = authed(ctx, "$url/celular/foto?id=${enc(cmd)}")
                .post(body)
                .build()
            try {
                http.newCall(req).execute().use { r ->
                    if (!r.isSuccessful) report(ctx, cmd, false, "nao enviou a foto")
                }
            } catch (_: Exception) {
                report(ctx, cmd, false, "nao enviou a foto")
            }
        }
    }

    private val tick = object : Runnable {
        override fun run() {
            if (!loop.get()) return
            val ctx = app ?: return
            try {
                poll(ctx)
            } catch (_: Exception) {
            }
            if (loop.get()) worker?.postDelayed(this, 1500)
        }
    }

    private fun ensureWorker(): Handler {
        synchronized(this) {
            if (worker != null && thread?.isAlive == true) return worker!!
            thread?.quitSafely()
            thread = HandlerThread("simba-phone").also { it.start() }
            worker = Handler(thread!!.looper)
            return worker!!
        }
    }

    private fun ping(context: Context) {
        val url = Prefs.url(context)
        val token = Prefs.token(context)
        if (url.isBlank() || token.isBlank()) return
        try {
            http.newCall(authed(context, "$url/health").get().build()).execute().close()
        } catch (_: Exception) {
        }
    }

    private fun poll(context: Context) {
        val url = Prefs.url(context)
        val token = Prefs.token(context)
        if (url.isBlank() || token.isBlank()) return
        val req = authed(context, "$url/celular/proximo").get().build()
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
        val hour = parts.getOrNull(0)?.toIntOrNull() ?: -1
        val minute = parts.getOrNull(1)?.toIntOrNull() ?: -1
        if (hour !in 0..23 || minute !in 0..59) {
            report(context, id, false, "hora invalida")
            return
        }
        val quando = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, hour)
            set(Calendar.MINUTE, minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
            if (timeInMillis <= System.currentTimeMillis() + 15_000L) add(Calendar.DAY_OF_YEAR, 1)
        }
        val fire = Intent(context, AlarmReceiver::class.java)
            .putExtra(AlarmRingActivity.EXTRA_HORA, hora)
            .putExtra(AlarmRingActivity.EXTRA_ETIQUETA, etiqueta)
        val firePi = PendingIntent.getBroadcast(
            context,
            hour * 60 + minute,
            fire,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val show = PendingIntent.getActivity(
            context,
            hour * 60 + minute + 9000,
            Intent(context, AlarmRingActivity::class.java)
                .putExtra(AlarmRingActivity.EXTRA_HORA, hora)
                .putExtra(AlarmRingActivity.EXTRA_ETIQUETA, etiqueta),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        try {
            val am = context.getSystemService(AlarmManager::class.java)
            if (Build.VERSION.SDK_INT >= 31 && !am.canScheduleExactAlarms()) {
                report(context, id, false, "o Android bloqueou alarme exacto; em Ajustes do SIMBA permita alarmes")
            } else {
                am.setAlarmClock(AlarmManager.AlarmClockInfo(quando.timeInMillis, show), firePi)
                report(context, id, true, "")
            }
        } catch (_: SecurityException) {
            report(context, id, false, "o Android bloqueou o alarme")
        } catch (_: Exception) {
            report(context, id, false, "nao criou o alarme")
        }
        val launch = Intent(context, AlarmActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            .putExtra(AlarmActivity.EXTRA_CMD, id)
            .putExtra(AlarmActivity.EXTRA_HORA, hora)
            .putExtra(AlarmActivity.EXTRA_ETIQUETA, etiqueta)
        try {
            context.startActivity(launch)
        } catch (_: Exception) {
        }
        avisou(context, launch, hora, etiqueta)
    }

    private fun avisou(context: Context, target: Intent, hora: String, etiqueta: String) {
        val manager = context.getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel("simba-cmd", "Comandos do SIMBA", NotificationManager.IMPORTANCE_HIGH)
        channel.lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
        manager.createNotificationChannel(channel)
        val pi = PendingIntent.getActivity(
            context,
            (hora + etiqueta + target.getStringExtra(AlarmActivity.EXTRA_CMD)).hashCode(),
            target,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        manager.notify(
            72,
            NotificationCompat.Builder(context, "simba-cmd")
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle("SIMBA")
                .setContentText("Alarme às $hora")
                .setContentIntent(pi)
                .setFullScreenIntent(pi, true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setAutoCancel(true)
                .build()
        )
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
            pingOpen(context, intent, nome)
            report(context, id, false, "o Android bloqueou abrir o app em segundo plano")
        }
    }

    private fun pingOpen(context: Context, target: Intent, nome: String) {
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
        val ctx = context.applicationContext
        ensureWorker().post {
            val url = Prefs.url(ctx)
            val token = Prefs.token(ctx)
            if (url.isBlank() || token.isBlank() || id.isBlank()) return@post
            val json = JSONObject()
                .put("id", id)
                .put("ok", if (ok) "true" else "false")
                .put("detalhe", detalhe)
                .toString()
                .toRequestBody("application/json; charset=utf-8".toMediaType())
            val req = authed(ctx, "$url/celular/resultado")
                .post(json)
                .build()
            try {
                http.newCall(req).execute().close()
            } catch (_: Exception) {
            }
        }
    }

    private fun authed(context: Context, url: String): Request.Builder {
        val token = Prefs.token(context)
        val join = if (url.contains("?")) "&" else "?"
        return Request.Builder()
            .url("$url${join}token=${enc(token)}")
            .header("Authorization", "Bearer $token")
            .header("X-Simba-Token", token)
    }

    private fun enc(v: String) = java.net.URLEncoder.encode(v, "UTF-8")
}
