package com.korety.outfitadvisor

import android.app.Activity
import android.content.Context
import android.location.Location
import android.location.LocationManager
import android.os.Bundle
import android.os.CancellationSignal
import android.os.Handler
import android.os.Looper
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkManager

/**
 * The full-screen-intent wake Activity — the spine of the whole app (PLAN risk #1).
 *
 * Launched by AlarmReceiver's FSI notification at the armed morning time. It becomes
 * briefly VISIBLE over the lockscreen, which makes the ensuing one-shot GPS read
 * count as legitimate foreground location under plain ACCESS_FINE_LOCATION.
 * Since 2026-07-15 the app ALSO declares ACCESS_BACKGROUND_LOCATION (user request):
 * when "Allow all the time" is granted, the GPS read no longer depends on this
 * activity's visibility timing at all.
 *
 * SCOPE (changed 2026-08-02): this activity now does ONLY the fast part — read one
 * fresh fix, hand it to AdviceWorker, finish. It used to do the POST too, under an
 * 11-second watchdog with a 9-second read timeout, while real /advice calls take
 * 20-30s against a 122B model. The watchdog therefore always won and the user got
 * "Tap to check what to wear" EVERY morning — the server log shows this path never
 * once reached it in 30 days. The slow half now lives in AdviceWorker, which has no
 * visible UI waiting on it and can take as long as the model needs.
 *
 * PRIVACY: the fix is handed over in process memory (LocationHandoff), never as
 * WorkManager input Data — that gets persisted to disk, which would break the
 * RAM-only coordinates invariant.
 *
 * Requires minSdk 30 (getCurrentLocation).
 */
class WakeActivity : Activity() {

    private val main = Handler(Looper.getMainLooper())
    private var gpsCancel: CancellationSignal? = null
    private var done = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        OutfitNotification.ensureChannel(this)

        // Watchdog covers the GPS read ONLY now, so it can be short again — the
        // point of this screen is a 1-2s flash, not a spinner on the lock screen.
        main.postDelayed({ handOff(null) }, GPS_WATCHDOG_MS)

        if (!LocationReader.hasPermission(this)) {
            // No runtime grant: let the worker try (it may hold background location)
            // and post the soft fallback if not.
            handOff(null)
            return
        }
        readFreshLocation()
    }

    private fun readFreshLocation() {
        val lm = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val provider = when {
            lm.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
            lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
            else -> null
        } ?: return handOff(null)

        try {
            gpsCancel = CancellationSignal()
            lm.getCurrentLocation(provider, gpsCancel, mainExecutor) { loc ->
                if (done) return@getCurrentLocation
                // a recent last-known beats no outfit
                val fix = loc ?: try { lm.getLastKnownLocation(provider) } catch (se: SecurityException) { null }
                handOff(fix)
            }
        } catch (se: SecurityException) {
            handOff(null)
        }
    }

    /**
     * Hand the fix (or the absence of one) to AdviceWorker and get off the screen.
     * First caller wins — the watchdog and the GPS callback race, exactly as before.
     */
    private fun handOff(fix: Location?) {
        if (done) return
        done = true

        if (fix != null) LocationHandoff.put(fix.latitude, fix.longitude)

        // KEEP, not REPLACE. AlarmReceiver now enqueues the worker itself (that is
        // what makes the push work on a locked phone), so by the time this activity
        // runs a worker is usually already going — and REPLACE would CANCEL that
        // in-flight worker, throwing away the request it had already started.
        // Handing over the fix above is this activity's real contribution now; the
        // enqueue is only a safety net for the case where the receiver's did not
        // land.
        WorkManager.getInstance(this).enqueueUniqueWork(
            AdviceWorker.WORK_NAME,
            ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<AdviceWorker>()
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build()
        )

        gpsCancel?.cancel()
        finish()
    }

    private companion object {
        // Only has to cover a GPS fix now, not a 30-second LLM round trip.
        const val GPS_WATCHDOG_MS = 8_000L
    }
}
