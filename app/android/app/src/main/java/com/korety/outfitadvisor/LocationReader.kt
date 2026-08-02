package com.korety.outfitadvisor

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.LocationManager
import android.os.CancellationSignal
import androidx.core.content.ContextCompat
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * Blocking one-shot location read, for AdviceWorker's recovery path only.
 *
 * The normal flow reads GPS in the VISIBLE WakeActivity, which is what makes the
 * read count as foreground location under plain ACCESS_FINE_LOCATION. This exists
 * for the case where the process died between the activity handing off and the
 * worker running, so LocationHandoff came back empty. That read happens with no UI
 * on screen, which only works because the app also holds ACCESS_BACKGROUND_LOCATION
 * (added 2026-07-15 at the user's request). If the user kept "only while using the
 * app", this returns null and the caller posts the soft fallback — correct, rather
 * than pretending to have a location.
 *
 * Blocking is safe here: Worker.doWork() already runs off the main thread.
 */
object LocationReader {

    fun readBlocking(context: Context, timeoutMs: Long = 20_000): Pair<Double, Double>? {
        if (!hasPermission(context)) return null
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val provider = when {
            lm.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
            lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
            else -> return null
        }

        val latch = CountDownLatch(1)
        // AtomicReference, not @Volatile — @Volatile is a property annotation and
        // does not compile on a local. The callback runs on `exec`, so the value
        // still has to cross a thread boundary safely.
        val result = AtomicReference<Pair<Double, Double>?>(null)
        val exec = Executors.newSingleThreadExecutor()
        val cancel = CancellationSignal()
        return try {
            lm.getCurrentLocation(provider, cancel, exec) { loc ->
                if (loc != null) result.set(loc.latitude to loc.longitude)
                latch.countDown()
            }
            if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) cancel.cancel()
            result.get() ?: lm.getLastKnownLocation(provider)?.let { it.latitude to it.longitude }
        } catch (se: SecurityException) {
            null
        } finally {
            exec.shutdownNow()
        }
    }

    fun hasPermission(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
}
