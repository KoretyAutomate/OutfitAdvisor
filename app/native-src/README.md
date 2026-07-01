# Phase 2 native layer — staging area

These files are the **native scheduling glue** (PLAN Phase 2). They live here as a
staging area because `app/android/` does not exist yet: generating it needs the
Android SDK + JDK 17, which the DGX does not have installed (Java 8 only). So this
code is **written but not yet compiled or run** — device verification is Phase 3.

## What's here

| File | Role |
|---|---|
| `java/.../AlarmScheduler.kt` | Arms/cancels the once-daily exact alarm (local wall-clock, timezone-following). |
| `java/.../OutfitAlarmPlugin.kt` | Capacitor plugin — bridges JS `Plugins.OutfitAlarm.arm/cancel` to AlarmScheduler. |
| `java/.../AlarmReceiver.kt` | Fires daily: re-arms tomorrow, then launches WakeActivity via an FSI notification. |
| `java/.../BootReceiver.kt` | Re-arms the alarm after a reboot (exact alarms don't survive reboot). |
| `java/.../WakeActivity.kt` | The full-screen-intent visible wake: one fresh GPS fix → POST /advice → notify → discard coords. |
| `java/.../MainActivity.kt` | Capacitor host that `registerPlugin(OutfitAlarmPlugin)`. |
| `res/xml/network_security_config.xml` | Cleartext scoped to the DGX tailnet IP only. |
| `res/values/themes_outfit.xml` | `Theme.OutfitWake` for the transient wake screen. |
| `AndroidManifest.additions.xml` | Permission set + component registrations to graft into the generated manifest. |

## Contract this code implements (must stay in sync with `app/www/index.html`)

- JS calls `Plugins.OutfitAlarm.arm({hour, minute})` / `.cancel()`.
- WakeActivity reads the **Capacitor Preferences** store (`SharedPreferences`
  file **`CapacitorStorage`**) for keys `oa.baseUrl`, `oa.gender`, `oa.style`
  — the same keys the web layer writes. If a Preferences `group` is ever set in
  `capacitor.config.json`, update the SharedPreferences name in `WakeActivity.kt`.
- POST body: `{lat, lon, gender, style, day: 0}` → `{baseUrl}/advice`.
- Response used: `outfit_text`, `source`, `weather.{lo,hi,emoji}`.

## Phase 3 graft steps (once the SDK/JDK 17 toolchain is installed)

1. Install JDK 17 + Android cmdline-tools + `platforms;android-34` `build-tools;34.0.0`
   (PLAN "APK build path"), `export ANDROID_HOME JAVA_HOME`.
2. `cd app && npx cap add android` (generates `app/android/`).
3. Copy `java/com/korety/outfitadvisor/*.kt` →
   `app/android/app/src/main/java/com/korety/outfitadvisor/` (overwrite the
   generated `MainActivity`).
4. Copy `res/xml/network_security_config.xml` and merge `res/values/themes_outfit.xml`
   into `app/android/app/src/main/res/…`.
5. Graft `AndroidManifest.additions.xml` into the generated
   `app/android/app/src/main/AndroidManifest.xml` (permissions + components + the
   `android:networkSecurityConfig` attribute on `<application>`).
6. Ensure `minSdkVersion >= 29` and `compileSdk/targetSdk = 34` in
   `app/android/variables.gradle` / module gradle (LocationManager.getCurrentLocation
   needs API 30; the code degrades on 29 via requestSingleUpdate).
7. `cd android && ./gradlew assembleDebug` → verify exit 0 **and** `stat` the
   `app-debug.apk`.

## De-risk verification (Phase 2.6 / 2.7, on the Pixel — NOT provable on paper)

- Set a 2-minute test alarm, lock the phone (screen off) → confirm WakeActivity
  fires through Doze, reads a **fresh** fix (not stale), the POST lands, and the
  outfit notification shows.
- Kill the DGX → confirm the soft fallback notification appears (opens the app,
  which runs its own on-device estimate) instead of a crash or a hang.
- Reboot the phone → confirm BootReceiver re-arms and the next fire still works.

## Known MVP scope choices

- **Fallback is a soft notification**, not a full native rule-engine. When the DGX
  is unreachable at fire time, WakeActivity posts "Tap to check what to wear" that
  opens the web app, which already has the JS `recommend()` rule engine + local
  Open-Meteo fetch. Porting the engine to Kotlin for a fully-silent offline push is
  banked for later (PLAN risk #4 acceptable trade-off for MVP).
- Location is held only as local variables in `WakeActivity.onLocation` and never
  written to prefs, files, or logs (privacy requirement).
