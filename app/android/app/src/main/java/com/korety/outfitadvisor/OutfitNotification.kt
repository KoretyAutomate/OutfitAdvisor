package com.korety.outfitadvisor

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon

/**
 * The one place the morning outfit notification is built.
 *
 * It used to live inside WakeActivity, which was fine while the activity also did
 * the POST. Now the POST happens in AdviceWorker (the activity finishes in ~2s),
 * so BOTH need to post notifications — the worker for the real advice, the
 * activity for the "couldn't even get a location" case. Two copies of a
 * notification builder is exactly how the feedback action buttons end up on one
 * path and not the other, so there is only one copy.
 */
object OutfitNotification {

    const val CHANNEL_OUTFIT = "outfit_daily"
    const val OUTFIT_NOTIF_ID = 4775

    fun ensureChannel(context: Context) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (nm.getNotificationChannel(CHANNEL_OUTFIT) == null) {
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_OUTFIT, "Daily outfit", NotificationManager.IMPORTANCE_DEFAULT
                ).apply { description = "Your morning outfit recommendation" }
            )
        }
    }

    /**
     * @param withFeedback only when [text] is real advice. Asking "how did that
     *   feel?" under "Tap to check what to wear" would collect a rating for an
     *   outfit we never actually recommended, quietly poisoning the calibration.
     */
    fun post(context: Context, title: String, text: String, badge: String?, withFeedback: Boolean) {
        ensureChannel(context)
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
            ?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            ?: Intent(context, MainActivity::class.java)
        val pi = PendingIntent.getActivity(
            context, 4774, launch,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // A collapsed notification shows ONE line of contentText. An earlier build
        // put a "tap for details" teaser there and hid the outfit in BigTextStyle,
        // so the advice only appeared if the user expanded it — which most never do.
        // Show the advice itself: compact one-liner collapsed, full text expanded.
        val oneLine = text
            .replace(Regex("^\\s*[-•]\\s*", RegexOption.MULTILINE), "")
            .replace('\n', ' ')
            .trim()

        val b = Notification.Builder(context, CHANNEL_OUTFIT)
            .setSmallIcon(context.applicationInfo.icon)
            .setContentTitle(title)
            .setContentText(oneLine)
            .setStyle(Notification.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setContentIntent(pi)
        if (badge != null) b.setSubText(badge)
        if (withFeedback) {
            // Android renders at most 3 actions; the "a bit cool/warm" steps are in-app.
            b.addAction(feedbackAction(context, "🥶 Too cold", -2, FeedbackReceiver.REQ_COLD))
            b.addAction(feedbackAction(context, "👌 Just right", 0, FeedbackReceiver.REQ_OK))
            b.addAction(feedbackAction(context, "🥵 Too warm", 2, FeedbackReceiver.REQ_WARM))
        }

        nm.notify(OUTFIT_NOTIF_ID, b.build())
        nm.cancel(AlarmReceiver.WAKE_NOTIF_ID)   // clear the transient wake notification
    }

    /**
     * Distinct request codes per rating — a shared code with FLAG_UPDATE_CURRENT
     * makes every button deliver whichever extras were written last.
     */
    private fun feedbackAction(context: Context, label: String, rating: Int, requestCode: Int): Notification.Action {
        val i = Intent(context, FeedbackReceiver::class.java)
            .setAction(FeedbackReceiver.ACTION_FEEDBACK)
            .putExtra(FeedbackReceiver.EXTRA_RATING, rating)
        val pi = PendingIntent.getBroadcast(
            context, requestCode, i,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return Notification.Action.Builder(
            Icon.createWithResource(context, context.applicationInfo.icon), label, pi
        ).build()
    }
}
