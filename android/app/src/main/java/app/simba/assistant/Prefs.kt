package app.simba.assistant

import android.content.Context

object Prefs {
    private const val FILE = "simba"
    private const val URL = "url"
    private const val TOKEN = "token"
    private const val LISTENING = "listening"

    private fun box(context: Context) = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    fun url(context: Context) = box(context).getString(URL, "").orEmpty()
    fun token(context: Context) = box(context).getString(TOKEN, "").orEmpty()
    fun listening(context: Context) = box(context).getBoolean(LISTENING, false)

    fun save(context: Context, url: String, token: String, listening: Boolean) {
        box(context).edit()
            .putString(URL, url.trim().trimEnd('/'))
            .putString(TOKEN, token.trim())
            .putBoolean(LISTENING, listening)
            .apply()
    }

    fun setListening(context: Context, on: Boolean) {
        box(context).edit().putBoolean(LISTENING, on).apply()
    }
}
