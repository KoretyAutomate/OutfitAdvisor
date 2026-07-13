package com.korety.outfitadvisor

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.abs

/**
 * PackingWorker — fires N days before a confirmed trip and notifies the user to pack.
 *
 * WHY A WORKER AND NOT A BROADCAST RECEIVER (the bug this design exists to avoid):
 * a BroadcastReceiver's onReceive() runs on the main thread and, once it returns,
 * the process holds no live component and can be killed immediately. The daily
 * outfit push gets away with a background thread only because the visible
 * WakeActivity keeps the process alive while it runs. A packing push has no visible
 * activity and fires days out on a cold, idle phone — precisely the case where an
 * unmanaged thread is killed mid-request. It would pass every warm-process test and
 * fail in the field. WorkManager owns the execution context instead, survives
 * reboot on its own, and needs no exact-alarm permission.
 *
 * PRIVACY: the trip's destination is already stored as COORDINATES (the phone
 * resolved the city at confirm time), so this worker never touches the calendar and
 * never sends a place name or event text anywhere. It POSTs {lat, lon, start, end,
 * type, styles} and nothing else.
 *
 * The closet is deliberately NOT sent from here. The notification only shows the
 * city and the weather ("Osaka - 8-16C, rain Wed"), so the packing list itself is
 * not needed to build it; tapping opens the app, which regenerates the full
 * closet-aware list with the availability math that lives in one place, in JS.
 * That keeps the packAvail/cooldown rules from being duplicated in Kotlin, where
 * they would silently drift.
 */
class PackingWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {

    override fun doWork(): Result {
        val tripId = inputData.getString(KEY_TRIP_ID) ?: return Result.success()
        val prefs = applicationContext.getSharedPreferences("CapacitorStorage",
            Context.MODE_PRIVATE)

        val trip = findTrip(prefs.getString("oa.trips", "[]") ?: "[]", tripId)
        // The trip was deleted, or its dates already passed. Never fire retroactively.
            ?: return Result.success()

        val startMs = localMidnight(trip.optString("start"))
        if (startMs <= 0L || System.currentTimeMillis() > startMs) return Result.success()

        val base = prefs.getString("oa.baseUrl", WakeActivity.DEFAULT_BASE)
            ?: WakeActivity.DEFAULT_BASE
        val gender = prefs.getString("oa.gender", "man") ?: "man"
        val place = trip.optString("place").ifBlank { "your trip" }

        val summary = try {
            fetchSummary(base, trip, gender)
        } catch (e: Exception) {
            // Transient network/server trouble: back off and retry rather than
            // burning the one notification the user gets for this trip.
            if (runAttemptCount < 3) return Result.retry()
            null
        }

        notify(place, summary, trip)
        return Result.success()
    }

    /** POST /packing WITHOUT a closet — we only need the trip's weather summary. */
    private fun fetchSummary(base: String, trip: JSONObject, gender: String): Summary {
        val body = JSONObject()
            .put("lat", trip.getDouble("lat"))
            .put("lon", trip.getDouble("lon"))
            .put("start", trip.getString("start"))
            .put("end", trip.getString("end"))
            .put("type", trip.optString("type", "vacation"))
            .put("gender", gender)
            .put("styles", trip.optJSONArray("styles") ?: JSONArray().put("casual"))
            .toString()

        val conn = (URL("${base.trimEnd('/')}/packing").openConnection() as HttpURLConnection)
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json")
        conn.connectTimeout = 8000
        conn.readTimeout = 25000
        try {
            conn.outputStream.use { it.write(body.toByteArray()) }
            if (conn.responseCode !in 200..299) throw IllegalStateException("http ${conn.responseCode}")
            val json = JSONObject(conn.inputStream.bufferedReader().readText())
            val s = json.getJSONObject("forecast").getJSONObject("summary")
            val days = json.getJSONObject("forecast").getJSONArray("days")
            var wettest: String? = null
            var worst = 0
            for (i in 0 until days.length()) {
                val d = days.getJSONObject(i)
                if (d.optInt("rain") > worst && d.optInt("rain") >= 50) {
                    worst = d.optInt("rain"); wettest = weekday(d.optString("date"))
                }
            }
            return Summary(
                lo = s.optInt("loMin"), hi = s.optInt("hiMax"),
                rainDays = s.optInt("rainDays"), nDays = s.optInt("nDays"),
                normals = s.optString("mode") == "normals",
                wettestDay = wettest,
            )
        } finally {
            conn.disconnect()
        }
    }

