package com.korety.outfitadvisor

import android.content.Context
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Does the slow half of the morning push: POST /advice, then notify.
 *
 * WHY THIS EXISTS (the bug it fixes, found 2026-08-02 from the server log):
 * WakeActivity used to do the POST itself, guarded by an 11-second watchdog and a
 * 9-second read timeout. Real requests take 20-30s — the DGX runs a 122B model and
 * the closet path measured 26.19s and 29.18s. So the watchdog ALWAYS won: the user
 * got "Tap to check what to wear" every single morning, and in 30 days the server
 * never logged one request from this path. It was not flaky, it could not succeed.
 *
 * Splitting it fixes both halves at once: the visible wake screen now only does the
 * fast thing it exists for (a foreground GPS read) and finishes in ~2s instead of
 * hanging on the lock screen, while the LLM call gets as long as it needs here.
 *
 * PRIVACY — why coordinates are NOT passed as WorkManager input Data:
 * WorkManager PERSISTS input Data to its own SQLite database. Putting lat/lon there
 * would write coordinates to disk and break the locked RAM-only invariant. They are
 * handed over in process memory instead (LocationHandoff) and cleared on read. If
 * the process died in between, the handoff is empty and we re-read location here —
 * legitimate now that the app holds ACCESS_BACKGROUND_LOCATION (2026-07-15).
 */
class AdviceWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    override fun doWork(): Result {
        val fix = acquireLocation()
            ?: run {
                // Say WHICH step failed. "Tap to check what to wear" told the user
                // nothing, so three rounds of debugging went on server logs and
                // inference instead of the phone just reporting it (2026-08-11).
                postFallback(
                    if (!LocationReader.hasPermission(applicationContext))
                        "Location permission is off — tap to fix."
                    else "Couldn't get your location this morning — tap to retry."
                )
                return Result.success()   // a missed morning is not worth a retry storm
            }

