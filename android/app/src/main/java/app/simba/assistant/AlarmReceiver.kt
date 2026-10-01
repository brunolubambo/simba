package app.simba.assistant

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Dispara quando chega a hora do alarme criado pelo SIMBA. */
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val launch = Intent(context, AlarmRingActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .putExtra(AlarmRingActivity.EXTRA_HORA, intent.getStringExtra(AlarmRingActivity.EXTRA_HORA))
            .putExtra(AlarmRingActivity.EXTRA_ETIQUETA, intent.getStringExtra(AlarmRingActivity.EXTRA_ETIQUETA))
        context.startActivity(launch)
    }
}
