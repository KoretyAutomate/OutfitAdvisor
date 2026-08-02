package com.korety.outfitadvisor

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

/**
 * Thermal feedback from the morning notification's action buttons (2026-07-27).
 *
 * Why a bare BroadcastReceiver is correct HERE, when PackingWorker needed WorkManager:
 * this does a SharedPreferences write and nothing else — no network, no LLM, microseconds
 * of main-thread work that completes long before onReceive() returns. The packing path
 * was different precisely because it had to hold the process alive for a 10-30s POST.
 * Do not grow this receiver into anything that touches the network.
 *
 * Writes the same two CapacitorStorage keys the web layer owns, so the app and the
 * notification are one shared calibration:
 *   oa.tempOffset — the scalar, e.g. "-0.75"
 *   oa.feedback   — [{"at": epochMs, "rating": -2..2}], pruned to the last 60
 *
 * JS twin: fbApply() / saveFeedback() in app/www/index.html — change them together.
 */
class FeedbackReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_FEEDBACK) return
        val rating = intent.getIntExtra(EXTRA_RATING, 99)
        val delta = DELTA[rating] ?: return   // unknown rating -> do nothing, silently

        val prefs = context.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE)

        // ---- offset: incremental, damped, clamped (twin of fbApply) ----
        val current = prefs.getString(KEY_OFFSET, "0")?.toDoubleOrNull() ?: 0.0
        val updated = clamp(round2(current + RATE * delta))

        // ---- history: append, prune to the newest KEEP entries (twin of saveFeedback) ----
        val log = try {
            JSONArray(prefs.getString(KEY_LOG, "[]") ?: "[]")
        } catch (e: Exception) {
            JSONArray()   // corrupt history must never cost the user their calibration
        }
        log.put(JSONObject().put("at", System.currentTimeMillis()).put("rating", rating))
        val pruned = JSONArray()
        for (i in max(0, log.length() - KEEP) until log.length()) pruned.put(log.get(i))

        prefs.edit()
            .putString(KEY_OFFSET, fmt(updated))
            .putString(KEY_LOG, pruned.toString())
            .apply()

        // The notification is done: the user answered it.
        (context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .cancel(OutfitNotification.OUTFIT_NOTIF_ID)

        val msg = if (rating == 0) "Thanks — keeping this calibration"
                  else "Noted — now ${if (updated > 0) "+" else ""}${fmt(updated)}°"
        Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
    }

    private fun clamp(v: Double) = max(-CLAMP, min(CLAMP, v))

    /** Match JS `Math.round(x*100)/100` exactly — see the half-up note below. */
    private fun round2(v: Double) = floor(v * 100.0 + 0.5) / 100.0

    /**
     * Render like JS `String(n)`: whole numbers without a decimal point, everything
     * else with the minimum digits. The web layer parses this back with parseFloat,
     * so "0" and "0.0" are equivalent to it — but keeping the forms identical means
     * the two writers produce byte-identical prefs, which makes drift obvious.
     */
    private fun fmt(v: Double): String {
        val r = round2(v)
        return if (r == floor(r)) r.toLong().toString() else r.toString()
    }

    companion object {
        const val ACTION_FEEDBACK = "com.korety.outfitadvisor.FEEDBACK"
        const val EXTRA_RATING = "rating"

        const val KEY_OFFSET = "oa.tempOffset"
        const val KEY_LOG = "oa.feedback"

        // Twin constants — app/www/index.html FB_DELTA / FB_RATE / FB_CLAMP / FB_KEEP.
        // The notification carries only the three coarse verdicts (Android renders at
        // most 3 actions); the -1 / +1 "a bit" steps exist in-app and are accepted
        // here too, so the two paths share one table rather than two.
        private val DELTA = mapOf(-2 to -1.5, -1 to -0.6, 0 to 0.0, 1 to 0.6, 2 to 1.5)
        private const val RATE = 0.5
        private const val CLAMP = 6.0
        private const val KEEP = 60

        // Fresh request codes — daily push owns 4771/4773/4774, packing owns 4781/4782+.
        const val REQ_COLD = 4791
        const val REQ_OK = 4792
        const val REQ_WARM = 4793
    }
}
