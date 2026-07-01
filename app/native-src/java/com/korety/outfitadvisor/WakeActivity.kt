package com.korety.outfitadvisor

import android.Manifest
import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.CancellationSignal
import android.os.Handler
import android.os.Looper
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * The full-screen-intent wake Activity — the spine of the whole app (PLAN risk #1).
 *
 * Launched by AlarmReceiver's FSI notification at the armed morning time. It becomes
 * briefly VISIBLE over the lockscreen, which is what makes the ensuing one-shot GPS
 * read count as legitimate foreground location under plain ACCESS_FINE_LOCATION —
 * no ACCESS_BACKGROUND_LOCATION, no foreground service, no paid SDK.
 *
 * Flow: show over lockscreen -> one fresh GPS fix -> POST {lat,lon,gender,style}
 * to the DGX /advice endpoint -> post the outfit as a local notification -> DISCARD
 * the coordinates (never persisted) -> finish(). If anything fails, post a soft
 * "tap to check your outfit" notification that opens the app (which has its own
 * on-device fallback), so the user always gets *something*.
 */
class WakeActivity : Activity() {

    private val main = Handler(Looper.getMainLooper())
    private var gpsCancel: CancellationSignal? = null
    private var done = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        showWhenLockedAndTurnScreenOn()
        ensureChannel()

        // Watchdog: never hang the visible activity. If we can't finish in ~11s,
        // post the fallback and bail so we don't strand a wake screen on the lock screen.
        main.postDelayed({ if (!done) finishWithFallback("timeout") }, 11_000)

        if (!hasLocationPermission()) {
            // Can't legitimately read GPS without the runtime grant. Nudge via the app.
            finishWithFallback("no-location-permission")
            return
        }
        readFreshLocation()
    }

    // ---- lock-screen visibility ------------------------------------------------

    private fun showWhenLockedAndTurnScreenOn() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                    android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                    android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            )
        }
    }

    // ---- one fresh GPS fix -----------------------------------------------------

    private fun readFreshLocation() {
        val lm = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val provider = when {
            lm.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
            lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
            else -> null
        } ?: return finishWithFallback("no-location-provider")

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                gpsCancel = CancellationSignal()
                lm.getCurrentLocation(provider, gpsCancel, mainExecutor) { loc ->
                    if (loc != null) onLocation(loc)
                    else fallbackToLastKnown(lm, provider)
                }
            } else {
                // Older devices: single-shot request, then give up to last-known.
                @Suppress("DEPRECATION")
                lm.requestSingleUpdate(provider, { loc -> onLocation(loc) }, Looper.getMainLooper())
                main.postDelayed({ if (!done) fallbackToLastKnown(lm, provider) }, 8_000)
            }
        } catch (se: SecurityException) {
            finishWithFallback("location-security-exception")
        }
    }

    private fun fallbackToLastKnown(lm: LocationManager, provider: String) {
        if (done) return
        try {
            val last = lm.getLastKnownLocation(provider)
            if (last != null) onLocation(last) else finishWithFallback("no-fix")
        } catch (se: SecurityException) {
            finishWithFallback("location-security-exception")
        }
    }

    private fun onLocation(loc: Location) {
        if (done) return
        val lat = loc.latitude
        val lon = loc.longitude
        // Network off the main thread; coords live only as locals -> discarded on return.
        Thread {
            val prefs = getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE)
            val base = (prefs.getString("oa.baseUrl", DEFAULT_BASE) ?: DEFAULT_BASE).trimEnd('/')
            val gender = prefs.getString("oa.gender", "man") ?: "man"
            val style = prefs.getString("oa.style", "casual") ?: "casual"
            val result = fetchAdvice(base, lat, lon, gender, style)
            main.post {
                if (result != null) finishWithAdvice(result) else finishWithFallback("advice-unreachable")
            }
        }.start()
    }

    // ---- DGX /advice call ------------------------------------------------------

    private data class Advice(val text: String, val source: String, val hi: Int?, val lo: Int?, val emoji: String?)

    private fun fetchAdvice(base: String, lat: Double, lon: Double, gender: String, style: String): Advice? {
        var conn: HttpURLConnection? = null
        return try {
            val body = JSONObject()
                .put("lat", lat).put("lon", lon)
                .put("gender", gender).put("style", style).put("day", 0)
                .toString()
            conn = (URL("$base/advice").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 4_000
                readTimeout = 9_000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
            }
            conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            if (conn.responseCode != 200) return null
            val json = conn.inputStream.bufferedReader().use { it.readText() }
            val o = JSONObject(json)
            val w = o.optJSONObject("weather")
            Advice(
                text = o.optString("outfit_text", "").ifBlank { o.optString("text", "") },
                source = o.optString("source", "llm"),
                hi = w?.optInt("hi"),
                lo = w?.optInt("lo"),
                emoji = w?.optString("emoji")
            )
        } catch (e: Exception) {
            null
        } finally {
            conn?.disconnect()
        }
    }

    // ---- notifications + finish ------------------------------------------------

    private fun finishWithAdvice(a: Advice) {
        val srcBadge = if (a.source == "llm") "122B" else a.source
        val header = buildString {
            a.emoji?.takeIf { it.isNotBlank() }?.let { append(it).append("  ") }
            if (a.lo != null && a.hi != null) append("${a.lo}–${a.hi}°  ")
            append("Today's outfit")
        }
        val body = a.text.ifBlank { "Tap to see today's outfit." }
        postOutfit(header, body, "AI · $srcBadge")
        wrapUp()
    }

    private fun finishWithFallback(reason: String) {
        if (done) return
        // Soft notification that opens the app; the web layer runs its own
        // on-device rule-engine estimate when the DGX is unreachable.
        postOutfit("Today's outfit", "Tap to check what to wear.", null, openApp = true)
        wrapUp()
    }

    private fun postOutfit(title: String, text: String, badge: String?, openApp: Boolean = false) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val launch = packageManager.getLaunchIntentForPackage(packageName)
            ?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            ?: Intent(this, WakeActivity::class.java)
        val pi = PendingIntent.getActivity(
            this, 4774, launch,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val style = Notification.BigTextStyle().bigText(text)
        val builder = Notification.Builder(this, CHANNEL_OUTFIT)
            .setSmallIcon(applicationInfo.icon)
            .setContentTitle(title)
            .setContentText(if (badge != null) "$badge · tap for details" else text)
            .setStyle(style)
            .setAutoCancel(true)
            .setContentIntent(pi)
        nm.notify(OUTFIT_NOTIF_ID, builder.build())
        // Clear the transient "getting your outfit…" wake notification.
        nm.cancel(AlarmReceiver.WAKE_NOTIF_ID)
    }

    /** Mark done, cancel any pending GPS request, and dismiss the visible activity. */
    private fun wrapUp() {
        done = true
        gpsCancel?.cancel()
        finish()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (nm.getNotificationChannel(CHANNEL_OUTFIT) == null) {
                nm.createNotificationChannel(
                    NotificationChannel(
                        CHANNEL_OUTFIT, "Daily outfit",
                        NotificationManager.IMPORTANCE_DEFAULT
                    ).apply { description = "Your morning outfit recommendation" }
                )
            }
        }
    }

    private fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    companion object {
        const val CHANNEL_OUTFIT = "outfit_daily"
        const val OUTFIT_NOTIF_ID = 4775
        const val DEFAULT_BASE = "http://100.112.171.54:8787"
    }
}
