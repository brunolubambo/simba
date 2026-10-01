package app.simba.assistant

import android.content.Intent
import android.os.Bundle
import android.provider.AlarmClock
import androidx.appcompat.app.AppCompatActivity

/** Tenta gravar também no Relógio da Samsung. O alarme real já foi agendado pelo SIMBA. */
class AlarmActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val hora = intent.getStringExtra(EXTRA_HORA).orEmpty()
        val etiqueta = intent.getStringExtra(EXTRA_ETIQUETA).orEmpty()
        val parts = hora.split(":")
        val hour = parts.getOrNull(0)?.toIntOrNull() ?: -1
        val minute = parts.getOrNull(1)?.toIntOrNull() ?: -1
        if (hour in 0..23 && minute in 0..59) {
            val clock = Intent(AlarmClock.ACTION_SET_ALARM)
                .putExtra(AlarmClock.EXTRA_HOUR, hour)
                .putExtra(AlarmClock.EXTRA_MINUTES, minute)
                .putExtra(AlarmClock.EXTRA_MESSAGE, etiqueta.ifBlank { "SIMBA" })
                .putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            try {
                startActivity(clock)
            } catch (_: Exception) {
            }
        }
        finish()
    }

    companion object {
        const val EXTRA_CMD = "cmd"
        const val EXTRA_HORA = "hora"
        const val EXTRA_ETIQUETA = "etiqueta"
    }
}
