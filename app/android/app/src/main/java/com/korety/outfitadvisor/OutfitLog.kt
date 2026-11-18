package com.korety.outfitadvisor

import org.json.JSONArray
import org.json.JSONObject

/**
 * What I wore (user, 2026-11-14) — the native half of the outfit log.
 *
 * The app owns `oa.outfitlog` (index.html: outfitLog, pruneOutfitLog). The
 * notification's "Wearing it" appends to its OWN queue, `oa.nativeOutfits`, one entry
 * per day: `oa.nativeWore` is a single record overwritten per tap, so several days of
 * taps with the app closed would otherwise lose all but the last. The app folds the
 * queue in (mergeNativeOutfits) and acknowledges it in `oa.nativeOutfitsSeen`; the
 * morning worker adds what is still unfolded to the log it sends.
 *
 * Bounds are twins of index.html's OUTFIT_KEEP_DAYS / OUTFIT_MAX / OUTFIT_BYTES.
 */
object OutfitLog {
    const val KEY_QUEUE = "oa.nativeOutfits"
    const val KEEP_DAYS = 120
    const val MAX = 90
    const val BYTES = 48000

    /** The log entry for an outfit worn today, or null without the weather it was worn in. */
    fun entry(day: String, picks: JSONObject, context: JSONObject?, now: Long): JSONObject? {
        val ctx = context ?: return null
        val temp = ctx.opt("temp") as? Number ?: return null
        val worn = JSONObject()
        for (slot in SLOTS) {
            if (!picks.has(slot) || picks.isNull(slot)) continue
            val id = picks.optString(slot)
            if (id.isNotEmpty()) worn.put(slot, id)
        }
        if (worn.length() == 0) return null
        return JSONObject()
            .put("day", day)
            .put("occasion", ctx.optString("occasion").takeIf { it in OCCASIONS } ?: JSONObject.NULL)
            .put("temp", temp.toDouble())
            .put("peak", (ctx.opt("peak") as? Number)?.toDouble() ?: JSONObject.NULL)
            .put("rain", (ctx.opt("rain") as? Number)?.toDouble() ?: 0.0)
            .put("wind", (ctx.opt("wind") as? Number)?.toDouble() ?: 0.0)
            .put("picks", worn)
            .put("chose", JSONArray())      // the notification only ever logs what was served
            .put("at", now)
    }

    /** The bounded context the notification's action carries, from an /advice response. */
    fun context(raw: JSONObject, occasion: String): JSONObject? {
        val temp = raw.opt("rawPlanTemp") as? Number ?: return null
        val w = raw.optJSONObject("weather")
        return JSONObject()
            .put("occasion", occasion)
            .put("temp", temp.toDouble())
            .put("peak", (raw.opt("rawPeakTemp") as? Number)?.toDouble() ?: JSONObject.NULL)
            .put("rain", (w?.opt("rain") as? Number)?.toDouble() ?: 0.0)
            .put("wind", (w?.opt("wind") as? Number)?.toDouble() ?: 0.0)
    }

    /** One entry per day, newest last; 120 days, 90 entries, then oldest first to 48 KB. */
    fun prune(entries: List<JSONObject>, today: String, nowMs: Long): JSONArray {
        val cut = FeedbackReceiver.dayOf(nowMs - KEEP_DAYS * 86_400_000L)
        val byDay = LinkedHashMap<String, JSONObject>()
        for (e in entries) {
            val day = e.optString("day")
            if (day.length != 10 || day < cut || day > today) continue
            byDay.remove(day)
            byDay[day] = e
        }
        var out = byDay.entries.sortedBy { it.key }.map { it.value }.takeLast(MAX)
        while (out.isNotEmpty() && JSONArray(out).toString().length > BYTES) out = out.drop(1)
        return JSONArray(out)
    }

    /** The queue with this entry added under a new key (replacing any for the same day), bounded. */
    fun enqueue(queue: JSONArray, entry: JSONObject, key: String, today: String, nowMs: Long): JSONArray {
        val items = (0 until queue.length()).mapNotNull { queue.optJSONObject(it) }
            .filter { it.optJSONObject("entry")?.optString("day") != entry.optString("day") } +
            JSONObject().put("key", key).put("entry", entry)
        val keep = prune(items.mapNotNull { it.optJSONObject("entry") }, today, nowMs)
        val kept = (0 until keep.length()).map { keep.getJSONObject(it).optString("day") }.toSet()
        return JSONArray(items.filter { it.optJSONObject("entry")?.optString("day") in kept })
    }

    /** The log to send: the snapshot's, plus the queue entries it does not hold yet
     *  (by day, the queue's newer tap winning), bounded like the app's. */
    fun overlay(snapshot: JSONArray?, queue: JSONArray, seen: Set<String>, today: String, nowMs: Long): JSONArray {
        val all = mutableListOf<JSONObject>()
        if (snapshot != null) for (i in 0 until snapshot.length()) snapshot.optJSONObject(i)?.let { all.add(it) }
        for (i in 0 until queue.length()) {
            val q = queue.optJSONObject(i) ?: continue
            if (q.optString("key") in seen) continue
            q.optJSONObject("entry")?.let { all.add(it) }
        }
        return prune(all, today, nowMs)
    }

    private val SLOTS = listOf("inner", "base", "mid", "outer", "bottoms", "footwear")
    private val OCCASIONS = setOf("office", "wfh", "off")
}
