package com.korety.outfitadvisor

import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin

/**
 * In-app updates — "there's a new build, tap to install" — without Play.
 *
 * WHY THIS EXISTS: the user's complaint was updates losing settings and closet
 * photos. That was never sideloading's fault. Android keeps app data across an
 * update as long as the package name AND the signing key are unchanged; the data
 * loss came from CI signing each build with a fresh ephemeral debug key, which
 * makes Android refuse the update and forces an uninstall-first. Fixed 2026-07-11
 * by the persistent keystore + the CI cert-drift gate. This plugin adds the
 * missing half — DELIVERY — so updates arrive like Play's without a Play account.
 *
 * The signature rule is also what makes this safe: even if `oa.baseUrl` pointed at
 * a hostile server, the system installer will not let a differently-signed APK
 * replace this app. It would be a separate install with a visible prompt, not a
 * silent takeover. We additionally verify the sha256 from /version to catch a
 * truncated or corrupted download before handing anything to the installer.
 *
 * Since v1.60 the install itself is SelfUpdate's: silent where Android allows.
 *
 * JS: Plugins.AppUpdate.current() / .install({url, sha256, size, versionName})
 */
@CapacitorPlugin(name = "AppUpdate")
class AppUpdatePlugin : Plugin() {

    /** What this build is, so the web layer can compare against GET /version. */
    @PluginMethod
    fun current(call: PluginCall) {
        val pm = context.packageManager
        val info = pm.getPackageInfo(context.packageName, 0)
        @Suppress("DEPRECATION")
        val code = if (android.os.Build.VERSION.SDK_INT >= 28) info.longVersionCode.toInt()
                   else info.versionCode
        call.resolve(JSObject()
            .put("versionCode", code)
            .put("versionName", info.versionName ?: "")
            .put("canInstall", canInstall())
            .put("lastError", SelfUpdate.prefs(context).getString(SelfUpdate.KEY_LAST_ERROR, "") ?: ""))
    }

    /**
     * Download, verify and install — silently where Android allows (SelfUpdate).
     *
     * This is the path the wearer asked for by tapping Install, so it runs with the
     * app on screen. A successful install stops this process, which closes the app.
     * The JS card says so before it happens. If Android wants confirmation,
     * UpdateResultReceiver opens the old prompt.
     */
    @PluginMethod
    fun install(call: PluginCall) {
        val url = call.getString("url")
        if (url.isNullOrBlank()) { call.reject("url required"); return }
        val expectedSha = call.getString("sha256")?.lowercase()
        val expectedSize = call.getLong("size") ?: 0L
        val versionName = call.getString("versionName") ?: "?"

        if (!canInstall()) {
            // Android 8+: installing from a non-store source is a per-app grant the
            // user makes in Settings. There is no in-app dialog for it by OS design,
            // so route them there and let the JS layer re-check on resume.
            openInstallPermissionSettings()
            call.resolve(JSObject().put("status", "needs-permission"))
            return
        }

        // ~15 MB download: off the main thread so the WebView stays responsive.
        Thread {
            try {
                // False means the background job is already installing it: the
                // same outcome without a second download, so the same answer.
                SelfUpdate.fetchAndInstall(context, url, expectedSha, expectedSize, versionName)
                call.resolve(JSObject().put("status", "installing"))
            } catch (e: Exception) {
                SelfUpdate.recordError(context, e.message ?: "download failed")
                call.reject(e.message ?: "download failed")
            }
        }.start()
    }

    /** Send the user to the "Install unknown apps" screen for THIS app. */
    @PluginMethod
    fun requestInstallPermission(call: PluginCall) {
        if (canInstall()) { call.resolve(JSObject().put("granted", true)); return }
        openInstallPermissionSettings()
        call.resolve(JSObject().put("granted", false))
    }

    private fun canInstall(): Boolean =
        if (android.os.Build.VERSION.SDK_INT >= 26)
            context.packageManager.canRequestPackageInstalls()
        else true

    private fun openInstallPermissionSettings() {
        if (android.os.Build.VERSION.SDK_INT < 26) return
        try {
            context.startActivity(
                Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                       Uri.parse("package:${context.packageName}"))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            // Some OEM builds lack the per-app screen; the global list is the fallback.
            try {
                context.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            } catch (ignored: Exception) {}
        }
    }

}