        val prefs = applicationContext.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE)
        val base = (prefs.getString("oa.baseUrl", DEFAULT_BASE) ?: DEFAULT_BASE).trimEnd('/')
        val gender = prefs.getString("oa.gender", "man") ?: "man"
        val style = prefs.getString("oa.style", "casual") ?: "casual"
        val offset = prefs.getString(FeedbackReceiver.KEY_OFFSET, "0")?.toDoubleOrNull() ?: 0.0

        val advice = fetchAdvice(base, fix.first, fix.second, gender, style, offset)
        if (advice == null) {
            // The overwhelmingly common cause is the phone being unable to reach the
            // DGX while asleep — Doze deferring network, or Tailscale down. Name it.
            postFallback("Couldn't reach the advisor. Check Tailscale is connected, and Battery unrestricted in the app.")
            return Result.success()
        }

        val srcBadge = if (advice.source == "llm") "122B" else advice.source
        val header = buildString {
            advice.emoji?.takeIf { it.isNotBlank() }?.let { append(it).append("  ") }
            if (advice.lo != null && advice.hi != null) append("${advice.lo}–${advice.hi}°  ")
            append("Today's outfit")
        }
        // Written BEFORE the notification is posted: the user can tap it immediately,
        // and the app must already have the advice when it opens.
        persistToday(prefs, advice)
        OutfitNotification.post(
            applicationContext, header,
            advice.text.ifBlank { "Tap to see today's outfit." },
            "AI · $srcBadge",
            withFeedback = advice.text.isNotBlank()
        )
        maybeNotifyUpdate(base)
        return Result.success()
    }

    /**
     * Get a fix, by whichever route this device actually allows.
     *
     * Order matters and depends on the background-location grant:
     *  - "Allow all the time" → read it here, directly. No activity involved, so a
     *    locked phone is no obstacle. This is the path that makes the push work
     *    when the phone is asleep.
     *  - only "while using the app" → we CANNOT read location from here. The only
     *    legitimate source is the visible WakeActivity, which the FSI may be
     *    starting right now. Wait briefly for its handoff instead of failing
     *    instantly — the receiver enqueues us before posting that notification, so
     *    without this grace period we would always lose the race.
     */
    private fun acquireLocation(): Pair<Double, Double>? {
        LocationHandoff.take()?.let { return it }

        if (LocationReader.hasBackgroundPermission(applicationContext)) {
            LocationReader.readBlocking(applicationContext)?.let { return it }
        }

        // Either background location is missing, or the direct read failed.
        // WakeActivity is our remaining hope; give it a chance to hand one over.
        return LocationHandoff.await(HANDOFF_GRACE_MS)
    }

    /**
     * Tell the user a new build is waiting, from the one thing that runs every day
     * without them opening the app.
     *
     * The pull-only updater assumed the app gets opened while an update happens to
     * be published. It does not: v1.4 and v1.5 sat unread for a week while the very
     * fixes they contained were being debugged (2026-08-11). This is the closest
     * thing to a push notification available without FCM, which the all-local
     * design rules out.
     *
     * Notifies ONCE per published version — `oa.updNotified` — so it never becomes
     * a daily nag the user learns to swipe away.
     */
    private fun maybeNotifyUpdate(base: String) {
        var conn: HttpURLConnection? = null
        try {
            conn = (URL("$base/version").openConnection() as HttpURLConnection).apply {
                connectTimeout = 8_000
                readTimeout = 8_000
            }
            if (conn.responseCode != 200) return
            val v = JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
            val latest = v.optInt("versionCode", 0)
            val name = v.optString("versionName", "?")
            val pm = applicationContext.packageManager
            val info = pm.getPackageInfo(applicationContext.packageName, 0)
            @Suppress("DEPRECATION")
            val running = if (android.os.Build.VERSION.SDK_INT >= 28)
                info.longVersionCode.toInt() else info.versionCode
            if (latest <= running) return

            val prefs = applicationContext
                .getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE)
            if (prefs.getString(KEY_UPD_NOTIFIED, "")?.toIntOrNull() == latest) return
            prefs.edit().putString(KEY_UPD_NOTIFIED, latest.toString()).apply()

            OutfitNotification.postUpdate(
                applicationContext,
                "Outfit Advisor v$name is ready",
                "You're on v${info.versionName}. Tap to install — your closet and settings are kept."
            )
        } catch (e: Exception) {
            // An update check must never cost the user their outfit.
        } finally {
            conn?.disconnect()
        }
    }

    private fun postFallback(reason: String) {
        // No advice to rate, so no feedback buttons — see OutfitNotification.post.
        OutfitNotification.post(applicationContext, "Today's outfit", reason, null,
                                withFeedback = false)
    }

    private data class Advice(
        val text: String, val source: String,
        val hi: Int?, val lo: Int?, val emoji: String?,
        /** The whole response, so the app can show what the push already worked out. */
        val raw: JSONObject?
    )

    /**
     * Write today's advice where the web layer looks for it.
     *
     * The morning push had the answer at 06:45 and the app threw it away: opening it
     * showed a blank page, and getting the same advice back meant another 30-second
     * round trip (user, 2026-08-24). SharedPreferences named "CapacitorStorage" IS
     * the Preferences plugin's own store, so writing here is writing to the same box
     * `prefGet("oa.today")` reads from — no bridge, no message, and it works while
     * the app is not running, which is the whole point.
     *
     * The shape is the RAW /advice response plus a day stamp, because index.html's
     * saveToday() writes the same shape from the other side and the two must agree.
     * Stamped with the DAY: yesterday's advice is not stale, it is wrong.
     *
     * `place` is deliberately absent. This worker knows the coordinates and the
     * privacy rule is that they are never persisted; the app fills in its own label.
     */
    private fun persistToday(prefs: android.content.SharedPreferences, a: Advice) {
        val raw = a.raw ?: return
        try {
            val out = JSONObject()
                .put("day", today())
                .put("at", System.currentTimeMillis())
                .put("how", "push")
                .put("weather", raw.opt("weather"))
                .put("outfit", raw.opt("outfit"))
                .put("outfit_text", raw.optString("outfit_text", a.text))
                .put("source", a.source)
                .put("picks", raw.opt("picks"))
                .put("closetUsed", raw.optBoolean("closetUsed", false))
            prefs.edit().putString(KEY_TODAY, out.toString()).apply()
        } catch (e: Exception) {
            // Losing the copy must never cost the notification the user is waiting for.
        }
    }

    private fun fetchAdvice(
        base: String, lat: Double, lon: Double,
        gender: String, style: String, tempOffset: Double
    ): Advice? {
        var conn: HttpURLConnection? = null
        return try {
            val body = JSONObject()
                .put("lat", lat).put("lon", lon)
                .put("gender", gender).put("style", style).put("day", 0)
                .put("tempOffset", tempOffset.coerceIn(-6.0, 6.0))
                .also { attachWardrobe(it) }
                .toString()
            conn = (URL("$base/advice").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 10_000
                // Measured 26-29s on the closet path; a 122B behind a shared vLLM can
                // spike well past that. There is no visible UI waiting on this now,
                // so a generous ceiling costs nothing.
                readTimeout = 90_000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                // Identify the caller and its build. Without this, "did the morning
                // push reach the server?" had to be inferred from whether a closet
                // was attached — which is how a phone running a three-versions-old
                // build went unnoticed for two days (2026-08-11).
                setRequestProperty("X-OA-Client", "push/" + appVersion())
            }
            conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            if (conn.responseCode != 200) return null
            val o = JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
            val w = o.optJSONObject("weather")
            Advice(
                text = o.optString("outfit_text", ""),
                source = o.optString("source", "llm"),
                hi = w?.takeIf { it.has("hi") }?.optInt("hi"),
                lo = w?.takeIf { it.has("lo") }?.optInt("lo"),
                emoji = w?.optString("emoji"),
                raw = o
            )
        } catch (e: Exception) {
            null
        } finally {
            conn?.disconnect()
        }
    }

    /**
     * Put the wardrobe and the wearer's rules on the morning request.
     *
     * This request had been carrying NEITHER, so the one that matters most — the
     * 06:45 push, the whole point of the app — was generic advice, with a
     * prohibition the server had never been told about. It is also why the server
     * logged `closet=0/0` on every push while the app's own requests carried 17
     * items (2026-08-24).
     *
     * Read, not computed. Availability depends on the wear log, the cooldown and
     * whether a trip is under way; a Kotlin twin of that arithmetic would be a
     * fourth place for the same rules to drift, and this project has paid for twin
     * drift before. index.html writes `oa.pushPayload` whenever any of its inputs
     * change, and on every launch.
     *
     * A stale payload is REFUSED rather than sent. Items come back from the laundry
     * on a timer, so an old copy under-reports what is wearable — which is the safe
     * direction, but past a few days it stops describing the wardrobe at all, and
     * generic advice is honester than confidently dressing someone from last week's.
     */
    private fun attachWardrobe(body: JSONObject) {
        try {
            val prefs = applicationContext
                .getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE)
            val raw = prefs.getString(KEY_PUSH_PAYLOAD, null) ?: return
            val p = JSONObject(raw)
            val age = System.currentTimeMillis() - p.optLong("at", 0L)
            if (age !in 0..PUSH_PAYLOAD_MAX_AGE_MS) return
            // A trip boundary invalidates the payload ABRUPTLY, in a way age cannot
            // see: closetPayload() answers "the suitcase" on a trip and "the
            // wardrobe" otherwise, so one written at home the evening before a
            // departure is hours old and describes clothes 800 km away. The app
            // stamps the last day its answer applies; past that, send nothing and
            // let the advice be generic rather than confidently wrong.
            // EXCLUSIVE. The stamp is the first day the payload is wrong, and it is
            // already wrong on that day: one stamped with a trip's departure date
            // describes the home wardrobe on the morning of the flight. `>=`, and
            // the field is named for the boundary so it cannot be misread as the
            // last good day.
            val validBefore = p.optString("validBefore", "")
            if (validBefore.isNotEmpty() && today() >= validBefore) return
            val closet = p.optJSONArray("closet") ?: return
            if (closet.length() == 0) return
            body.put("closet", closet)
            val rules = p.optJSONArray("rules")
            if (rules != null && rules.length() > 0) body.put("rules", rules)
        } catch (e: Exception) {
            // A wardrobe we cannot read costs generic advice, never the notification.
        }
    }

    /** Local calendar day, the same "yyyy-MM-dd" the app compares against. */
    private fun today(): String =
        java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US)
            .format(java.util.Date())

    private fun appVersion(): String = try {
        applicationContext.packageManager
            .getPackageInfo(applicationContext.packageName, 0).versionName ?: "?"
    } catch (e: Exception) { "?" }

    companion object {
        const val DEFAULT_BASE = "http://100.112.171.54:8787"
        const val WORK_NAME = "daily-advice"
        const val KEY_UPD_NOTIFIED = "oa.updNotified"
        /** Twin of TODAY_KEY in index.html — both sides write this one key. */
        const val KEY_TODAY = "oa.today"
        /** Twin of PUSH_PAYLOAD_KEY in index.html — the app writes it, this reads it. */
        const val KEY_PUSH_PAYLOAD = "oa.pushPayload"
        /** Past this the payload no longer describes the wardrobe; send nothing. */
        const val PUSH_PAYLOAD_MAX_AGE_MS = 7L * 24 * 60 * 60 * 1000
        // How long to wait for WakeActivity's fix when we cannot read location
        // ourselves. Long enough for the FSI to start an activity and get a fix,
        // short enough that a device where the FSI never fires still produces the
        // fallback notification while the alarm's Doze allowance is alive.
        const val HANDOFF_GRACE_MS = 12_000L
    }
}

