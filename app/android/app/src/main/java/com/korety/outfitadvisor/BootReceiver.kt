package com.korety.outfitadvisor

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Exact alarms do NOT survive a reboot — the OS clears them. RECEIVE_BOOT_COMPLETED
 * lets us re-arm from the stored prefs so the morning push keeps working after the
 * phone is restarted. AlarmScheduler.rearm is a no-op if the user disabled the schedule.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action == Intent.ACTION_BOOT_COMPLETED ||
            action == Intent.ACTION_LOCKED_BOOT_COMPLETED ||
            action == "android.intent.action.QUICKBOOT_POWERON"
        ) {
            AlarmScheduler.rearm(context)
        }
    }
}
