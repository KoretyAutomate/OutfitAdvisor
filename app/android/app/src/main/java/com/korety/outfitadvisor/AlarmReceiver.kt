package com.korety.outfitadvisor

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkManager

/**
 * Fires once/day at the armed time (via AlarmScheduler's setExactAndAllowWhileIdle).
 *
 * Two jobs, in order:
 *  1. RE-ARM tomorrow immediately — the exact alarm is one-shot, so if we don't
 *     re-arm here the schedule dies after a single fire.
 *  2. Wake a briefly-VISIBLE Activity via a full-screen-intent notification. On a
 *     locked/Doze device a bare startActivity() from a receiver is blocked, but a
 *     high-importance notification carrying setFullScreenIntent() is allowed to
 *     launch WakeActivity. Android then treats the ensuing GPS read as legitimate
 *     foreground location — the whole reason the MVP avoids ACCESS_BACKGROUND_LOCATION.
 */
class AlarmReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent?) {
        // 1. Re-arm for tomorrow (survives across days without a server or reboot).
        AlarmScheduler.rearm(context)

        // 2. START THE WORK OURSELVES. This used to be WakeActivity's job, which
        //    made the entire feature depend on that activity launching — and on
        //    Android 14+ USE_FULL_SCREEN_INTENT is no longer auto-granted to apps
        //    that aren't calling/alarm apps, so on a LOCKED phone the FSI silently
        //    degrades to a heads-up notification and the activity never starts.
        //    The user's own observation nailed it (2026-08-09): full advice when
        //    the phone was open (they saw the notification and it launched), never
        //    when it was asleep.
        //
        //    The worker reads location itself when background location is granted,
        //    so the happy path no longer needs a visible activity at all. Enqueue
        //    BEFORE posting the notification: this receiver's onReceive must return
        //    quickly, and enqueue is the part that actually matters.
        WorkManager.getInstance(context).enqueueUniqueWork(
            AdviceWorker.WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<AdviceWorker>()
                // Expedited so it is not parked until Doze's next maintenance
                // window — a 6am outfit delivered at 9am is worthless. On API 31+
                // this uses the expedited job quota, no foreground service, so it
                // does not drag FOREGROUND_SERVICE_DATA_SYNC into targetSdk 34.
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build()
        )

        // 3. Still fire the FSI. When it IS available it gives a foreground GPS read
        //    (better fix, and works even without background location). It is now an
        //    accelerator, not the critical path.
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
            .setAutoCancel(true)
            .setFullScreenIntent(fsi, true)
            .setContentIntent(fsi)
            .build()

        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(WAKE_NOTIF_ID, notif)
    }

    private fun ensureChannel(context: Context) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (nm.getNotificationChannel(CHANNEL_WAKE) == null) {
            val ch = NotificationChannel(
                CHANNEL_WAKE, "Morning wake",
                NotificationManager.IMPORTANCE_HIGH
            ).apply { description = "Briefly wakes the app to read weather for your outfit" }
            nm.createNotificationChannel(ch)
        }
    }

    companion object {
        const val CHANNEL_WAKE = "outfit_wake"
        const val WAKE_NOTIF_ID = 4772
        const val WAKE_REQUEST = 4773
    }
}
