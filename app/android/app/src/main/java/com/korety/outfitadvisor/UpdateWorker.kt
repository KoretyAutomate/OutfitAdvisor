package com.korety.outfitadvisor

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/**
 * Installs a newer published build while the app is NOT on screen (user,
 * 2026-11-21).
 *
 * A self-update stops the running process, so installing while the wearer is in
 * the app would close it under their thumb. This job runs every 6 hours and
 * 2 minutes after the app goes to the background (MainActivity.onStop). It does
 * nothing while the app is visible. The Settings button is the one path that
 * installs in the foreground, because there the wearer asked.
 *
 * Bounded: MAX_TRIES downloads per published version. After that it falls back to
 * the old "tap to install" notification, once, instead of pulling 15 MB every
 * 6 hours for a build that will never install.
 */
class UpdateWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    override fun doWork(): Result {
        val ctx = applicationContext
        // On screen, or a session from a moment ago is still deciding (e.g. its
        // confirm prompt is open): try again next time.
        if (visible || SelfUpdate.inFlight(ctx)) return Result.success()
        val pub = SelfUpdate.published(SelfUpdate.baseUrl(ctx)) ?: return Result.success()
        if (pub.code <= SelfUpdate.runningCode(ctx)) return Result.success()

        val prefs = SelfUpdate.prefs(ctx)
        val triedFor = prefs.getInt(KEY_TRIED_CODE, -1)
        val tries = if (triedFor == pub.code) prefs.getInt(KEY_TRIES, 0) else 0
        if (!SelfUpdate.canInstall(ctx) || tries >= MAX_TRIES) {
            notifyOnce(ctx, pub)
            return Result.success()
        }
        prefs.edit().putInt(KEY_TRIED_CODE, pub.code).putInt(KEY_TRIES, tries + 1).apply()

        return try {
            // The download takes a while; they may have opened the app meanwhile.
            SelfUpdate.fetchAndInstall(ctx, "${SelfUpdate.baseUrl(ctx)}/apk", pub.sha256, pub.size,
                                       pub.name, stillWanted = { !visible })
            Result.success()
        } catch (e: Exception) {
            SelfUpdate.recordError(ctx, "background update failed: ${e.message ?: "unknown"}")
            Result.success()                             // the next run is the retry
        }
    }

    /** The pre-1.60 notice, for when installing silently isn't possible. */
    private fun notifyOnce(ctx: Context, pub: SelfUpdate.Published) {
        val prefs = SelfUpdate.prefs(ctx)
        if (prefs.getString(AdviceWorker.KEY_UPD_NOTIFIED, "")?.toIntOrNull() == pub.code) return
        prefs.edit().putString(AdviceWorker.KEY_UPD_NOTIFIED, pub.code.toString()).apply()
        val why = if (!SelfUpdate.canInstall(ctx))
            "Allow installs from this app once and future updates install by themselves. Tap to open."
        else "It couldn't install by itself. Tap to install — your closet and settings are kept."
        OutfitNotification.postUpdate(ctx, "Outfit Advisor v${pub.name} is ready", why)
    }

    companion object {
        /** Whether MainActivity is on screen. Set from onStart/onStop, not
         *  onResume/onPause: a paused activity can still be visible, e.g. under a
         *  translucent one (pre-push gate, 2026-11-21). A fresh process starts
         *  false, which is right, since nothing is on screen then. */
        @Volatile var visible = false

        const val MAX_TRIES = 3
        private const val KEY_TRIED_CODE = "oa.updTriedCode"
        private const val KEY_TRIES = "oa.updTries"
        private const val PERIODIC = "self-update"
        private const val SOON = "self-update-soon"

        private fun constraints() =
            Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        /** Idempotent: KEEP leaves an existing schedule alone. Called from every
         *  entry point (app open, package replaced, boot, morning push), so an
         *  update to v1.60 that is never opened still gets scheduled. */
        fun schedule(context: Context) {
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                PERIODIC, ExistingPeriodicWorkPolicy.KEEP,
                PeriodicWorkRequestBuilder<UpdateWorker>(6, TimeUnit.HOURS)
                    .setConstraints(constraints()).build()
            )
        }

        /** A check shortly after the app leaves the screen, or after the morning push. */
        fun soon(context: Context, delayMinutes: Long = 2) {
            WorkManager.getInstance(context).enqueueUniqueWork(
                SOON, ExistingWorkPolicy.REPLACE,
                OneTimeWorkRequestBuilder<UpdateWorker>()
                    .setInitialDelay(delayMinutes, TimeUnit.MINUTES)
                    .setConstraints(constraints()).build()
            )
        }
    }
}
