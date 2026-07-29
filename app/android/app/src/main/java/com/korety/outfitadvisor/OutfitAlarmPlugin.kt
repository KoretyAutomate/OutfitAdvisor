package com.korety.outfitadvisor

import android.Manifest
import android.app.AlarmManager
import android.content.Context
import android.os.Build
import com.getcapacitor.JSObject
import com.getcapacitor.PermissionState
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.getcapacitor.annotation.Permission
import com.getcapacitor.annotation.PermissionCallback

/**
 * JS bridge for the once-daily morning alarm.
 *
 * The web layer (app/www/index.html) calls:
 *   Plugins.OutfitAlarm.arm({hour, minute})   when the schedule is enabled/saved
 *   Plugins.OutfitAlarm.cancel()              when the toggle is turned off
 *   Plugins.OutfitAlarm.bgLocation()          background-location state (+request)
 *
 * arm() reports whether the alarm is exact so the UI *could* surface a degraded-mode
 * hint; either way AlarmScheduler falls back to an inexact allow-while-idle alarm.
 */
@CapacitorPlugin(
    name = "OutfitAlarm",
    permissions = [Permission(
        alias = "bgLocation",
        strings = [Manifest.permission.ACCESS_BACKGROUND_LOCATION]
    )]
)
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

    /**
     * Ground truth for the UI's "next push" line: reports what is actually
     * armed (the native prefs the alarm re-arms from), not what the web layer
     * last saved — the two can diverge and the UI should show the real thing.
     */
    @PluginMethod
    fun status(call: PluginCall) {
        val enabled = AlarmScheduler.isEnabled(context)
        val hour = AlarmScheduler.hour(context)
        val minute = AlarmScheduler.minute(context)
        val ret = JSObject()
        ret.put("armed", enabled)
        ret.put("hour", hour)
        ret.put("minute", minute)
        ret.put("exact", canScheduleExact(context))
        if (enabled) ret.put("nextFireMillis", AlarmScheduler.nextFireMillis(hour, minute))
        call.resolve(ret)
    }

    /**
     * "Allow all the time" location (user request 2026-07-15 — reverses the
     * original no-background-location decision, see PLAN). Without the manifest
     * declaration the option doesn't even EXIST in Android's settings UI.
     *
     * bgLocation()               -> {granted}
     * bgLocation({request:true}) -> asks; on Android 11+ the OS shows no inline
     *   dialog — it routes to the app's location-settings screen where the user
     *   can pick "Allow all the time". Only meaningful once foreground location
     *   is already granted (the OS auto-denies otherwise), which saveSchedule()
     *   guarantees by requesting Geolocation permissions first.
     */
    @PluginMethod
    fun bgLocation(call: PluginCall) {
        val granted = getPermissionState("bgLocation") == PermissionState.GRANTED
        if (granted || call.getBoolean("request") != true) {
            call.resolve(JSObject().put("granted", granted))
            return
        }
        requestPermissionForAlias("bgLocation", call, "bgLocationResult")
    }

    @PermissionCallback
    private fun bgLocationResult(call: PluginCall) {
        call.resolve(JSObject().put(
            "granted", getPermissionState("bgLocation") == PermissionState.GRANTED))
    }

    private fun canScheduleExact(ctx: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        return am.canScheduleExactAlarms()
    }
}
