package com.korety.outfitadvisor

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Updates that install themselves (user, 2026-11-21: "avoid requiring me to hit
 * install and still update").
 *
 * Until v1.59 every update went through ACTION_VIEW on the APK, which always opens
 * the system installer and waits for a tap. Android 12+ lets an app UPDATE ITSELF
 * through a PackageInstaller session that asks for no user action
 * (USER_ACTION_NOT_REQUIRED). The conditions: the session updates the caller's own
 * package, the app holds UPDATE_PACKAGES_WITHOUT_USER_ACTION (a normal permission,
 * in the manifest), the "install unknown apps" grant is on, and the APK targets a
 * recent SDK. Android treats it as a request, not a promise, so a session that
 * still needs confirmation comes back as STATUS_PENDING_USER_ACTION and
 * UpdateResultReceiver falls back to the old prompt. Nothing can get worse than the
 * old behaviour.
 *
 * What makes it safe is unchanged: Android refuses any APK not signed with this
 * app's key, and the sha256 and size from /version are checked before a single
 * byte reaches the installer.
 *
 * One owner for download, verify and install, so the Settings button
 * (AppUpdatePlugin) and the background job (UpdateWorker) can never disagree.
 */
object SelfUpdate {

    /** What GET /version says is published. */
    data class Published(val code: Int, val name: String, val sha256: String, val size: Long)

    // The real APK is ~15 MB; 100 MB still bounds a malicious or broken response.
    private const val MAX_APK_BYTES = 100L * 1024 * 1024
    private const val APK_NAME = "update.apk"

    // Shared with the web layer, which reads them out of the same store.
    const val KEY_INSTALLING = "oa.updInstalling"   // the versionName a session was committed for
    const val KEY_LAST_ERROR = "oa.updLastError"    // what went wrong, shown in Settings
    private const val KEY_INSTALLING_AT = "oa.updInstallingAt"
    // How long a committed session counts as in flight: long enough to cover the
    // wearer reading the fallback confirm prompt, short enough that a session
    // that died without reporting never blocks updates for long.
    private const val IN_FLIGHT_MS = 15 * 60 * 1000L

    fun prefs(context: Context) =
        context.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE)

    fun baseUrl(context: Context): String =
        (prefs(context).getString("oa.baseUrl", AdviceWorker.DEFAULT_BASE)
            ?: AdviceWorker.DEFAULT_BASE).trimEnd('/')

    fun runningCode(context: Context): Int {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        return info.longVersionCode.toInt()   // minSdk 31, so always available
    }

    fun canInstall(context: Context): Boolean =
        context.packageManager.canRequestPackageInstalls()

    /** GET /version, or null when nothing is published or the server is unreachable. */
    fun published(base: String): Published? {
        var conn: HttpURLConnection? = null
        return try {
            conn = (URL("$base/version").openConnection() as HttpURLConnection).apply {
                connectTimeout = 8_000
                readTimeout = 8_000
            }
            if (conn.responseCode != 200) return null
            val v = JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
            val code = v.optInt("versionCode", 0)
            if (code <= 0) null
            else Published(code, v.optString("versionName", "?"),
                           v.optString("sha256", "").lowercase(), v.optLong("size", 0L))
        } catch (e: Exception) {
            null
        } finally {
            conn?.disconnect()
        }
    }

    /**
     * Download the APK and verify it. Throws on anything wrong, after deleting the
     * partial file. Blocking: call it off the main thread.
     */
    fun download(context: Context, url: String, expectedSha: String?, expectedSize: Long): File {
        val out = File(context.cacheDir, APK_NAME)
        out.delete()
        var conn: HttpURLConnection? = null
        try {
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
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            if (!expectedSha.isNullOrBlank() && actual != expectedSha.lowercase())
                throw IllegalStateException("checksum mismatch — download corrupted")
            return out
        } catch (e: Exception) {
            out.delete()
            throw e
        } finally {
            conn?.disconnect()
        }
    }

    /**
     * Hand a verified APK to PackageInstaller, asking for no confirmation.
     *
     * Returns once the session is committed. The outcome arrives later at
     * UpdateResultReceiver. On success Android stops this process to replace it, so
     * a caller must not count on anything running after this.
     */
    fun install(context: Context, apk: File, versionName: String) {
        val installer = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(context.packageName)
            setSize(apk.length())
            setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
        }
        val id = installer.createSession(params)
        try {
            installer.openSession(id).use { session ->
                apk.inputStream().use { input ->
                    session.openWrite("base.apk", 0, apk.length()).use { sink ->
                        input.copyTo(sink, 64 * 1024)
                        session.fsync(sink)
                    }
                }
                // Before commit: success kills this process, and the "Updated" notice
                // after the restart is how the wearer learns it happened.
                prefs(context).edit()
                    .putString(KEY_INSTALLING, versionName)
                    .putLong(KEY_INSTALLING_AT, System.currentTimeMillis())
                    .remove(KEY_LAST_ERROR)
                    .commit()
                // MUTABLE: the installer writes the status extras into this intent.
                // Explicit component, so no other app can receive it.
                val result = PendingIntent.getBroadcast(
                    context, id,
                    Intent(context, UpdateResultReceiver::class.java)
                        .setAction(UpdateResultReceiver.ACTION),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
                )
                session.commit(result.intentSender)
            }
        } catch (e: Exception) {
            try { installer.abandonSession(id) } catch (ignored: Exception) {}
            prefs(context).edit().remove(KEY_INSTALLING).apply()
            apk.delete()
            throw e
        }
    }

    /** A session was committed moments ago and hasn't reported back yet. */
    fun inFlight(context: Context): Boolean {
        val p = prefs(context)
        if (p.getString(KEY_INSTALLING, null) == null) return false
        return System.currentTimeMillis() - p.getLong(KEY_INSTALLING_AT, 0L) < IN_FLIGHT_MS
    }

    fun clearDownload(context: Context) {
        File(context.cacheDir, APK_NAME).delete()
    }

    fun recordError(context: Context, message: String) {
        prefs(context).edit()
            .putString(KEY_LAST_ERROR, message.take(200))
            .remove(KEY_INSTALLING)
            .apply()
    }
}
