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
 *   oa.feedback   — [{"at": epochMs, "rating": -2..2, "from": offset before it}],
 *                   pruned to the last 60
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
        // A rating belongs to the morning it was advised for. A notification left over
        // from an earlier day is about clothes already off, and replacing today's
        // verdict with it would be wrong — so it is ignored (pre-push reviewer,
        // 2026-10-11). Older builds' buttons carry no day and keep the old behaviour.
        val advised = intent.getStringExtra(EXTRA_DAY)
        if (advised != null && advised != today) return
        var prevIdx = -1
        for (i in 0 until log.length()) {
            val e = log.optJSONObject(i) ?: continue
            if (e.has("at") && dayOf(e.optLong("at", 0L)) == today) prevIdx = i
        }
        var current = prefs.getString(KEY_OFFSET, "0")?.toDoubleOrNull() ?: 0.0
        current = if (current.isNaN()) 0.0 else clamp(current)   // the app clamps on read too (and parseFloat("NaN") is 0 to it)
        val replaced = prevIdx >= 0
        if (replaced) {
            // Back to the offset that rating started from (twin of fbTakeBack):
            // subtracting the nominal step is wrong at the clamp. Entries written
            // before `from` existed fall back to the step.
            val prevEntry = log.optJSONObject(prevIdx)
            val from = prevEntry?.optDouble("from", Double.NaN) ?: Double.NaN
            current = if (!from.isNaN()) clamp(from)
            else clamp(round2(current - RATE * (DELTA[prevEntry?.optInt("rating", 0) ?: 0] ?: 0.0)))
            log.remove(prevIdx)
        }

        // ---- offset: incremental, damped, clamped (twin of fbApply) ----
        val updated = clamp(round2(current + RATE * delta))

        // ---- history: append, prune to the newest KEEP entries (twin of saveFeedback) ----
        log.put(JSONObject().put("at", now).put("rating", rating).put("from", round2(current)))
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
        // ONE WRITER PER KEY (2026-10-11). The app owns oa.wearlog, oa.woreToday and
        // the push snapshot; this receiver only APPENDS to its own queue and day
        // record, which the app folds in (mergeNativeWears) and the morning worker
        // applies to the snapshot (AdviceWorker.attachWardrobe). Writing the app's
        // keys from here raced the open app's saves and lost wears — raised by the
        // pre-push reviewer, 2026-10-11.
        val appLog = try { JSONArray(prefs.getString(KEY_WEARLOG, "[]") ?: "[]") } catch (e: Exception) { JSONArray() }
        val queue = nativeQueue(prefs)
        val kept = JSONArray()
        for (i in 0 until queue.length()) {
            val e = queue.optJSONObject(i) ?: continue
            if (now - e.optLong("wornAt", 0L) < QUEUE_DAYS * DAY_MS) kept.put(e)   // native prunes its own
        }
        for (id in ids) {
            val wornToday = listOf(appLog, kept).any { arr ->
                (0 until arr.length()).any { i ->
                    val e = arr.optJSONObject(i)
                    e != null && e.optString("itemId") == id && dayOf(e.optLong("wornAt", 0L)) == today
                }
            }
            if (!wornToday) {
                kept.put(JSONObject().put("itemId", id).put("wornAt", now).put("key", "n$now-$id"))
            }
        }
        prefs.edit()
            .putString(KEY_NATIVE_WEARS, kept.toString())
            .putString(KEY_NATIVE_WORE, JSONObject().put("day", today).put("map", picks).toString())
            .apply()

        OutfitNotification.afterWear(context)
        Toast.makeText(context, "Rotation updated — these go to the laundry pile",
            Toast.LENGTH_SHORT).show()
    }

    /** Twin of the launch-time read of oa.woreToday: today's day AND a map. */
    private fun loggedToday(prefs: android.content.SharedPreferences, today: String): Boolean =
        listOf(KEY_WORE, KEY_NATIVE_WORE).any { key ->
            try {
                val raw = prefs.getString(key, "") ?: ""
                raw.isNotEmpty() && JSONObject(raw).let { it.optString("day") == today && it.optJSONObject("map") != null }
            } catch (e: Exception) { false }
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
        // This receiver's OWN keys — the only ones it writes for a wear (2026-10-11).
        const val KEY_NATIVE_WEARS = "oa.nativeWears"
        const val KEY_NATIVE_WORE = "oa.nativeWore"
        private const val QUEUE_DAYS = 14
        private const val RECENT_DAYS = 7     // twin of RECENT_DAYS in index.html

        fun nativeQueue(prefs: android.content.SharedPreferences): JSONArray =
            try { JSONArray(prefs.getString(KEY_NATIVE_WEARS, "[]") ?: "[]") } catch (e: Exception) { JSONArray() }

        /**
         * The push snapshot with the native queue's wears that the app has not folded
         * in yet (the snapshot's `nativeSeen`) applied: each garment one unit fewer
         * available until worn + COOLDOWN_DAYS, and its time in `recentAt`. Units
         * already back (freeAt passed) are counted first, as AdviceWorker.freedBy does.
         * Null when there is nothing to apply.
         */
        fun applyNativeWears(raw: String?, queue: JSONArray, now: Long): String? {
            if (raw == null) return null
            return try {
                val p = JSONObject(raw)
                val seen = p.optJSONArray("nativeSeen")?.let { a -> (0 until a.length()).map { a.optString(it) }.toSet() }
                    ?: emptySet()
                val recent = p.optJSONObject("recentAt") ?: JSONObject()
                var changed = false
                for (q in 0 until queue.length()) {
                    val e = queue.optJSONObject(q) ?: continue
                    val id = e.optString("itemId")
                    val worn = e.optLong("wornAt", 0L)
                    if (e.optString("key") in seen) continue
                    // Recent-wear HISTORY for a week, independent of the laundry hold
                    // below, which ends after COOLDOWN_DAYS (pre-push reviewer, 2026-10-11).
                    if (worn > now - RECENT_DAYS * DAY_MS && recent.optLong(id, 0L) < worn) {
                        recent.put(id, worn)
                        changed = true
                    }
                    if (worn + COOLDOWN_DAYS * DAY_MS <= now) continue
                    for (arr in listOfNotNull(p.optJSONArray("closet"), p.optJSONArray("pending"))) {
                        for (i in 0 until arr.length()) {
                            val o = arr.optJSONObject(i) ?: continue
                            if (o.optString("id") != id) continue
                            var n = o.optInt("availableCount", 0)
                            val still = JSONArray()
                            val times = o.optJSONArray("freeAt")
                            if (times != null) for (k in 0 until times.length()) {
                                val t = times.optLong(k, Long.MAX_VALUE)
                                if (t <= now) n++ else still.put(t)
                            }
                            if (n < 1) continue
                            still.put(worn + COOLDOWN_DAYS * DAY_MS)
                            o.put("availableCount", n - 1)
                            o.put("freeAt", still)
                        }
                    }
                    changed = true
                }
                if (!changed) return null
                p.put("recentAt", recent)
                p.toString()
            } catch (e: Exception) { null }
        }
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
