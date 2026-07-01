package com.korety.outfitadvisor

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import java.util.Calendar

/**
 * Arms a once-daily EXACT alarm at the user's local wall-clock time.
 *
 * The alarm uses the device's current timezone (Calendar default tz), so it
 * automatically follows the user across timezones — fly Tokyo→London and 07:00
 * re-fires at 07:00 London time with no extra code.
 *
 * setExactAndAllowWhileIdle fires through Doze; it is one-shot, so AlarmReceiver
 * re-arms the next day after each fire (and BootReceiver re-arms after reboot).
 */
object AlarmScheduler {
    private const val PREFS = "outfit_alarm"
    private const val KEY_HOUR = "hour"
    private const val KEY_MIN = "minute"
    private const val KEY_ENABLED = "enabled"
    const val REQUEST_CODE = 4771

    fun prefs(ctx: Context): SharedPreferences =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun save(ctx: Context, hour: Int, minute: Int, enabled: Boolean) {
        prefs(ctx).edit()
            .putInt(KEY_HOUR, hour).putInt(KEY_MIN, minute)
            .putBoolean(KEY_ENABLED, enabled).apply()
    }

    fun isEnabled(ctx: Context) = prefs(ctx).getBoolean(KEY_ENABLED, false)
    fun hour(ctx: Context) = prefs(ctx).getInt(KEY_HOUR, 6)
    fun minute(ctx: Context) = prefs(ctx).getInt(KEY_MIN, 45)

    private fun pendingIntent(ctx: Context): PendingIntent {
        val i = Intent(ctx, AlarmReceiver::class.java).setAction("com.korety.outfitadvisor.FIRE")
        return PendingIntent.getBroadcast(
            ctx, REQUEST_CODE, i,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    /** Next occurrence of hour:minute in the device's local timezone. */
    fun nextFireMillis(hour: Int, minute: Int): Long {
        val now = Calendar.getInstance()
        val next = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, hour)
            set(Calendar.MINUTE, minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        if (next.timeInMillis <= now.timeInMillis) next.add(Calendar.DAY_OF_YEAR, 1)
        return next.timeInMillis
    }

    fun arm(ctx: Context, hour: Int, minute: Int) {
        save(ctx, hour, minute, true)
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val at = nextFireMillis(hour, minute)
        // If exact alarms aren't permitted, fall back to an inexact alarm so we still fire.
        if (android.os.Build.VERSION.SDK_INT < 31 || am.canScheduleExactAlarms()) {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pendingIntent(ctx))
        } else {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pendingIntent(ctx))
        }
    }

    /** Re-arm using stored prefs (after a fire or a reboot). */
    fun rearm(ctx: Context) {
        if (isEnabled(ctx)) arm(ctx, hour(ctx), minute(ctx))
    }

    fun cancel(ctx: Context) {
        save(ctx, hour(ctx), minute(ctx), false)
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        am.cancel(pendingIntent(ctx))
    }
}
