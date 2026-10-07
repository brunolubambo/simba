package app.simba.assistant

import android.content.Context
import android.graphics.PixelFormat
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.WindowManager

/**
 * Janela de sobreposição de 1x1 px, transparente e sem toque.
 * Com "Aparecer sobre outros apps" concedido e esta janela visível, o Android deixa o app
 * abrir o Relógio em segundo plano. Sem a permissão, [mostrar] devolve false e nada muda.
 * Chamar sempre na thread principal.
 */
class AlarmOverlay(context: Context) {
    private val app = context.applicationContext
    private var view: View? = null

    fun mostrar(): Boolean {
        if (view != null) return true
        if (!Settings.canDrawOverlays(app)) {
            Log.i(TAG, "sobreposicao: sem permissao 'Aparecer sobre outros apps'")
            return false
        }
        return try {
            val wm = app.getSystemService(WindowManager::class.java)
            val v = View(app).apply { setBackgroundColor(0x01000000) } // alfa 1/255: invisível, mas desenhada
            val lp = WindowManager.LayoutParams(
                1, 1,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
                PixelFormat.TRANSLUCENT
            ).apply { gravity = Gravity.TOP or Gravity.START }
            wm.addView(v, lp)
            view = v
            Log.i(TAG, "sobreposicao: janela 1x1 adicionada")
            true
        } catch (e: SecurityException) {
            Log.w(TAG, "sobreposicao: bloqueada (SecurityException)")
            false
        } catch (e: Exception) {
            Log.w(TAG, "sobreposicao: falhou (${e.javaClass.simpleName})")
            false
        }
    }

    fun remover() {
        val v = view ?: return
        view = null
        try {
            app.getSystemService(WindowManager::class.java).removeViewImmediate(v)
            Log.i(TAG, "sobreposicao: janela removida")
        } catch (e: Exception) {
            Log.w(TAG, "sobreposicao: nao removeu (${e.javaClass.simpleName})")
        }
    }

    companion object {
        const val TAG = "SimbaAlarme"
    }
}
