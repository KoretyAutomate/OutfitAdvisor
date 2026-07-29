package com.korety.outfitadvisor

import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

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
 * JS: Plugins.AppUpdate.current() / .install({url, sha256, size})
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
            .put("canInstall", canInstall()))
    }

    /**
     * Download the APK, verify it, and hand it to the system installer.
     *
     * Runs the download on a background thread: it is ~14 MB and the main thread
     * must keep the WebView responsive. The Activity is visible throughout (the
     * user just tapped a button), so unlike the packing push there is no risk of
     * the process being killed mid-flight — that case needed WorkManager, this
     * one genuinely does not.
     */
    @PluginMethod
    fun install(call: PluginCall) {
        val url = call.getString("url")
        if (url.isNullOrBlank()) { call.reject("url required"); return }
        val expectedSha = call.getString("sha256")?.lowercase()
        val expectedSize = call.getLong("size") ?: 0L

        if (!canInstall()) {
            // Android 8+: installing from a non-store source is a per-app grant the
            // user makes in Settings. There is no in-app dialog for it by OS design,
            // so route them there and let the JS layer re-check on resume.
            openInstallPermissionSettings()
            call.resolve(JSObject().put("status", "needs-permission"))
            return
        }

        Thread {
            var conn: HttpURLConnection? = null
            try {
                val out = File(context.cacheDir, "update.apk")
                out.delete()

                conn = (URL(url).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 10_000
                    readTimeout = 60_000
                }
                if (conn.responseCode != 200) throw IllegalStateException("server ${conn.responseCode}")

                val digest = MessageDigest.getInstance("SHA-256")
                var total = 0L
                conn.inputStream.use { input ->
                    out.outputStream().use { sink ->
                        val buf = ByteArray(64 * 1024)
                        while (true) {
                            val n = input.read(buf)
                            if (n <= 0) break
                            digest.update(buf, 0, n)
                            sink.write(buf, 0, n)
                            total += n
                            // A runaway or hostile response must not fill the disk.
                            if (total > MAX_APK_BYTES) throw IllegalStateException("apk too large")
                        }
                    }
                }

                if (expectedSize > 0 && total != expectedSize)
                    throw IllegalStateException("size mismatch: got $total, expected $expectedSize")

                val actualSha = digest.digest().joinToString("") { "%02x".format(it) }
                if (!expectedSha.isNullOrBlank() && actualSha != expectedSha)
                    throw IllegalStateException("checksum mismatch — download corrupted")

                val uri = FileProvider.getUriForFile(
                    context, "${context.packageName}.fileprovider", out)
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(intent)
                call.resolve(JSObject().put("status", "installer-opened").put("bytes", total))
            } catch (e: Exception) {
                File(context.cacheDir, "update.apk").delete()
                call.reject(e.message ?: "download failed")
            } finally {
                conn?.disconnect()
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

    private companion object {
        // The real APK is ~15 MB; 100 MB is a generous ceiling that still bounds
        // a malicious or broken response.
        const val MAX_APK_BYTES = 100L * 1024 * 1024
    }
}
