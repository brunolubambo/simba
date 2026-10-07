package app.simba.assistant

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/** Dispara quando chega a hora do alarme de reserva criado pelo SIMBA (só se o Relógio não confirmou). */
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val hora = intent.getStringExtra(AlarmRingActivity.EXTRA_HORA)
        Log.i(AlarmOverlay.TAG, "disparo: AlarmReceiver hora=$hora")
        val launch = Intent(context, AlarmRingActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .putExtra(AlarmRingActivity.EXTRA_HORA, hora)
            .putExtra(AlarmRingActivity.EXTRA_ETIQUETA, intent.getStringExtra(AlarmRingActivity.EXTRA_ETIQUETA))
        try {
            context.startActivity(launch)
            Log.i(AlarmOverlay.TAG, "disparo: startActivity(AlarmRingActivity) enviado")
        } catch (e: Exception) {
            Log.w(AlarmOverlay.TAG, "disparo: startActivity falhou (${e.javaClass.simpleName})")
        }
    }
}
