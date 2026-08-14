package com.korety.outfitadvisor

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.location.Geocoder
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import com.getcapacitor.JSObject
import com.getcapacitor.PermissionState
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.getcapacitor.annotation.Permission
import com.getcapacitor.annotation.PermissionCallback
import java.util.Locale

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

    /**
     * Everything that must be true for the morning push to work WITH THE PHONE
     * ASLEEP, reported honestly so the UI can stop guessing.
     *
     * Added 2026-08-09 after the user observed the push only ever delivered full
     * advice when the phone happened to be awake. Each of these fails silently and
     * in a way that looks identical from the outside, which is why it took a user
     * report to find: the app looked armed, and was.
     */
    @PluginMethod
    fun pushReadiness(call: PluginCall) {
        val ctx = context
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager

        // Android 14+ stopped auto-granting USE_FULL_SCREEN_INTENT to apps that are
        // not calling/alarm apps. When false the FSI silently degrades to a heads-up
        // notification and WakeActivity never launches on a locked phone — which is
        // why the alarm must no longer depend on it.
        val fsi = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE)
            nm.canUseFullScreenIntent() else true

        call.resolve(
            JSObject()
                .put("notifications", nm.areNotificationsEnabled())
                .put("exactAlarm", canScheduleExact(ctx))
                .put("bgLocation", getPermissionState("bgLocation") == PermissionState.GRANTED)
                .put("batteryUnrestricted", pm.isIgnoringBatteryOptimizations(ctx.packageName))
                .put("fullScreenIntent", fsi)
        )
    }

    /**
     * Ask to be exempt from Doze network deferral. There is no inline dialog we can
     * host — the OS owns this screen — so we open it and the web layer re-checks on
     * resume, same pattern as bgLocation().
     */
    @PluginMethod
    fun requestBatteryUnrestricted(call: PluginCall) {
        val ctx = context
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
        if (pm.isIgnoringBatteryOptimizations(ctx.packageName)) {
            call.resolve(JSObject().put("granted", true))
            return
        }
        try {
            ctx.startActivity(
                Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                    .setData(Uri.parse("package:${ctx.packageName}"))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        } catch (e: Exception) {
            // Some OEM builds hide the direct dialog; fall back to the settings list.
            try {
                ctx.startActivity(
                    Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                )
            } catch (ignored: Exception) {}
        }
        call.resolve(JSObject().put("granted", false))
    }

    /** Open the OS screen where "Allow full screen intents" can be turned on. */
    @PluginMethod
    fun requestFullScreenIntent(call: PluginCall) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            try {
                context.startActivity(
                    Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT)
                        .setData(Uri.parse("package:${context.packageName}"))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                )
            } catch (ignored: Exception) {}
        }
        call.resolve(JSObject().put("opened", true))
    }

    /**
     * Name a coordinate — locality, state, postal code — using ANDROID'S OWN
     * geocoder (2026-08-14).
     *
     * Deliberately not a web geocoding service: naming the user's home means
     * sending their exact position somewhere, and every public geocoder is a third
     * party they have no relationship with. The platform geocoder resolves through
     * services the phone already talks to, so this introduces no new recipient of
     * the user's location — the same reasoning that keeps raw calendar strings away
     * from Open-Meteo.
     *
     * Used once, when the user sets their home area. Nothing here is stored by the
     * plugin; the web layer decides what to keep.
     */
    @PluginMethod
    fun reverseGeocode(call: PluginCall) {
        val lat = call.getDouble("lat")
        val lon = call.getDouble("lon")
        if (lat == null || lon == null) { call.reject("lat/lon required"); return }
        if (!Geocoder.isPresent()) { call.reject("no geocoder on this device"); return }

        val geo = Geocoder(context, Locale.getDefault())
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            // The blocking overload is deprecated on 33+; the callback form is the
            // supported path and keeps the network work off the caller's thread.
            geo.getFromLocation(lat, lon, 1, object : Geocoder.GeocodeListener {
                override fun onGeocode(addresses: MutableList<android.location.Address>) {
                    call.resolve(addressToJs(addresses.firstOrNull()))
                }
                override fun onError(msg: String?) { call.reject(msg ?: "geocode failed") }
            })
        } else {
            Thread {
                try {
                    @Suppress("DEPRECATION")
                    val a = geo.getFromLocation(lat, lon, 1)?.firstOrNull()
                    call.resolve(addressToJs(a))
                } catch (e: Exception) {
                    call.reject(e.message ?: "geocode failed")
                }
            }.start()
        }
    }

    private fun addressToJs(a: android.location.Address?): JSObject {
        // A readable label, coarsest-useful first. Postal code is included because
        // the user asked to treat "that zip area" as home — it is the unit people
        // actually think of as "where I live".
        val locality = a?.locality ?: a?.subAdminArea
        val label = listOfNotNull(
            locality, a?.adminArea, a?.postalCode
        ).distinct().joinToString(", ").ifBlank { a?.countryName ?: "" }
        return JSObject()
            .put("locality", locality ?: "")
            .put("adminArea", a?.adminArea ?: "")
            .put("postalCode", a?.postalCode ?: "")
            .put("country", a?.countryName ?: "")
            .put("label", label)
    }

    private fun canScheduleExact(ctx: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        return am.canScheduleExactAlarms()
    }
}
