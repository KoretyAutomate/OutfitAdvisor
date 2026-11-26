package com.korety.outfitadvisor

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CalendarContract
import androidx.core.content.ContextCompat
import java.text.Normalizer
import java.util.Calendar
import java.util.Locale
import java.util.TimeZone

/**
 * Is today a day off by the calendar? (user, 2026-11-26: "I have a day off today and
 * it's Thanksgiving" — the office days said Office; "Both public holidays and my
 * entry for the calendar".)
 *
 * Two signals, either one makes today a day off, ahead of the office days and behind
 * only the Today screen's one-day override:
 *
 *  - A public holiday: an all-day event today in a Google holiday calendar (owner
 *    "<region>#holiday@group.v.calendar.google.com" — "Holidays in United States",
 *    "日本の祝日"), read whatever the picker's ticks say, since the picker suggests
 *    leaving holiday feeds out of the trip scan. Observances (Halloween, Mother's
 *    Day) are not days off: Google writes "Observance" in their description.
 *  - Their own time-off entry: in one of THEIR OWN ticked calendars — never a shared
 *    one, a partner's "Day off" is not theirs — an event today that is all-day or
 *    covers the dressed day (08:00-19:00), not declined, whose title says time off
 *    ("Day off", "PTO", "Vacation", "Out of office", "有給", "休み").
 *
 * Only "off" leaves the phone, as the request's occasion. Titles are read here and
 * shown on the phone's own screen, never sent.
 *
 * Shared by the morning push (AdviceWorker.dayKind) and the app (OutfitAlarmPlugin.
 * dayOff) so the two can never call the same day differently.
 */
object DayOff {
    data class Off(val source: String, val label: String)   // source: "holiday" | "entry"

    private const val HOLIDAY_OWNER = "#holiday@group.v.calendar.google.com"
    private val OBSERVANCE = Regex("observance|記念日", RegexOption.IGNORE_CASE)

    // Whole words in English; Japanese has no word boundaries, so its words stand alone,
    // with オフィス (office) and オフ会 (a meet-up) kept out.
    private val TIME_OFF = Regex(
        "\\b(day[\\s-]?off|days[\\s-]?off|off|pto|vacation|vacay|holidays?|annual leave|leave|ooo|" +
            "out of (the )?office|sick( day)?|time off|bank holiday|public holiday)\\b|" +
            "休み|休暇|有給|有休|代休|振休|年休|休日|オフ(?!ィス|会|サイト)",
        RegexOption.IGNORE_CASE
    )
    // A meeting about the time off is not the time off: "PTO planning", "Holiday party";
    // nor is an off-site, which is work somewhere else (pre-push gate, 2026-11-26).
    private val NOT_OFF = Regex(
        "\\b(party|dinner|lunch|meeting|call|request|planning|deadline|sync|review|kick[\\s-]?off|sign[\\s-]?off|" +
            "off[\\s-]?sites?)\\b|会議|打ち合わせ|申請|飲み会|オフサイト",
        RegexOption.IGNORE_CASE
    )

    /** The dressed day's hours, as EveningOut's DAY_ENDS. */
    private const val DAY_STARTS = 8

    fun saysTimeOff(title: String): Boolean {
        val t = Normalizer.normalize(title, Normalizer.Form.NFKC)
        return TIME_OFF.containsMatchIn(t) && !NOT_OFF.containsMatchIn(t)
    }

    fun isObservance(description: String): Boolean =
        OBSERVANCE.containsMatchIn(Normalizer.normalize(description, Normalizer.Form.NFKC))

    fun isHolidayCalendar(owner: String): Boolean = owner.trim().lowercase(Locale.ROOT).endsWith(HOLIDAY_OWNER)