    /**
     * The notification names the CITY and the weather, but never the dates.
     * A date range plus a destination is identifying, and notification text is
     * readable by any NotificationListenerService and sits on the lock screen —
     * so it must not re-leak what the server deliberately refuses to log.
     */
    private fun notify(place: String, s: Summary?, trip: JSONObject) {
        val nm = applicationContext
            .getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        ensureChannel(nm)

        val emoji = if (trip.optString("type") == "business") "💼" else "🏖️"
        val title = "$emoji Pack for $place"
        val body = when {
            s == null -> "Time to pack. Tap for your packing list."
            else -> buildString {
                append("${s.lo}°–${s.hi}°")
                if (s.rainDays > 0) {
                    append(" · ")
                    append(s.wettestDay?.let { "rain $it" }
                        ?: "${s.rainDays} of ${s.nDays} days wet")
                }
                if (s.normals) append(" · typical, not a forecast")
                append(" — tap for your packing list")
            }
        }

        val launch = applicationContext.packageManager
            .getLaunchIntentForPackage(applicationContext.packageName)
            ?.apply { addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP) }
        val pi = PendingIntent.getActivity(
            applicationContext, PACK_TAP_REQUEST, launch ?: Intent(),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)

        val n = NotificationCompat.Builder(applicationContext, CHANNEL_PACKING)
            .setSmallIcon(android.R.drawable.ic_menu_agenda)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(pi)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()

        // Distinct id per trip so two trips don't overwrite each other's notification
        // — and well clear of the daily push's 4772/4775.
        nm.notify(PACK_NOTIF_BASE + abs(trip.optString("id").hashCode() % 1000), n)
    }

    private fun ensureChannel(nm: NotificationManager) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        if (nm.getNotificationChannel(CHANNEL_PACKING) != null) return
        nm.createNotificationChannel(NotificationChannel(
            CHANNEL_PACKING, "Trip packing reminders",
            NotificationManager.IMPORTANCE_DEFAULT
        ).apply { description = "A reminder of what to pack before a trip." })
    }

    private fun findTrip(json: String, id: String): JSONObject? {
        return try {
            val arr = JSONArray(json)
            (0 until arr.length()).map { arr.getJSONObject(it) }
                .firstOrNull { it.optString("id") == id }
        } catch (e: Exception) { null }
    }

    private data class Summary(val lo: Int, val hi: Int, val rainDays: Int,
                               val nDays: Int, val normals: Boolean,
                               val wettestDay: String?)

    companion object {
        const val KEY_TRIP_ID = "tripId"
        const val CHANNEL_PACKING = "outfit_packing"
        const val PACK_NOTIF_BASE = 4782   // daily push owns 4772 / 4775
        const val PACK_TAP_REQUEST = 4781  // daily push owns 4771 / 4773 / 4774

        fun workName(tripId: String) = "packing-$tripId"

        /** Local midnight of an ISO yyyy-MM-dd date, or 0 if unparseable. */
        fun localMidnight(iso: String): Long {
            val p = iso.split("-")
            if (p.size != 3) return 0L
            return try {
                java.util.Calendar.getInstance().apply {
                    set(p[0].toInt(), p[1].toInt() - 1, p[2].toInt(), 0, 0, 0)
                    set(java.util.Calendar.MILLISECOND, 0)
                }.timeInMillis
            } catch (e: Exception) { 0L }
        }

        fun weekday(iso: String): String? {
            val ms = localMidnight(iso)
            if (ms <= 0L) return null
            return java.text.SimpleDateFormat("EEE", java.util.Locale.getDefault())
                .format(java.util.Date(ms))
        }
    }
}
