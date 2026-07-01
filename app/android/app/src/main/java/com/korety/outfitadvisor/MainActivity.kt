package com.korety.outfitadvisor

import android.os.Bundle
import com.getcapacitor.BridgeActivity

/**
 * Capacitor host Activity. The only customization vs the generated default is
 * registering our local OutfitAlarm plugin so `Plugins.OutfitAlarm.arm/cancel`
 * resolves in app/www/index.html.
 *
 * NOTE (Phase 3 graft): `npx cap add android` generates its own MainActivity.
 * Overwrite it with this file (same package + path), OR add the single
 * registerPlugin() line to the generated one.
 */
class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(OutfitAlarmPlugin::class.java)
        super.onCreate(savedInstanceState)
    }
}
