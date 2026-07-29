package com.korety.outfitadvisor

import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import java.util.concurrent.TimeUnit

/**
 * OutfitPacking — JS bridge for the trip packing push.
 *
 * Scheduling is WorkManager unique work keyed by the TRIP ID (a String), not an
 * AlarmManager PendingIntent keyed by an int request code. That is deliberate: a
 * hashed-int request code per trip can silently collide, and a collision would
 * overwrite another trip's reminder with no way to detect it — the same class of
 * bug the daily push's dedicated constant block exists to prevent, just moved down
 * a level. Unique work names cannot collide, cancel by name, and survive reboot.
 *
 * No exact-alarm permission is used or needed: "about two days before you leave"
 * has no second-accuracy requirement, and keeping this feature off
 * SCHEDULE_EXACT_ALARM avoids stacking a second justification onto a permission
 * granted for a genuine alarm-clock use case.
 */
@CapacitorPlugin(name = "OutfitPacking")
class PackingPlugin : Plugin() {

    @PluginMethod
    fun arm(call: PluginCall) {
        val tripId = call.getString("tripId")
        val fireAt = call.getLong("fireAtMillis")
        if (tripId.isNullOrBlank() || fireAt == null) {
            call.reject("tripId and fireAtMillis are required"); return
        }
        val delay = fireAt - System.currentTimeMillis()
        if (delay <= 0) { call.reject("fireAtMillis is in the past"); return }

        val req = OneTimeWorkRequestBuilder<PackingWorker>()
            .setInitialDelay(delay, TimeUnit.MILLISECONDS)
            .setInputData(Data.Builder().putString(PackingWorker.KEY_TRIP_ID, tripId).build())
            .addTag(TAG)
            .build()

        WorkManager.getInstance(context).enqueueUniqueWork(
            PackingWorker.workName(tripId), ExistingWorkPolicy.REPLACE, req)

        call.resolve(JSObject().put("armed", true).put("fireAtMillis", fireAt))
    }

    @PluginMethod
    fun cancel(call: PluginCall) {
        val tripId = call.getString("tripId")
        if (tripId.isNullOrBlank()) { call.reject("tripId is required"); return }
        WorkManager.getInstance(context).cancelUniqueWork(PackingWorker.workName(tripId))
        call.resolve(JSObject().put("cancelled", true))
    }

    /** Ground truth from WorkManager, so the UI can show what is ACTUALLY pending
     *  rather than what the web layer last believed it saved. */
    @PluginMethod
    fun status(call: PluginCall) {
        val tripId = call.getString("tripId")
        if (tripId.isNullOrBlank()) { call.reject("tripId is required"); return }
        val infos = WorkManager.getInstance(context)
            .getWorkInfosForUniqueWork(PackingWorker.workName(tripId)).get()
        val pending = infos.any { !it.state.isFinished }
        call.resolve(JSObject().put("armed", pending))
    }

    companion object { const val TAG = "outfit-packing" }
}
