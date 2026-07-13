package com.korety.outfitadvisor

import android.os.Bundle
import com.getcapacitor.BridgeActivity

/**
 * Capacitor host Activity. The only customization vs the generated default is
 * registering our local plugins so `Plugins.OutfitAlarm.*` (daily morning push) and
 * `Plugins.OutfitPacking.*` (trip packing push) resolve in app/www/index.html.
 *
 * NOTE (Phase 3 graft): `npx cap add android` generates its own MainActivity.
 * Overwrite it with this file (same package + path), OR add the
 * registerPlugin() lines to the generated one — BOTH of them.
 */
class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(OutfitAlarmPlugin::class.java)
        registerPlugin(PackingPlugin::class.java)
        super.onCreate(savedInstanceState)
    }
}
