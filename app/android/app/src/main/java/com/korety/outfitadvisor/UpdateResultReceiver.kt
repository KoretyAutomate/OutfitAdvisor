package com.korety.outfitadvisor

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller

/**
 * Where a SelfUpdate session reports back.
 *
 * SUCCESS mostly never arrives here, because the process it would run in is the one
 * being replaced. The "Updated to vX" notice comes from BootReceiver's
 * MY_PACKAGE_REPLACED instead.
 *
 * PENDING_USER_ACTION is Android declining to install silently. That's the old
 * behaviour, so fall back to it. With the app on screen, open the confirm prompt as
 * before. With the app in the background, an activity may not be started, so post a
 * notification whose tap opens the prompt.
 */
class UpdateResultReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION) return
        val sessionId = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1)
        // A superseded session's late result must not touch the current one's state.
        if (!SelfUpdate.isActive(context, sessionId)) return
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        when (status) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION")
                val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT) ?: return
                confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                SelfUpdate.awaitConfirm(context, sessionId)
                if (UpdateWorker.visible) {
                    try { context.startActivity(confirm); return } catch (e: Exception) {}
                }
                val name = SelfUpdate.prefs(context).getString(SelfUpdate.KEY_INSTALLING, null) ?: "?"
                OutfitNotification.postUpdate(
                    context,
                    "Outfit Advisor v$name is ready",
                    "Android wants you to confirm this one. Tap to install — your closet and settings are kept.",
                    PendingIntent.getActivity(
                        context, OutfitNotification.UPDATE_REQUEST, confirm,
                        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                    )
                )
            }
            PackageInstaller.STATUS_SUCCESS -> {}
            else -> {
                // Includes the wearer pressing Cancel on the fallback prompt.
                val msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
                SelfUpdate.recordError(context, "install failed ($status): ${msg ?: "no reason given"}")
            }
        }
    }

    companion object {
        const val ACTION = "com.korety.outfitadvisor.UPDATE_RESULT"
    }
}
