package app.simba.assistant

import android.os.SystemClock
import android.util.Log

/**
 * Linha do tempo de um comando por voz. Cada linha mostra o relógio (elapsedRealtime) e o tempo
 * desde o início da pergunta atual (a última vez que o reconhecedor ficou pronto).
 * Nunca registrar o texto das perguntas nem token: só contagens e tempos.
 */
object VozLog {
    private const val TAG = "SimbaVoz"

    @Volatile
    private var t0 = SystemClock.elapsedRealtime()

    /** Começa uma nova linha do tempo (reconhecedor pronto para ouvir). */
    fun start(event: String) {
        t0 = SystemClock.elapsedRealtime()
        i(event)
    }

    fun i(event: String) {
        val now = SystemClock.elapsedRealtime()
        Log.i(TAG, "t=$now +${now - t0}ms $event")
    }
}
