package com.korety.outfitadvisor

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

/**
 * Fires once/day at the armed time (via AlarmScheduler's setExactAndAllowWhileIdle).
 *
 * Two jobs, in order:
 *  1. RE-ARM tomorrow immediately — the exact alarm is one-shot, so if we don't
 *     re-arm here the schedule dies after a single fire.
 *  2. Wake a briefly-VISIBLE Activity via a full-screen-intent notification. On a
 *     locked/Doze device a bare startActivity() from a receiver is blocked, but a
 *     high-priority notification carrying setFullScreenIntent() is allowed to launch
 *     WakeActivity. Android then treats the ensuing GPS read as legitimate
 *     foreground location — the whole reason the MVP avoids ACCESS_BACKGROUND_LOCATION.
 */
class AlarmReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent?) {
        // 1. Re-arm for tomorrow (survives across days without a server or reboot).
        AlarmScheduler.rearm(context)

        // 2. Launch the visible wake Activity through a full-screen-intent notification.
        ensureChannel(context)

        val wake = Intent(context, WakeActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val fsi = PendingIntent.getActivity(context, WAKE_REQUEST, wake, flags)

        val notif = Notification.Builder(context, CHANNEL_WAKE)
            .setSmallIcon(context.applicationInfo.icon)
            .setContentTitle("Getting your outfit…")
            .setContentText("Checking the weather at your location")
            .setCategory(Notification.CATEGORY_ALARM)
            .setPriority(Notification.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setFullScreenIntent(fsi, true)
            .setContentIntent(fsi)
            .build()

        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(WAKE_NOTIF_ID, notif)
    }

    private fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (nm.getNotificationChannel(CHANNEL_WAKE) == null) {
                val ch = NotificationChannel(
                    CHANNEL_WAKE, "Morning wake",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply { description = "Briefly wakes the app to read weather for your outfit" }
                nm.createNotificationChannel(ch)
            }
        }
    }

    companion object {
        const val CHANNEL_WAKE = "outfit_wake"
        const val WAKE_NOTIF_ID = 4772
        const val WAKE_REQUEST = 4773
    }
}
