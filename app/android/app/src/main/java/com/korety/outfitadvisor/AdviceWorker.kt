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
            postFallback("Couldn't reach the advisor — check Battery unrestricted in the app.")
            return Result.success()
        }

        val srcBadge = if (advice.source == "llm") "122B" else advice.source
        val header = buildString {
            advice.emoji?.takeIf { it.isNotBlank() }?.let { append(it).append("  ") }
            if (advice.lo != null && advice.hi != null) append("${advice.lo}–${advice.hi}°  ")
            append("Today's outfit")
        }
        OutfitNotification.post(
            applicationContext, header,
            advice.text.ifBlank { "Tap to see today's outfit." },
            "AI · $srcBadge",
            withFeedback = advice.text.isNotBlank()
        )
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

    private fun postFallback(reason: String) {
        // No advice to rate, so no feedback buttons — see OutfitNotification.post.
        OutfitNotification.post(applicationContext, "Today's outfit", reason, null,
                                withFeedback = false)
    }

    private data class Advice(
        val text: String, val source: String,
        val hi: Int?, val lo: Int?, val emoji: String?
    )

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
                emoji = w?.optString("emoji")
            )
        } catch (e: Exception) {
            null
        } finally {
            conn?.disconnect()
        }
    }

    private fun appVersion(): String = try {
        applicationContext.packageManager
            .getPackageInfo(applicationContext.packageName, 0).versionName ?: "?"
    } catch (e: Exception) { "?" }

    companion object {
        const val DEFAULT_BASE = "http://100.112.171.54:8787"
        const val WORK_NAME = "daily-advice"
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
