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
import java.util.concurrent.locks.ReentrantLock

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
    // A session Android declined to install silently, waiting on the wearer's tap.
    private const val KEY_PENDING_SESSION = "oa.updPendingSession"
    // The one session whose result may change any of this state. A result from any
    // other session, e.g. the failure Android reports for one a tap superseded, is
    // ignored (pre-push gate, 2026-11-21).
    private const val KEY_ACTIVE_SESSION = "oa.updActiveSession"
    private const val KEY_PENDING_AT = "oa.updPendingAt"
    // A confirmation nobody acted on for this long, e.g. its notification was
    // swiped away, stops holding up the background job, which then starts over
    // (pre-push gate, 2026-11-21).
    private const val PENDING_MAX_MS = 24 * 60 * 60 * 1000L
    // How long a committed session counts as in flight: long enough to cover the
    // wearer reading the fallback confirm prompt, short enough that a session
    // that died without reporting never blocks updates for long.
    private const val IN_FLIGHT_MS = 15 * 60 * 1000L

    // One update at a time across the periodic job, the one-off job and the Install
    // button, which all run in this process and would otherwise share update.apk:
    // one could delete or overwrite the file another was about to install (pre-push
    // gate, 2026-11-21). tryLock, so a second caller skips instead of queuing a
    // second 15 MB download.
    private val busy = ReentrantLock()

    /** The wearer tapped Install and is waiting on the lock. A background run that
     *  holds it must then install, not back out because the app is on screen:
     *  backing out would leave the tap reported as installing with nothing
     *  installed (pre-push gate, 2026-11-21). */
    @Volatile var tapWaiting = false
        private set

    /**
     * Download, verify and commit, as one operation nobody else can interleave with.
     *
     * Background (`tap` false): skips and returns false if another run holds the
     * lock or a session is already deciding. `reserve` then claims an attempt and
     * may refuse. `stillWanted` is asked after the download and again just before
     * commit, so it can back out if the app came on screen.
     *
     * Tap (`tap` true): waits for the lock instead. If the run it waited for
     * committed a session, that's this tap's install too, so it returns without a
     * second download.
     *
     * Throws on failure. Blocking: call it off the main thread.
     */
    fun fetchAndInstall(context: Context, url: String, sha: String?, size: Long,
                        versionName: String, tap: Boolean = false,
                        stillWanted: () -> Boolean = { true },
                        reserve: () -> Boolean = { true }): Boolean {
        if (tap) {
            tapWaiting = true
            busy.lock()
            tapWaiting = false
            if (inFlight(context)) { busy.unlock(); return true }
        } else {
            if (!busy.tryLock()) return false
            // Rechecked under the lock: another background run may have committed, or
            // been told to wait for a confirmation, since this one's early checks.
            if (inFlight(context) || awaitingConfirm(context)) { busy.unlock(); return false }
            // The retry budget is spent here, under the lock and past every skip, so a
            // run that downloads nothing never uses up an attempt.
            if (!reserve()) { busy.unlock(); return false }
        }
        try {
            val apk = download(context, url, sha, size)
            try {
                install(context, apk, versionName, stillWanted)
            } finally {
                // The session holds its own copy once written, so the file is done
                // with either way. Deleted HERE, under the lock, so no other caller's
                // cleanup can ever reach a download in progress.
                apk.delete()
            }
            return true
        } finally {
            busy.unlock()
        }
    }

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

    /** Download the APK and verify it. Throws on anything wrong, after deleting the
     *  partial file. Only fetchAndInstall calls it, under the lock. */
    private fun download(context: Context, url: String, expectedSha: String?, expectedSize: Long): File {
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
    private fun install(context: Context, apk: File, versionName: String, stillWanted: () -> Boolean) {
        val installer = context.packageManager.packageInstaller
        // A tap supersedes a session still waiting on a confirmation. Its prompt may
        // only be reachable from a notification, and a fresh session started with the
        // app on screen opens its own (pre-push gate, 2026-11-21).
        abandonPending(context)
        if (!stillWanted()) return
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
                // Asked again HERE, after the copy and fsync: the wearer may have
                // opened the app while the APK was being staged, and committing now
                // would close it under them (pre-push gate, 2026-11-21).
                if (!stillWanted()) { session.abandon(); return }
                // Before commit: success kills this process, and the "Updated" notice
                // after the restart is how the wearer learns it happened.
                prefs(context).edit()
                    .putInt(KEY_ACTIVE_SESSION, id)
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
            throw e
        }
    }

    /** Whether a status broadcast is about the session this state belongs to. */
    fun isActive(context: Context, sessionId: Int): Boolean =
        sessionId >= 0 && prefs(context).getInt(KEY_ACTIVE_SESSION, -1) == sessionId

    /** Android wants a tap for this session (UpdateResultReceiver). It stops counting
     *  as in flight, so an Install tap isn't told one is already happening. */
    fun awaitConfirm(context: Context, sessionId: Int) {
        prefs(context).edit()
            .putInt(KEY_PENDING_SESSION, sessionId)
            .putLong(KEY_PENDING_AT, System.currentTimeMillis())
            .putLong(KEY_INSTALLING_AT, 0L)
            .apply()
    }

    /** A session is still waiting on the wearer's confirmation. The background job
     *  leaves it alone, so it neither re-downloads nor re-notifies every run. */
    fun awaitingConfirm(context: Context): Boolean {
        val p = prefs(context)
        val id = p.getInt(KEY_PENDING_SESSION, -1)
        if (id < 0) return false
        val fresh = System.currentTimeMillis() - p.getLong(KEY_PENDING_AT, 0L) < PENDING_MAX_MS
        if (fresh && context.packageManager.packageInstaller.getSessionInfo(id) != null) return true
        abandonPending(context)   // stale or gone: clear it so the next run starts over
        return false
    }

    /** Drop a session waiting on a confirmation. Also called at boot, when its
     *  notification is gone and nothing could reach its prompt any more. */
    fun abandonPending(context: Context) {
        val p = prefs(context)
        val id = p.getInt(KEY_PENDING_SESSION, -1)
        if (id < 0) return
        try { context.packageManager.packageInstaller.abandonSession(id) } catch (e: Exception) {}
        p.edit().remove(KEY_PENDING_SESSION).apply()
    }

    /** A session was committed moments ago and hasn't reported back yet. */
    fun inFlight(context: Context): Boolean {
        val p = prefs(context)
        if (p.getString(KEY_INSTALLING, null) == null) return false
        return System.currentTimeMillis() - p.getLong(KEY_INSTALLING_AT, 0L) < IN_FLIGHT_MS
    }

    fun recordError(context: Context, message: String) {
        prefs(context).edit()
            .putString(KEY_LAST_ERROR, message.take(200))
            .remove(KEY_INSTALLING)
            .apply()
    }
}
