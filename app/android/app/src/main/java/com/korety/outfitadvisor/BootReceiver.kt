package com.korety.outfitadvisor

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Re-arms the daily alarm from the stored prefs whenever the OS has made the armed
 * one wrong or gone. AlarmScheduler.rearm is a no-op if the user disabled the
 * schedule, and idempotent otherwise (same PendingIntent, so a set replaces).
 *
 *  - BOOT_COMPLETED: exact alarms do NOT survive a reboot — the OS clears them.
 *    RECEIVE_BOOT_COMPLETED lets us re-arm so the morning push keeps working after
 *    the phone is restarted. BOOT_COMPLETED only: LOCKED_BOOT_COMPLETED would need
 *    directBootAware=true, and the prefs live in credential-encrypted storage
 *    anyway — unreadable before first unlock.
 *  - TIMEZONE_CHANGED / TIME_SET (ACTION_TIME_CHANGED): the alarm is armed as an
 *    absolute instant computed in the zone current at arm time. Fly Tokyo→London
 *    and the instant does not move, so the ALREADY-ARMED fire lands at 07:00 Tokyo
 *    = 23:00 London; only the re-arm after that fire would be right. Same when the
 *    clock is set. Re-arming from the stored HH:MM here puts it back on the wall
 *    clock. Both actions are on the implicit-broadcast exception list, so a
 *    manifest receiver does get them.
 *  - MY_PACKAGE_REPLACED: AlarmManager keeps alarms across an update, but a
 *    re-arm costs nothing and covers a build that changed how the alarm is set.
 *
 * A force-stop also clears the alarms and sends NOTHING — and a stopped app gets
 * no broadcasts until launched. MainActivity re-arms on open for that case.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        when (intent?.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_TIMEZONE_CHANGED,
            Intent.ACTION_TIME_CHANGED,
            Intent.ACTION_MY_PACKAGE_REPLACED -> AlarmScheduler.rearm(context)
        }
    }
}
