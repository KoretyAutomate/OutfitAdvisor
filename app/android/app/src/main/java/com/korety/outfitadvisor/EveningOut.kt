package com.korety.outfitadvisor

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CalendarContract
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.util.Calendar

/**
 * Is the wearer out tonight, and until when? (user, 2026-10-10)
 *
 * "We should go over feels like temperature between 8am and 7pm unless there is an
 * event in our calendar." The day is dressed for 08:00-19:00; an evening event
 * stretches it to the event's end, so a 22:00 walk home is dressed for.
 *
 * What counts as going out: a timed (not all-day) event today that runs past 19:00,
 * in a calendar the wearer OWNS and ticked in the picker, that has a place — a
 * location that is not a video link — and was not declined. An evening event with
 * no place is as often a call or a reminder as a dinner, and guessing "out" costs
 * a coat on a night at home (user agreed, 2026-10-10).
 *
 * Only the HOUR leaves the phone. Title, place and notes are read here and nowhere
 * else, the same rule the trip scan follows.
 *
 * Shared by the morning push (AdviceWorker) and the app (OutfitAlarmPlugin.eveningOut)
 * so the two can never plan the same day differently.
 */
object EveningOut {
    const val DAY_ENDS = 19
    // A conferencing service, or a location that says nothing but "online". NOT any
    // link: "Blue Note, 131 W 3rd St https://maps.app.goo.gl/..." is a night out.
    // Raised by the pre-push reviewer, 2026-10-10. Pinned by test_feels_like.py.
    private val VIDEO = Regex(
        "zoom\\.us|meet\\.google|teams\\.microsoft|teams\\.live|webex|whereby\\.com|gotomeeting|" +
            "^\\s*(online|virtual|remote|phone|call|video call|zoom|teams|google meet)\\s*$",
        RegexOption.IGNORE_CASE
    )

    /** The picker's rule for a calendar that is not the wearer's own: either test. */
    fun isShared(owner: String, account: String, access: Int): Boolean {
        val otherOwner = owner.isNotEmpty() && account.isNotEmpty() && !owner.equals(account, ignoreCase = true)
        return otherOwner || access < CalendarContract.Calendars.CAL_ACCESS_OWNER
    }

    fun isPlace(location: String?): Boolean {
        val l = location.orEmpty().trim()
        return l.isNotEmpty() && !VIDEO.containsMatchIn(l)
    }

    /** End hour 20..24 of the latest evening event today, or null. Never throws. */
    fun until(ctx: Context): Int? = try {
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.READ_CALENDAR)
            != PackageManager.PERMISSION_GRANTED) null else readUntil(ctx)
    } catch (e: Exception) {
        null
    }

    private fun readUntil(ctx: Context): Int? {
        val allowed = allowedCalendars(ctx)
        if (allowed.isEmpty()) return null
        val day = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0)
            set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
        }.timeInMillis
        // Clock hours, from calendar fields — never elapsed milliseconds, which are an
        // hour off on a daylight-saving day. Raised by the pre-push reviewer, 2026-10-10.
        val from = Calendar.getInstance().apply {
            timeInMillis = day; set(Calendar.HOUR_OF_DAY, DAY_ENDS)
        }.timeInMillis
        val midnight = Calendar.getInstance().apply {
            timeInMillis = day; add(Calendar.DAY_OF_MONTH, 1)
        }.timeInMillis
        val uri = CalendarContract.Instances.CONTENT_URI.buildUpon().also {
            ContentUris.appendId(it, from); ContentUris.appendId(it, midnight)
        }.build()
        val projection = arrayOf(
            CalendarContract.Instances.BEGIN,
            CalendarContract.Instances.END,
            CalendarContract.Instances.ALL_DAY,
            CalendarContract.Instances.CALENDAR_ID,
            CalendarContract.Instances.EVENT_LOCATION,
            CalendarContract.Instances.SELF_ATTENDEE_STATUS
        )
        var latest: Int? = null
        ctx.contentResolver.query(uri, projection, null, null, null)?.use { c ->
            while (c.moveToNext()) {
                val begin = c.getLong(0)
                val end = c.getLong(1)
                if (c.getInt(2) == 1) continue                         // all-day
                if (c.getLong(3) !in allowed) continue
                if (!isPlace(c.getString(4))) continue
                if (!c.isNull(5) && c.getInt(5) == CalendarContract.Attendees.ATTENDEE_STATUS_DECLINED) continue
                if (begin < day || end <= from) continue                // a multi-day span is a trip, not an evening
                // The clock hour it ends, rounded up: out until 21:30 is dressed for 22:00.
                val h = endHour(end, midnight)
                if (h > DAY_ENDS && h > (latest ?: 0)) latest = h
            }
        }
        return latest
    }

    private fun endHour(end: Long, midnight: Long): Int {
        if (end >= midnight) return 24
        val c = Calendar.getInstance().apply { timeInMillis = end }
        val past = c.get(Calendar.MINUTE) > 0 || c.get(Calendar.SECOND) > 0
        return c.get(Calendar.HOUR_OF_DAY) + if (past) 1 else 0
    }

    /** The wearer's own calendars, narrowed to the ones ticked in the picker. */
    private fun allowedCalendars(ctx: Context): Set<Long> {
        val prefs = ctx.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE)
        val sel = try { JSONObject(prefs.getString("oa.calendars", null) ?: "{}") } catch (e: Exception) { JSONObject() }
        val mode = sel.optString("mode", "all")
        if (mode == "none") return emptySet()
        val ticked = sel.optJSONArray("ids")?.let { a -> (0 until a.length()).map { a.optString(it) }.toSet() } ?: emptySet()
        val out = mutableSetOf<Long>()
        val projection = arrayOf(
            CalendarContract.Calendars._ID,
            CalendarContract.Calendars.ACCOUNT_NAME,
            CalendarContract.Calendars.OWNER_ACCOUNT,
            CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL
        )
        ctx.contentResolver.query(CalendarContract.Calendars.CONTENT_URI, projection, null, null, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getLong(0)
                val access = if (c.isNull(3)) CalendarContract.Calendars.CAL_ACCESS_OWNER else c.getInt(3)
                if (isShared(c.getString(2).orEmpty().trim(), c.getString(1).orEmpty().trim(), access)) continue
                if (mode == "some" && id.toString() !in ticked) continue
                out.add(id)
            }
        }
        return out
    }
}
