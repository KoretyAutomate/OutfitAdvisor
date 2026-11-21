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
            Intent.ACTION_BOOT_COMPLETED -> {
                AlarmScheduler.rearm(context)
                // A confirmation's notification doesn't survive a reboot, so nothing
                // can reach its prompt; drop it and let the job start over.
                SelfUpdate.abandonPending(context)
                UpdateWorker.schedule(context)
            }
            Intent.ACTION_TIMEZONE_CHANGED,
            Intent.ACTION_TIME_CHANGED -> AlarmScheduler.rearm(context)
            Intent.ACTION_MY_PACKAGE_REPLACED -> {
                AlarmScheduler.rearm(context)
                UpdateWorker.schedule(context)
                announceSelfUpdate(context)
            }
        }
    }

    /**
     * "Updated to vX", only after an update this app installed itself. A silent
     * update must still be visible somewhere, and an adb or browser install
     * doesn't need a notice.
     */
    private fun announceSelfUpdate(context: Context) {
        val prefs = SelfUpdate.prefs(context)
        if (prefs.getString(SelfUpdate.KEY_INSTALLING, null) == null) return
        prefs.edit().remove(SelfUpdate.KEY_INSTALLING).apply()
        val name = try {
            context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "?"
        } catch (e: Exception) { "?" }
        OutfitNotification.postUpdate(context, "Outfit Advisor updated to v$name",
            "Installed by itself. Your closet and settings are kept.")
    }
}