/**
 * In-process handoff of one GPS fix from WakeActivity to AdviceWorker.
 *
 * Deliberately NOT WorkManager input Data, and deliberately not persisted anywhere:
 * coordinates are RAM-only by locked product decision. Cleared as soon as it is read
 * so a fix cannot linger in memory after the push it was taken for.
 */
object LocationHandoff {
    @Volatile private var fix: Pair<Double, Double>? = null
    @Volatile private var takenAt: Long = 0L

    @Synchronized fun put(lat: Double, lon: Double) {
        fix = lat to lon
        takenAt = System.currentTimeMillis()
    }

    /** Returns the fix once, then forgets it. Stale fixes are discarded, not used. */
    @Synchronized fun take(): Pair<Double, Double>? {
        val f = fix
        fix = null
        if (f == null || System.currentTimeMillis() - takenAt > MAX_AGE_MS) return null
        return f
    }

    /**
     * Block until a fix arrives or the timeout expires. Used only when this process
     * cannot read location itself and must rely on WakeActivity providing one.
     * Polls rather than waits on a monitor: put() is called from the main thread and
     * the sleep here is on a Worker thread, so a coarse poll is simpler and cannot
     * deadlock.
     */
    fun await(timeoutMs: Long): Pair<Double, Double>? {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            take()?.let { return it }
            try { Thread.sleep(250) } catch (ie: InterruptedException) {
                Thread.currentThread().interrupt(); return null
            }
        }
        return take()
    }

    private const val MAX_AGE_MS = 10 * 60 * 1000L
}
