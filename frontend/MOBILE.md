# SolarSage mobile — iOS + Android

The mobile build is a Capacitor wrapper around the existing React app, with
all the FastAPI logic ported into in-app JavaScript so the apps run
**self-contained**: no backend server, talks directly to
`monitor.eg4electronics.com`, stores its own SQLite history on-device.

## What's in the box

- `capacitor.config.ts` — app id `com.hitorro.solarsage`, name `SolarSage`
- `ios/` — Xcode project (`App/App.xcodeproj`)
- `android/` — Android Studio / Gradle project
- `src/local/` — JavaScript port of the Python backend
  - `eg4Client.js` — EG4 portal client (login + snapshots + day-line history)
  - `history.js` — local SQLite store, same `samples` schema as the FastAPI build
  - `forecast.js` — battery completion, historical ETA, battery cycles, etc.
  - `solar.js` — clear-sky envelope
  - `weather.js` — Open-Meteo
  - `poller.js` — foreground polling loop (60 s while the app is visible)
  - `server.js` — dispatches `/api/*` paths from `api.js` to local handlers

`api.js` detects the Capacitor runtime and routes to the local handlers
instead of `fetch('/api/...')`. The React components don't know which build
they're running in.

## Build flow

Every time you change the React code:

```bash
cd frontend
npm run build         # produces dist/
npx cap sync          # copies dist/ into ios/ and android/
```

Then open the platform you want and hit Run.

## iOS

### One-time setup

1. Install Xcode 16+ from the App Store, accept its license, and run
   `sudo xcode-select --install` once if `xcodebuild -version` complains.
2. Install **CocoaPods**: `sudo gem install cocoapods` (or via Homebrew).
3. From `frontend/`:
   ```bash
   cd ios/App && pod install && cd ../..
   ```
   (Capacitor 8 uses Swift Package Manager by default; pod install only
   matters if a plugin still ships a podspec — harmless to run.)

### Open + run

```bash
cd frontend && npx cap open ios
```

In Xcode:

1. Click the **App** target → **Signing & Capabilities** → set your **Team**
   (your personal Apple ID is fine for sideloading; an Apple Developer Program
   team is required to submit to the App Store).
2. Plug in an iPhone / iPad, pick it in the device dropdown, hit ▶ Run.
3. On the device: Settings → General → VPN & Device Management → trust the
   developer cert.

### App Store submission

1. Apple Developer Program account ($99/yr) and registration of the bundle id
   `com.hitorro.solarsage` in App Store Connect.
2. In Xcode: **Product → Archive**. When the archive finishes, **Distribute
   App → App Store Connect → Upload**.
3. In App Store Connect: fill in the listing (screenshots required for iPhone
   6.7", 6.5", and iPad 13"; the existing app screenshots can be reused).
4. Submit for review.

**Guideline 4.2 risk:** Apple sometimes rejects apps that are essentially
website wrappers. To clear this, add at least one genuinely native feature
before submission — biometric login (`@capacitor-community/biometric-auth`)
or local notifications for low-battery alerts. Neither is in the project yet;
both are about a half-day's work.

## Android

### One-time setup

1. Install **Android Studio** (Hedgehog or newer).
2. Open Android Studio → SDK Manager → install SDK Platform 34 + Build-Tools 34.

### Open + run

```bash
cd frontend && npx cap open android
```

In Android Studio:

1. Wait for Gradle sync to finish.
2. Plug in an Android device with USB debugging on (or start an emulator).
3. Hit ▶ Run.

### Play Store submission

1. Google Play Console account ($25 one-time).
2. Build a signed AAB:
   ```bash
   cd android
   ./gradlew bundleRelease
   ```
   Output: `app/build/outputs/bundle/release/app-release.aab`.
3. In Play Console: create the app, upload the AAB, fill in store listing,
   privacy policy URL, content rating, submit for review.

Play Store is generally far more lenient than Apple — pure web-wrapper apps
typically pass review without native-feature gymnastics.

## Self-contained app — what works and what doesn't

The mobile build is genuinely self-contained: no FastAPI backend involved.
That comes with platform-level limits worth understanding before you ship.

### Works without a server

- Login + live tiles + raw data — fetched on-demand from EG4
- Battery forecast (model + historical ETA), battery cycle vs temperature
- Range chart, heatmap, today's production, excess chart
- Weather panel (Open-Meteo, fetched on-demand)
- Local SQLite history accumulates while the app is open

### Doesn't work the same as the web build

- **History has gaps.** The FastAPI poller runs every 60 s 24/7. On a phone,
  iOS Background App Refresh fires at most every 15–30 minutes and only
  when the OS decides to. While the app is in your pocket, no data is being
  recorded. Open the app for a few seconds and the latest minute lands in
  SQLite. Use **Sync** in the top bar to pull the missing days from EG4's
  history endpoint on demand.
- **Alerts only fire when foreground.** "Battery dropped below X%" can only
  fire as a local notification while the app is open. Real push alerts need
  a server somewhere with APNs/FCM credentials — outside the scope of a
  self-contained build.
- **Multi-site / appliances / scheduler / alerts panels are stubbed.** The
  `/api/sites`, `/api/appliances`, `/api/schedule`, etc. handlers return a
  501 "not yet ported" error in the local build. The web build still has
  them. Either port them next or hide those panels behind a feature flag in
  the mobile build.
- **EG4 portal changes will break things.** The `eg4Client.js` port uses the
  same undocumented endpoints as the Python library — if EG4 changes them,
  you'll have to update both sides.

## Quick smoke test on Mac (no device)

Capacitor's iOS simulator and Android emulator both work, but they don't
exercise the most interesting bit (talking to EG4 from a real network). For
that, run on a physical device once you have signing set up.

In Xcode: pick "iPhone 16 Pro" simulator → Run. Or in Android Studio: pick
"Medium Phone API 35" → Run.

## Troubleshooting

- **"No such module 'Capacitor'" in Xcode**: `npx cap sync ios` from
  `frontend/`, then in Xcode: File → Packages → Reset Package Caches.
- **Android Gradle sync fails**: check `android/local.properties` has
  `sdk.dir=/Users/chris/Library/Android/sdk` (or wherever your SDK lives).
- **`CapacitorHttp` CORS errors**: the requests should be going through the
  native HTTP stack. Make sure you import from `@capacitor/core` and call
  `CapacitorHttp.post(...)`, *not* `fetch(...)`.
- **SQLite "no connection" on first launch**: the connection is created
  lazily on first record; if you're seeing this, the plugin probably failed
  to link. `npx cap sync` and rebuild.

## What to do next

Tasks worth doing before you submit to the App Store:

1. **First-run onboarding screen** — replace the current `Login.jsx` web flow
   with a clean "enter EG4 username + password, hit Connect" screen scoped to
   the mobile build (currently it works but looks like a desktop login).
2. **Biometric unlock** (Face ID / fingerprint) before the saved credentials
   re-auth. `@aparajita/capacitor-biometric-auth` is a good pick.
3. **Port the appliances + scheduler endpoints** if you actually use those
   panels. They're the only big pieces of the web app that are stubbed.
4. **App Store screenshots** at the three required iPhone/iPad sizes —
   simulator screenshots from the Battery + History tabs work great.
