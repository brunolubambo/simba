package app.simba.assistant

import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.SystemClock
import android.provider.AlarmClock
import android.util.Log
import androidx.core.app.NotificationCompat
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
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
    private const val TAG = "SimbaAlarme"
    private const val ESPERA_OVERLAY_MS = 300L  // a sobreposição precisa estar na tela antes do startActivity
    private const val ESPERA_RELOGIO_MS = 3_000L // quanto esperar o Relógio aparecer em getNextAlarmClock()
    private const val PASSO_MS = 250L
    private val ISO = DateTimeFormatter.ISO_OFFSET_DATE_TIME
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
            Log.w(TAG, "recebido id=$id hora='$hora' invalida")
            report(context, id, false, "hora invalida")
            return
        }
        val agora = ZonedDateTime.now()
        val alvo = AlarmTime.calcular(hour, minute, agora)
        val am = context.getSystemService(AlarmManager::class.java)
        val antes = am.nextAlarmClock?.triggerTime
        Log.i(
            TAG,
            "recebido id=$id hora=$hora etiqueta='$etiqueta' fuso=${agora.zone.id} agora=${agora.format(ISO)} " +
                "alvo=${alvo.iso()} (${alvo.descricao()}) amanha=${alvo.amanha} proximoAntes=${iso(antes)}"
        )
        // Abrir o Relógio em segundo plano só é permitido com uma sobreposição visível (Android 15+).
        val overlay = AlarmOverlay(context)
        val comOverlay = overlay.mostrar()
        main.postDelayed({
            val erroAbrir = abrirRelogio(context, hour, minute, etiqueta)
            overlay.remover()
            aguardarRelogio(
                context, am, alvo, antes, id, hora, etiqueta, erroAbrir, comOverlay,
                SystemClock.elapsedRealtime()
            )
        }, if (comOverlay) ESPERA_OVERLAY_MS else 0L)
    }

    /** Pede o alarme ao Relógio sem tela. Devolve null se o pedido saiu, ou o motivo da falha. */
    private fun abrirRelogio(context: Context, hour: Int, minute: Int, etiqueta: String): String? {
        val clock = Intent(AlarmClock.ACTION_SET_ALARM)
            .putExtra(AlarmClock.EXTRA_HOUR, hour)
            .putExtra(AlarmClock.EXTRA_MINUTES, minute)
            .putExtra(AlarmClock.EXTRA_MESSAGE, etiqueta.ifBlank { "SIMBA" })
            .putExtra(AlarmClock.EXTRA_SKIP_UI, true)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return try {
            context.startActivity(clock)
            Log.i(TAG, "relogio: ACTION_SET_ALARM enviado")
            null
        } catch (e: ActivityNotFoundException) {
            Log.w(TAG, "relogio: nenhum app atende ACTION_SET_ALARM")
            "nenhum app de relógio atendeu"
        } catch (e: SecurityException) {
            Log.w(TAG, "relogio: bloqueado (SecurityException)")
            "o Android bloqueou"
        } catch (e: Exception) {
            Log.w(TAG, "relogio: falhou (${e.javaClass.simpleName})")
            "falhou ao abrir"
        }
    }

    /** Espera até ~3 s o Relógio aparecer em getNextAlarmClock(); só então decide o que reportar. */
    private fun aguardarRelogio(
        context: Context, am: AlarmManager, alvo: AlarmTime.Alvo, antes: Long?, id: String, hora: String,
        etiqueta: String, erroAbrir: String?, comOverlay: Boolean, inicio: Long
    ) {
        val depois = am.nextAlarmClock?.triggerTime
        val veredito = AlarmTime.avaliar(antes, depois, alvo.millis)
        val esgotou = SystemClock.elapsedRealtime() - inicio >= ESPERA_RELOGIO_MS
        val decidido = erroAbrir != null || esgotou || veredito != AlarmTime.Veredito.NAO_CONFIRMADO
        if (!decidido) {
            main.postDelayed({
                aguardarRelogio(context, am, alvo, antes, id, hora, etiqueta, erroAbrir, comOverlay, inicio)
            }, PASSO_MS)
            return
        }
        val resultado = if (erroAbrir != null) AlarmTime.Veredito.NAO_CONFIRMADO else veredito
        Log.i(
            TAG,
            "relogio: id=$id veredito=$resultado esperado=${iso(alvo.millis)} proximoDepois=${iso(depois)} " +
                "esperouMs=${SystemClock.elapsedRealtime() - inicio} sobreposicao=$comOverlay erroAbrir=${erroAbrir ?: "nenhum"}"
        )
        if (resultado == AlarmTime.Veredito.CONFIRMADO) {
            report(context, id, true, "Relógio confirmou: alarme ${alvo.descricao()}")
            return
        }
        // Sem prova do Relógio: comportamento antigo (alarme do SIMBA + notificação para tocar) e verdade ao servidor.
        val erroProprio = agendarProprio(context, am, alvo, hora, etiqueta)
        val launch = Intent(context, AlarmActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            .putExtra(AlarmActivity.EXTRA_CMD, id)
            .putExtra(AlarmActivity.EXTRA_HORA, hora)
            .putExtra(AlarmActivity.EXTRA_ETIQUETA, etiqueta)
        try {
            context.startActivity(launch)
        } catch (e: Exception) {
            Log.i(TAG, "fallback: AlarmActivity nao abriu em segundo plano (${e.javaClass.simpleName})")
        }
        avisou(context, launch, hora, etiqueta)
        val motivo = when {
            resultado == AlarmTime.Veredito.JA_EXISTIA ->
                "já havia um alarme neste horário e não consegui provar que o Relógio criou outro"
            erroAbrir != null -> "não consegui abrir o Relógio ($erroAbrir)"
            else -> "o Relógio não confirmou"
        }
        val detalhe = "$motivo (${alvo.descricao()}); deixei uma notificação para tocar" +
            (if (erroProprio != null) "; o alarme do SIMBA também falhou: $erroProprio" else "")
        report(context, id, false, detalhe)
    }

    /** Alarme do próprio SIMBA (AlarmManager). Devolve null se agendou, ou o motivo da falha. */
    private fun agendarProprio(
        context: Context, am: AlarmManager, alvo: AlarmTime.Alvo, hora: String, etiqueta: String
    ): String? {
        // Um id por horário absoluto: horários diferentes não se sobrescrevem.
        val codigo = alvo.codigo
        val fire = Intent(context, AlarmReceiver::class.java)
            .putExtra(AlarmRingActivity.EXTRA_HORA, hora)
            .putExtra(AlarmRingActivity.EXTRA_ETIQUETA, etiqueta)
        val firePi = PendingIntent.getBroadcast(
            context, codigo, fire, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val show = PendingIntent.getActivity(
            context,
            codigo,
            Intent(context, AlarmRingActivity::class.java)
                .putExtra(AlarmRingActivity.EXTRA_HORA, hora)
                .putExtra(AlarmRingActivity.EXTRA_ETIQUETA, etiqueta),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return try {
            if (Build.VERSION.SDK_INT >= 31 && !am.canScheduleExactAlarms()) {
                Log.w(TAG, "fallback: alarme exato bloqueado")
                "o Android bloqueou alarme exato"
            } else {
                am.setAlarmClock(AlarmManager.AlarmClockInfo(alvo.millis, show), firePi)
                Log.i(TAG, "fallback: setAlarmClock agendado codigo=$codigo alvo=${alvo.iso()} proximo=${iso(am.nextAlarmClock?.triggerTime)}")
                null
            }
        } catch (e: SecurityException) {
            Log.w(TAG, "fallback: setAlarmClock bloqueado (SecurityException)")
            "o Android bloqueou o alarme"
        } catch (e: Exception) {
            Log.w(TAG, "fallback: setAlarmClock falhou (${e.javaClass.simpleName})")
            "não criou o alarme"
        }
    }

    private fun iso(millis: Long?): String =
        if (millis == null) "nenhum"
        else Instant.ofEpochMilli(millis).atZone(ZoneId.systemDefault()).format(ISO)

    private fun avisou(context: Context, target: Intent, hora: String, etiqueta: String) {
        val manager = context.getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel("simba-cmd", "Comandos do SIMBA", NotificationManager.IMPORTANCE_HIGH)
        channel.lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
        manager.createNotificationChannel(channel)
        Log.i(TAG, "fallback: postando notificacao (notificacoesAtivas=${manager.areNotificationsEnabled()})")
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
                .setContentText("Alarme às $hora. Toque para criar no Relógio.")
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
                http.newCall(req).execute().use { r ->
                    Log.i(TAG, "report id=$id ok=$ok detalhe='$detalhe' http=${r.code}")
                }
            } catch (e: Exception) {
                Log.w(TAG, "report id=$id ok=$ok nao chegou ao servidor (${e.javaClass.simpleName})")
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
