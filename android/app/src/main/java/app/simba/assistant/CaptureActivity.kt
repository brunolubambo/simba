package app.simba.assistant

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.graphics.SurfaceTexture
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.ImageReader
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.view.Surface
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

/** Tira uma foto e envia ao SIMBA. Fecha sozinha. */
class CaptureActivity : AppCompatActivity() {
    private var cmd = ""
    private var wantFront = false
    private var camera: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var reader: ImageReader? = null
    private var thread: HandlerThread? = null
    private var sent = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        cmd = intent.getStringExtra(EXTRA_CMD).orEmpty()
        wantFront = intent.getStringExtra(EXTRA_CAMERA) == "frontal"
        if (cmd.isBlank()) {
            finish()
            return
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            Phone.report(this, cmd, false, "sem permissao da camera")
            finish()
            return
        }
        thread = HandlerThread("simba-cam").also { it.start() }
        open()
    }

    private fun open() {
        val manager = getSystemService(CameraManager::class.java)
        val id = manager.cameraIdList.firstOrNull { cid ->
            val facing = manager.getCameraCharacteristics(cid).get(CameraCharacteristics.LENS_FACING)
            if (wantFront) facing == CameraCharacteristics.LENS_FACING_FRONT
            else facing == CameraCharacteristics.LENS_FACING_BACK
        } ?: manager.cameraIdList.firstOrNull()
        if (id == null) {
            fail("camera indisponivel")
            return
        }
        reader = ImageReader.newInstance(1280, 720, ImageFormat.JPEG, 1).also { img ->
            img.setOnImageAvailableListener({
                val image = it.acquireLatestImage() ?: return@setOnImageAvailableListener
                val buf = image.planes[0].buffer
                val bytes = ByteArray(buf.remaining())
                buf.get(bytes)
                image.close()
                if (sent) return@setOnImageAvailableListener
                sent = true
                Phone.sendPhoto(this, cmd, bytes)
                runOnUiThread { finish() }
            }, Handler(thread!!.looper))
        }
        try {
            manager.openCamera(id, object : CameraDevice.StateCallback() {
                override fun onOpened(device: CameraDevice) {
                    camera = device
                    shoot(device)
                }
                override fun onDisconnected(device: CameraDevice) {
                    fail("camera desconectada")
                }
                override fun onError(device: CameraDevice, error: Int) {
                    fail("camera erro $error")
                }
            }, Handler(thread!!.looper))
        } catch (_: SecurityException) {
            fail("sem permissao da camera")
        } catch (_: Exception) {
            fail("nao abriu a camera")
        }
    }

    private fun shoot(device: CameraDevice) {
        val jpeg = reader?.surface ?: return fail("camera indisponivel")
        val texture = SurfaceTexture(false)
        texture.setDefaultBufferSize(640, 480)
        val preview = Surface(texture)
        device.createCaptureSession(listOf(preview, jpeg), object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(s: CameraCaptureSession) {
                session = s
                try {
                    val live = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
                    live.addTarget(preview)
                    s.setRepeatingRequest(live.build(), null, Handler(thread!!.looper))
                    val shot = device.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE)
                    shot.addTarget(jpeg)
                    shot.set(CaptureRequest.JPEG_ORIENTATION, 90)
                    s.capture(shot.build(), null, Handler(thread!!.looper))
                } catch (_: Exception) {
                    fail("nao tirou a foto")
                }
            }
            override fun onConfigureFailed(session: CameraCaptureSession) {
                fail("nao tirou a foto")
            }
        }, Handler(thread!!.looper))
    }

    private fun fail(motivo: String) {
        if (!sent) {
            sent = true
            Phone.report(this, cmd, false, motivo)
        }
        runOnUiThread { finish() }
    }

    override fun onDestroy() {
        session?.close()
        camera?.close()
        reader?.close()
        thread?.quitSafely()
        super.onDestroy()
    }

    companion object {
        const val EXTRA_CMD = "cmd"
        const val EXTRA_CAMERA = "camera"
    }
}