    /** Today's reason to be off, or null. Never throws. */
    fun today(ctx: Context): Off? = try {
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.READ_CALENDAR)
            != PackageManager.PERMISSION_GRANTED) null else read(ctx)
    } catch (e: Exception) {
        null
    }

    private fun read(ctx: Context): Off? {
        val holidays = holidayCalendars(ctx)
        val own = EveningOut.allowedCalendars(ctx, shared = false)
        if (holidays.isEmpty() && own.isEmpty()) return null
        val now = Calendar.getInstance()
        val today = iso(now)
        val day = (now.clone() as Calendar).apply {
            set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0)
            set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
        }
        // Clock hours from calendar fields, never elapsed milliseconds (a DST day).
        val starts = (day.clone() as Calendar).apply { set(Calendar.HOUR_OF_DAY, DAY_STARTS) }.timeInMillis
        val ends = (day.clone() as Calendar).apply { set(Calendar.HOUR_OF_DAY, EveningOut.DAY_ENDS) }.timeInMillis
        val midnight = (day.clone() as Calendar).apply { add(Calendar.DAY_OF_MONTH, 1) }.timeInMillis
        // A day either side: an all-day event is a UTC midnight, hours away from local.
        val uri = CalendarContract.Instances.CONTENT_URI.buildUpon().also {
            ContentUris.appendId(it, day.timeInMillis - DAY_MS); ContentUris.appendId(it, midnight + DAY_MS)
        }.build()
        val projection = arrayOf(
            CalendarContract.Instances.TITLE,
            CalendarContract.Instances.BEGIN,
            CalendarContract.Instances.END,
            CalendarContract.Instances.ALL_DAY,
            CalendarContract.Instances.CALENDAR_ID,
            CalendarContract.Instances.DESCRIPTION,
            CalendarContract.Instances.SELF_ATTENDEE_STATUS
        )
        // Only the holiday feeds and their own ticked calendars are queried: a row from
        // any other calendar is never read, not even to be skipped (pre-push gate,
        // 2026-11-26; the same posture as CalendarInstances.list).
        val ids = (holidays + own).toList()
        val selection = "${CalendarContract.Instances.CALENDAR_ID} IN (${ids.joinToString(",") { "?" }})"
        val args = ids.map { it.toString() }.toTypedArray()
        var entry: Off? = null
        ctx.contentResolver.query(uri, projection, selection, args, "${CalendarContract.Instances.BEGIN} ASC")?.use { c ->
            while (c.moveToNext()) {
                val cal = c.getLong(4)
                if (cal !in holidays && cal !in own) continue
                val title = c.getString(0).orEmpty().trim()
                val begin = c.getLong(1)
                val end = c.getLong(2)
                val allDay = c.getInt(3) == 1
                if (!c.isNull(6) && c.getInt(6) == CalendarContract.Attendees.ATTENDEE_STATUS_DECLINED) continue
                // An all-day instance runs UTC midnight to the exclusive UTC midnight
                // after its last day: read its dates in UTC (CalendarInstances).
                val covers = if (allDay) {
                    val utc = TimeZone.getTimeZone("UTC")
                    iso(at(begin, utc)) <= today && today <= iso(at(maxOf(begin, end - 1), utc))
                } else {
                    begin <= starts && end >= ends
                }
                if (!covers) continue
                if (cal in holidays) {
                    if (allDay && title.isNotEmpty() && !isObservance(c.getString(5).orEmpty())) {
                        return Off("holiday", title)
                    }
                } else if (cal in own && entry == null && saysTimeOff(title)) {
                    entry = Off("entry", title)
                }
            }
        }
        return entry
    }

    private fun holidayCalendars(ctx: Context): Set<Long> {
        val out = mutableSetOf<Long>()
        val projection = arrayOf(CalendarContract.Calendars._ID, CalendarContract.Calendars.OWNER_ACCOUNT)
        ctx.contentResolver.query(CalendarContract.Calendars.CONTENT_URI, projection, null, null, null)?.use { c ->
            while (c.moveToNext()) if (isHolidayCalendar(c.getString(1).orEmpty())) out.add(c.getLong(0))
        }
        return out
    }

    private const val DAY_MS = 24L * 60 * 60 * 1000

    private fun at(ms: Long, zone: TimeZone): Calendar = Calendar.getInstance(zone).apply { timeInMillis = ms }

    private fun iso(c: Calendar): String = String.format(Locale.ROOT, "%04d-%02d-%02d",
        c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1, c.get(Calendar.DAY_OF_MONTH))
}
