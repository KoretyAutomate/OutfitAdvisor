package com.korety.outfitadvisor

import android.content.ContentUris
import android.content.Context
import android.provider.CalendarContract
import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import java.util.Calendar
import java.util.Locale
import java.util.TimeZone

/**
 * Every occurrence in the ticked calendars between two instants, for "Share my closet
 * with an AI" (user, 2026-10-24).
 *
 * Why not @ebarooni/capacitor-calendar's listEventsInRange (Codex review, 2026-10-24):
 * it queries the Events table — one row per SERIES, with DTSTART the first occurrence —
 * so a weekly gym session that began in March never appears in a four-week window, and
 * it reads every calendar on the device before the web layer filters. Instances expands
 * recurrences, and the calendar ids go into the query, so an unticked calendar is
 * never read at all.
 *
 * Dates are computed here, from calendar fields: an all-day instance is a UTC midnight
 * and is read in UTC (in New York, Friday's all-day event is Thursday 20:00 locally);
 * the week is the local Monday's date, never elapsed milliseconds, which a daylight-
 * saving week bends by an hour.
 */
object CalendarInstances {
    private val PROJECTION = arrayOf(
        CalendarContract.Instances.EVENT_ID,
        CalendarContract.Instances.TITLE,
        CalendarContract.Instances.BEGIN,
        CalendarContract.Instances.END,
        CalendarContract.Instances.ALL_DAY,
        CalendarContract.Instances.EVENT_LOCATION,
        CalendarContract.Instances.CALENDAR_ID,
        CalendarContract.Instances.RRULE,
        CalendarContract.Instances.SELF_ATTENDEE_STATUS
    )

    fun list(ctx: Context, from: Long, to: Long, calendars: List<Long>): JSArray {
        val out = JSArray()
        if (calendars.isEmpty() || to <= from) return out
        val uri = CalendarContract.Instances.CONTENT_URI.buildUpon().also {
            ContentUris.appendId(it, from); ContentUris.appendId(it, to)
        }.build()
        val selection = "${CalendarContract.Instances.CALENDAR_ID} IN (${calendars.joinToString(",") { "?" }})"
        val args = calendars.map { it.toString() }.toTypedArray()
        ctx.contentResolver.query(uri, PROJECTION, selection, args, "${CalendarContract.Instances.BEGIN} ASC")
            ?.use { c ->
                while (c.moveToNext()) {
                    // Declined: they are not going, so it dresses nobody.
                    if (!c.isNull(8) && c.getInt(8) == CalendarContract.Attendees.ATTENDEE_STATUS_DECLINED) continue
                    val allDay = c.getInt(4) == 1
                    val begin = c.getLong(2)
                    val end = c.getLong(3)
                    val zone = if (allDay) TimeZone.getTimeZone("UTC") else TimeZone.getDefault()
                    val start = Calendar.getInstance(zone).apply { timeInMillis = begin }
                    // An all-day end is the exclusive midnight after the last day.
                    val last = Calendar.getInstance(zone).apply { timeInMillis = maxOf(begin, if (allDay) end - 1 else end) }
                    out.put(JSObject().apply {
                        put("eventId", c.getLong(0).toString())
                        put("title", c.getString(1).orEmpty())
                        put("begin", begin)
                        put("end", end)
                        put("allDay", allDay)
                        put("location", c.getString(5).orEmpty())
                        put("calendarId", c.getLong(6).toString())
                        put("recurring", !c.getString(7).isNullOrBlank())
                        put("day", iso(start))
                        put("endDay", iso(last))
                        put("weekday", start.get(Calendar.DAY_OF_WEEK) - 1)
                        put("time", if (allDay) "" else String.format(Locale.ROOT, "%02d:%02d",
                            start.get(Calendar.HOUR_OF_DAY), start.get(Calendar.MINUTE)))
                        put("week", iso(monday(start)))
                    })
                }
            }
        return out
    }

    private fun iso(c: Calendar): String = String.format(Locale.ROOT, "%04d-%02d-%02d",
        c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1, c.get(Calendar.DAY_OF_MONTH))

    /** The Monday of this date's week, by calendar fields. */
    private fun monday(c: Calendar): Calendar = (c.clone() as Calendar).apply {
        add(Calendar.DAY_OF_MONTH, -((get(Calendar.DAY_OF_WEEK) + 5) % 7))
    }
}
