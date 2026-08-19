package com.korety.outfitadvisor

import android.content.Context
import android.os.Build
import android.os.Bundle
import com.getcapacitor.BridgeActivity

/**
 * Capacitor host Activity. The only customization vs the generated default is
 * registering our local plugins so `Plugins.OutfitAlarm.*` (daily morning push),
 * `Plugins.OutfitPacking.*` (trip packing push) and `Plugins.AppUpdate.*` (in-app
 * updates) resolve in app/www/index.html.
 *
 * NOTE (Phase 3 graft): `npx cap add android` generates its own MainActivity.
 * Overwrite it with this file (same package + path), OR add the
 * registerPlugin() lines to the generated one — ALL of them.
 */
class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(OutfitAlarmPlugin::class.java)
        registerPlugin(PackingPlugin::class.java)
        registerPlugin(AppUpdatePlugin::class.java)
        super.onCreate(savedInstanceState)
        clearWebCacheOnUpgrade()
    }

    /**
     * Drop the WebView's HTTP cache the first time we run after an upgrade.
     *
     * Capacitor serves the UI from the APK over https://localhost, and the WebView
     * caches that by URL. The URL never changes between releases, so the WebView
     * can keep serving the PREVIOUS build's index.html after an update — the native
     * package reports the new version, the update check says "up to date", and none
     * of the new UI is there. That is exactly the state reported on 2026-08-19, and
     * it is undiagnosable from the outside because every version signal says the
     * app is current.
     *
     * Keyed on versionCode, so it costs one cache rebuild per upgrade and nothing
     * on ordinary launches.
     */
    private fun clearWebCacheOnUpgrade() {
        val prefs = getSharedPreferences("outfit_app", Context.MODE_PRIVATE)
        val info = packageManager.getPackageInfo(packageName, 0)
        @Suppress("DEPRECATION")
        val code = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode.toInt() else info.versionCode
        if (prefs.getInt(KEY_LAST_VERSION, -1) == code) return
        try {
            bridge?.webView?.clearCache(true)
        } catch (e: Exception) {
            // A cache we could not clear must never stop the app from starting.
        }
        prefs.edit().putInt(KEY_LAST_VERSION, code).apply()
    }

    private companion object {
        const val KEY_LAST_VERSION = "lastVersionCode"
    }
}
