package com.korety.outfitadvisor

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Exact alarms do NOT survive a reboot — the OS clears them. RECEIVE_BOOT_COMPLETED
 * lets us re-arm from the stored prefs so the morning push keeps working after the
 * phone is restarted. AlarmScheduler.rearm is a no-op if the user disabled the schedule.
 *
 * BOOT_COMPLETED only: LOCKED_BOOT_COMPLETED would need directBootAware=true, and the
 * prefs live in credential-encrypted storage anyway — unreadable before first unlock.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action == Intent.ACTION_BOOT_COMPLETED) {
            AlarmScheduler.rearm(context)
        }
    }
}
