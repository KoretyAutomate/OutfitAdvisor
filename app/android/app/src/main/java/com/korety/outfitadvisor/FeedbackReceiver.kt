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
 * Thermal feedback from the morning notification's action buttons (2026-07-27),
 * and its "Wearing it" button (2026-10-11, see onWear).
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
 * ONE rating per calendar day across both writers (2026-10-11): a later verdict the
 * same day replaces the earlier one instead of stacking a second correction.
 *
 * JS twin: fbApply() / fbRevert() / todaysRating() / rateDay() / saveFeedback() in
 * app/www/index.html — change them together.
 */
class FeedbackReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == ACTION_WEAR) { onWear(context, intent); return }
        if (intent.action != ACTION_FEEDBACK) return
        val rating = intent.getIntExtra(EXTRA_RATING, 99)
        val delta = DELTA[rating] ?: return   // unknown rating -> do nothing, silently

        val prefs = context.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE)

        val log = try {
            JSONArray(prefs.getString(KEY_LOG, "[]") ?: "[]")
        } catch (e: Exception) {
            JSONArray()   // corrupt history must never cost the user their calibration
        }

        // ---- one rating per calendar day (twin of todaysRating / rateDay) ----
        // The day's rating is the last entry stamped today, whether the app or this
        // receiver wrote it. A later verdict REPLACES it: revert its step (twin of
        // fbRevert), drop it, then apply the new one — never stack two for a morning.
        val now = System.currentTimeMillis()
        val today = dayOf(now)
        var prevIdx = -1
        for (i in 0 until log.length()) {
            val e = log.optJSONObject(i) ?: continue
            if (e.has("at") && dayOf(e.optLong("at", 0L)) == today) prevIdx = i
        }
        var current = prefs.getString(KEY_OFFSET, "0")?.toDoubleOrNull() ?: 0.0
        current = clamp(current)   // the app clamps on read too
        val replaced = prevIdx >= 0
        if (replaced) {
            val prev = DELTA[log.optJSONObject(prevIdx)?.optInt("rating", 0) ?: 0] ?: 0.0
            current = clamp(round2(current - RATE * prev))
            log.remove(prevIdx)
        }

        // ---- offset: incremental, damped, clamped (twin of fbApply) ----
        val updated = clamp(round2(current + RATE * delta))

        // ---- history: append, prune to the newest KEEP entries (twin of saveFeedback) ----
        log.put(JSONObject().put("at", now).put("rating", rating))
        val pruned = JSONArray()
        for (i in max(0, log.length() - KEEP) until log.length()) pruned.put(log.get(i))

        prefs.edit()
            .putString(KEY_OFFSET, fmt(updated))
            .putString(KEY_LOG, pruned.toString())
            .apply()

        // The notification is done: the user answered it.
        (context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .cancel(OutfitNotification.OUTFIT_NOTIF_ID)

        val verb = if (replaced) "Changed today's rating" else "Noted"
        val msg = if (rating == 0) "$verb — keeping this calibration"
                  else "$verb — now ${if (updated > 0) "+" else ""}${fmt(updated)}°"
        Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
    }

    /**
     * "Wearing it" from the notification (2026-10-11): log a wear for each picked
     * garment exactly as the app's button does — twin of the `$("dWear").onclick`
     * logging branch, logWear() and saveWoreLogged() in app/www/index.html:
     *   oa.wearlog   — append {"itemId": id, "wornAt": epochMs}, at most once per
     *                  garment per local day (logWear is idempotent the same way)
     *   oa.woreToday — {"day": "yyyy-MM-dd", "map": picks}, today's record
     * and, because the app's button also re-stamps it through saveCloset, the
     * morning push's snapshot: each worn garment loses a unit until it comes back
     * from the wash, so tomorrow's 05:00 push does not offer it again.
     *
     * Idempotent: if today already has a record — the app's button, or an earlier
     * tap here — nothing is written. Still SharedPreferences only, no network.
     */
    private fun onWear(context: Context, intent: Intent) {
        val prefs = context.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        val today = dayOf(now)
        val picks = try {
            JSONObject(intent.getStringExtra(EXTRA_PICKS) ?: return)
        } catch (e: Exception) { return }
        val ids = pickIds(picks)
        if (ids.isEmpty()) return
        // The notification is about ONE morning. Tapped tomorrow from the shade it
        // would log yesterday's outfit as today's.
        if (intent.getStringExtra(EXTRA_DAY) != today) {
            Toast.makeText(context, "That was an earlier day's outfit — open the app to log today's",
                Toast.LENGTH_SHORT).show()
            return
        }
        if (loggedToday(prefs, today)) {
            OutfitNotification.afterWear(context)
            Toast.makeText(context, "Already logged for today", Toast.LENGTH_SHORT).show()
            return
        }
        val log = try {
            JSONArray(prefs.getString(KEY_WEARLOG, "[]") ?: "[]")
        } catch (e: Exception) {
            // Unreadable: writing a fresh one would be guessing. The app can do it.
            Toast.makeText(context, "Couldn't log it here — open the app", Toast.LENGTH_SHORT).show()
            return
        }
        for (id in ids) {
            var already = false
            for (i in 0 until log.length()) {
                val e = log.optJSONObject(i) ?: continue
                if (e.optString("itemId") == id && dayOf(e.optLong("wornAt", 0L)) == today) {
                    already = true
                    break
                }
            }
            if (!already) log.put(JSONObject().put("itemId", id).put("wornAt", now))
        }
        val edit = prefs.edit()
            .putString(KEY_WEARLOG, log.toString())
            .putString(KEY_WORE, JSONObject().put("day", today).put("map", picks).toString())
        holdInPayload(prefs.getString(AdviceWorker.KEY_PUSH_PAYLOAD, null), ids, now)
            ?.let { edit.putString(AdviceWorker.KEY_PUSH_PAYLOAD, it) }
        edit.apply()

        OutfitNotification.afterWear(context)
        Toast.makeText(context, "Rotation updated — these go to the laundry pile",
            Toast.LENGTH_SHORT).show()
    }

    /** Twin of the launch-time read of oa.woreToday: today's day AND a map. */
    private fun loggedToday(prefs: android.content.SharedPreferences, today: String): Boolean = try {
        val raw = prefs.getString(KEY_WORE, "") ?: ""
        if (raw.isEmpty()) false
        else JSONObject(raw).let { it.optString("day") == today && it.optJSONObject("map") != null }
    } catch (e: Exception) { false }

    /**
     * The push snapshot with each worn garment held: one unit fewer available, and
     * that unit's return time (worn + COOLDOWN_DAYS, the app's freeAt for an
     * unwashed wear) added to `freeAt`, which AdviceWorker.freedBy already reads.
     * Null when there is no snapshot or it cannot be read — then nothing is
     * written and the app re-stamps it on next open, as it always does.
     */
    private fun holdInPayload(raw: String?, ids: List<String>, now: Long): String? {
        if (raw == null) return null
        return try {
            val p = JSONObject(raw)
            val closet = p.optJSONArray("closet") ?: return null
            for (i in 0 until closet.length()) {
                val o = closet.optJSONObject(i) ?: continue
                if (o.optString("id") !in ids) continue
                val n = o.optInt("availableCount", 0)
                if (n < 1) continue
                o.put("availableCount", n - 1)
                val times = o.optJSONArray("freeAt") ?: JSONArray().also { o.put("freeAt", it) }
                times.put(now + COOLDOWN_DAYS * DAY_MS)
            }
            p.toString()
        } catch (e: Exception) { null }
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

        // "Wearing it" — twins of the keys app/www/index.html writes.
        const val ACTION_WEAR = "com.korety.outfitadvisor.WEAR"
        const val EXTRA_PICKS = "picks"
        const val EXTRA_DAY = "day"
        const val KEY_WEARLOG = "oa.wearlog"
        const val KEY_WORE = "oa.woreToday"
        // Twin of COOLDOWN_DAYS / DAY_MS in index.html: an unwashed wear holds a unit
        // for this long.
        private const val COOLDOWN_DAYS = 4
        private const val DAY_MS = 86_400_000L

        /** Local calendar day, "yyyy-MM-dd" — the app's todayISO()/dayISO(). */
        fun dayOf(ms: Long): String =
            java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).format(java.util.Date(ms))

        /**
         * The distinct garment ids in a picks map — twin of the app's
         * `Object.values(res.picks).filter(Boolean)`. JSON null slots are skipped:
         * optString would turn them into the string "null".
         */
        fun pickIds(picks: JSONObject?): List<String> {
            if (picks == null) return emptyList()
            val out = LinkedHashSet<String>()
            val keys = picks.keys()
            while (keys.hasNext()) {
                val v = picks.opt(keys.next())
                if (v is String && v.isNotEmpty()) out.add(v)
            }
            return out.toList()
        }

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
        const val REQ_WEAR = 4794
    }
}
