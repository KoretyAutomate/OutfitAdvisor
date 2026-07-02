package com.korety.outfitadvisor

import android.app.AlarmManager
import android.content.Context
import android.os.Build
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin

/**
 * JS bridge for the once-daily morning alarm.
 *
 * The web layer (app/www/index.html) calls:
 *   Plugins.OutfitAlarm.arm({hour, minute})   when the schedule is enabled/saved
 *   Plugins.OutfitAlarm.cancel()              when the toggle is turned off
 *
 * arm() reports whether the alarm is exact so the UI *could* surface a degraded-mode
 * hint; either way AlarmScheduler falls back to an inexact allow-while-idle alarm.
 */
@CapacitorPlugin(name = "OutfitAlarm")
class OutfitAlarmPlugin : Plugin() {

    @PluginMethod
    fun arm(call: PluginCall) {
        val hour = call.getInt("hour") ?: 6
        val minute = call.getInt("minute") ?: 45
        if (hour !in 0..23 || minute !in 0..59) {
            call.reject("hour/minute out of range")
            return
        }
        AlarmScheduler.arm(context, hour, minute)
        val ret = JSObject()
        ret.put("armed", true)
        ret.put("hour", hour)
        ret.put("minute", minute)
        ret.put("exact", canScheduleExact(context))
        call.resolve(ret)
    }

    @PluginMethod
    fun cancel(call: PluginCall) {
        AlarmScheduler.cancel(context)
        val ret = JSObject()
        ret.put("armed", false)
        call.resolve(ret)
    }

    private fun canScheduleExact(ctx: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        return am.canScheduleExactAlarms()
    }
}
