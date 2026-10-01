package app.simba.assistant

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
        if (!Prefs.listening(context) || Prefs.url(context).isBlank() || Prefs.token(context).isBlank()) return
        try {
            HotwordService.start(context)
        } catch (_: Exception) {
            // Android recente bloqueia microfone logo depois da reinicialização.
        }
    }
}
