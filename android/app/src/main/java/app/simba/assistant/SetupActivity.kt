package app.simba.assistant

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.speech.SpeechRecognizer
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import android.app.AlarmManager
import android.app.role.RoleManager

class SetupActivity : AppCompatActivity() {
    private lateinit var url: EditText
    private lateinit var token: EditText
    private lateinit var status: TextView

    private val mic = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        continueSetup()
    }
    private val camera = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        continueSetup()
    }
    private val notifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        continueSetup()
    }
    private val role = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        continueSetup()
    }
    private val battery = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        begin()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_setup)
        url = findViewById(R.id.url)
        token = findViewById(R.id.token)
        status = findViewById(R.id.status)
        url.setText(Prefs.url(this).ifBlank { DEFAULT_URL })
        token.setText(Prefs.token(this))
        if (Prefs.listening(this)) status.setText(R.string.listening_note)
        findViewById<Button>(R.id.start).setOnClickListener { activate() }
    }

    private fun activate() {
        val server = url.text.toString().trim()
        val code = token.text.toString().trim()
        if (server.isBlank() || code.isBlank()) {
            status.setText(R.string.no_server)
            return
        }
        Prefs.save(this, server, code, listening = true)
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            status.setText(R.string.no_mic)
            return
        }
        step = Step.MIC
        continueSetup()
    }

    private fun continueSetup() {
        when (step) {
            Step.MIC -> {
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    mic.launch(Manifest.permission.RECORD_AUDIO)
                    step = Step.CAMERA
                    return
                }
                step = Step.CAMERA
                continueSetup()
            }
            Step.CAMERA -> {
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                    camera.launch(Manifest.permission.CAMERA)
                    step = Step.NOTIFICATIONS
                    return
                }
                step = Step.NOTIFICATIONS
                continueSetup()
            }
            Step.NOTIFICATIONS -> {
                if (Build.VERSION.SDK_INT >= 33 &&
                    ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                ) {
                    notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                    step = Step.ROLE
                    return
                }
                step = Step.ROLE
                continueSetup()
            }
            Step.ROLE -> {
                val manager = getSystemService(RoleManager::class.java)
                if (manager.isRoleAvailable(RoleManager.ROLE_ASSISTANT) && !manager.isRoleHeld(RoleManager.ROLE_ASSISTANT)) {
                    role.launch(manager.createRequestRoleIntent(RoleManager.ROLE_ASSISTANT))
                    step = Step.BATTERY
                    return
                }
                step = Step.BATTERY
                continueSetup()
            }
            Step.BATTERY -> {
                val power = getSystemService(PowerManager::class.java)
                if (!power.isIgnoringBatteryOptimizations(packageName)) {
                    val intent = Intent(
                        Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        Uri.parse("package:$packageName")
                    )
                    battery.launch(intent)
                    return
                }
                begin()
            }
            Step.DONE -> begin()
        }
    }

    private fun begin() {
        step = Step.DONE
        if (Build.VERSION.SDK_INT >= 31) {
            val am = getSystemService(AlarmManager::class.java)
            if (!am.canScheduleExactAlarms()) {
                startActivity(
                    Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:$packageName"))
                )
            }
        }
        HotwordService.start(this)
        status.setText(R.string.listening_note)
        probe()
    }

    private fun probe() {
        val base = url.text.toString().trim().trimEnd('/')
        Thread {
            try {
                val req = okhttp3.Request.Builder().url("$base/health").get().build()
                okhttp3.OkHttpClient().newCall(req).execute().use { r ->
                    runOnUiThread {
                        status.text = if (r.isSuccessful) getString(R.string.listening_ok)
                        else getString(R.string.listening_bad, r.code)
                    }
                }
            } catch (_: Exception) {
                runOnUiThread { status.setText(R.string.listening_offline) }
            }
        }.start()
    }

    private enum class Step { MIC, CAMERA, NOTIFICATIONS, ROLE, BATTERY, DONE }

    private var step = Step.DONE

    companion object {
        private const val DEFAULT_URL = "https://authentic-friendship-production-0dac.up.railway.app"
    }
}
