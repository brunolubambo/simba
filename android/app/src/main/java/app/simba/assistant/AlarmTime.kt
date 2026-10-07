package app.simba.assistant

import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

/** Contas do alarme em funções puras (sem Android), para poder testar no PC. */
object AlarmTime {
    /** Quanto o próximo alarme do aparelho pode diferir do pedido e ainda valer como o mesmo. */
    const val TOLERANCIA_MS = 60_000L

    /** Horário absoluto do alarme e se ele caiu em amanhã. */
    data class Alvo(val momento: ZonedDateTime, val amanha: Boolean) {
        val millis: Long get() = momento.toInstant().toEpochMilli()

        /** Minutos desde 1970: id estável e único por horário absoluto (serve de requestCode). */
        val codigo: Int get() = (millis / 60_000L).toInt()

        fun iso(): String = momento.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)

        /** "hoje 10:41" ou "amanhã 10:41", para o detalhe enviado ao servidor. */
        fun descricao(): String =
            (if (amanha) "amanhã " else "hoje ") + "%02d:%02d".format(momento.hour, momento.minute)
    }

    /**
     * HH:MM no fuso de [agora]. Só vira amanhã se o horário de hoje já passou
     * (um horário daqui a poucos segundos continua sendo hoje).
     */
    fun calcular(hora: Int, minuto: Int, agora: ZonedDateTime): Alvo {
        val hoje = agora.withHour(hora).withMinute(minuto).withSecond(0).withNano(0)
        return if (hoje.isAfter(agora)) Alvo(hoje, false) else Alvo(hoje.plusDays(1), true)
    }

    /** O horário do próximo alarme do aparelho é o pedido, dentro da tolerância. */
    fun confere(proximo: Long?, esperado: Long, tolerancia: Long = TOLERANCIA_MS): Boolean =
        proximo != null && kotlin.math.abs(proximo - esperado) <= tolerancia

    enum class Veredito { CONFIRMADO, JA_EXISTIA, NAO_CONFIRMADO }

    /**
     * Compara o próximo alarme do aparelho antes e depois de pedir ao Relógio.
     * Se já havia um alarme naquele horário antes do pedido, não dá para provar que o Relógio criou outro.
     */
    fun avaliar(antes: Long?, depois: Long?, esperado: Long, tolerancia: Long = TOLERANCIA_MS): Veredito = when {
        !confere(depois, esperado, tolerancia) -> Veredito.NAO_CONFIRMADO
        confere(antes, esperado, tolerancia) -> Veredito.JA_EXISTIA
        else -> Veredito.CONFIRMADO
    }
}
