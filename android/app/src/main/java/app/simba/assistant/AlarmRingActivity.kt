package app.simba.assistant

import android.media.Ringtone
import android.media.RingtoneManager
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/** Tela e som do alarme do SIMBA, independente do app Relógio da Samsung. */
class AlarmRingActivity : AppCompatActivity() {
    private var tone: Ringtone? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val hora = intent.getStringExtra(EXTRA_HORA).orEmpty()
        val etiqueta = intent.getStringExtra(EXTRA_ETIQUETA).orEmpty().ifBlank { "Alarme" }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(48, 48, 48, 48)
        }
        root.addView(TextView(this).apply {
            text = hora
            textSize = 42f
            gravity = Gravity.CENTER
            setTextColor(0xFFFFFFFF.toInt())
        })
        root.addView(TextView(this).apply {
            text = etiqueta
            textSize = 22f
            gravity = Gravity.CENTER
            setPadding(0, 24, 0, 48)
            setTextColor(0xFFFFFFFF.toInt())
        })
        root.addView(Button(this).apply {
            text = "Desligar"
            setOnClickListener { finish() }
        })
        setContentView(root)
        val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        tone = RingtoneManager.getRingtone(this, uri)
        tone?.play()
    }

    override fun onDestroy() {
        tone?.stop()
        super.onDestroy()
    }

    companion object {
        const val EXTRA_HORA = "hora"
        const val EXTRA_ETIQUETA = "etiqueta"
    }
}
