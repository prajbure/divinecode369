# DIVINE CODE 369 Android

Developed by ER PRAJWAL AMBURE.

Native Kotlin, Compose and Material 3 client for the existing `https://divinecode369.in/` backend. There is no second scanner service or provider SDK in this application.

## Current validation status

The Gradle wrapper and project configuration run successfully. Twenty Kotlin source/test files passed a local Kotlin 2.2.21 syntax parser. Android compilation, lint, JVM tests and instrumented tests have **not** run successfully: the actual `assembleDebug` attempt stopped because Android SDK Platform 36 and Build Tools 35 licenses have not been accepted. No APK or release artifact has been generated. Syntax parsing is not Android compilation or device validation.

The owner must accept [Google's Android SDK terms](https://developer.android.com/studio/terms) before SDK installation continues. The license question is pending; the agent has not accepted it.

## Build after SDK acceptance

From the repository root in PowerShell:

```powershell
# Only after the owner has accepted Google's SDK terms:
./scripts/setup_android.ps1 -AcceptAndroidLicenses
./scripts/android_build.ps1
```

The setup script verifies official download checksums and installs tools under the ignored `.qa/android-tools` folder. It does not require a global JDK/Gradle installation. Pinned compatibility baseline: JDK 21, Gradle 8.13, AGP 8.13.2, Kotlin/Compose compiler 2.2.21, compile/target SDK 36, Build Tools 35.0.0, minimum SDK 26.

Library pins: Compose BOM 2025.12.00, Hilt 2.57.2, Retrofit 3.0.0, OkHttp 4.12.0, Coroutines 1.10.2, Kotlin serialization 1.9.0, Room 2.8.4, DataStore 1.2.0 and WorkManager 2.11.0. These are compatible project pins, not a claim that every dependency is the newest available release. Complete versions are in the [app build](app/build.gradle.kts).

Once a build succeeds, the debug APK is expected at `app/build/outputs/apk/debug/app-debug.apk`. Verify it before sharing:

```powershell
./.qa/android-tools/sdk/build-tools/35.0.0/apksigner.bat verify --verbose android/app/build/outputs/apk/debug/app-debug.apk
./.qa/android-tools/sdk/platform-tools/adb.exe install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Enable USB debugging on a test device and authorize its connection. The provisional debug package is `in.divinecode369.app.debug`. The release namespace is provisionally `in.divinecode369.app`; Google Play package availability has not been verified in the owner's Play Console. Debug builds are for testing, not Play distribution.

## Account connection

Choose More → Sign in → Connect device. The app creates a PKCE-bound request and displays a matching code. Open secure approval in a browser, sign in with the existing owner account, compare the code and approve. The backend issues a 15-minute scoped credential and a rotating refresh credential. Neither grants provider administration. Provider changes open the existing browser Connection Manager and require its administrator session and CSRF checks.

Session material uses AES-GCM with an Android Keystore key. Backup/cleartext traffic are disabled. OkHttp strips cookies and unexpected Authorization headers, attaches a device credential only to approved same-origin personal/research routes, and follows no redirects. No HTTP body logging, analytics, crash-reporting, advertising or Firebase SDK is configured.

## Local data and notifications

Room stores saved identifiers, alert choices, deletion tombstones and seen-event IDs. DataStore stores non-secret display/notification preferences. Provider quotes, IPO feeds and historical candles are not persisted on the phone. In-memory previous snapshots are labeled after a failed refresh. Foreground updates read the shared backend, and WorkManager synchronizes personal records/inbox events at Android's minimum periodic interval with network constraints and backoff. FCM is not configured; notifications are opt-in and may be delayed by Android power management.

Server records require a persistent backend filesystem/database. The existing Render configuration declares no disk. An ephemeral server replacement can revoke device sessions and lose synchronized server records; device Room records remain local. See the [implementation report](../reports/PLATFORM_IMPLEMENTATION.md) before production rollout.

## Tests to run on an isolated emulator

```powershell
./scripts/android_build.ps1 -Tasks testDebugUnitTest,lintDebug
./scripts/android_build.ps1 -Tasks connectedDebugAndroidTest
```

Prepared tests cover PKCE, contract nullability, credential destination restrictions, Room reopening/tombstones, Compose card actions, native back navigation and an offline refresh. Instrumented tests use synthetic in-process APIs and a dedicated test database. They have not been executed; an emulator/device and installed SDK are still required. Validate notification permission denial/grant, cold startup, process recreation, font scaling, tablet layouts and App Link verification on device before release.

## Release signing and links

No signing keys are committed. Release signing activates only with owner-provided `DIVINE_KEYSTORE_FILE`, `DIVINE_STORE_PASSWORD`, `DIVINE_KEY_ALIAS` and `DIVINE_KEY_PASSWORD`. Do not put secrets into Gradle source or version control. A release build without those inputs is not represented as signed or distributable.

Set the backend's public `ANDROID_APP_SHA256_CERTIFICATE` only after verifying the owner's release certificate and final package identifier. Until then, `/.well-known/assetlinks.json` returns an empty association list. The privacy page is `https://divinecode369.in/privacy`. No Google Play publishing was attempted.

## Contract

[Mobile OpenAPI](../contracts/mobile-v1.openapi.json) is generated from FastAPI. Regenerate both it and [Kotlin DTOs](app/src/main/java/in/divinecode369/app/data/api/MobileModels.kt) together using the configured Python environment:

```powershell
./.venv/Scripts/python.exe -m scripts.mobile_contract
```

Financial signals and IPO calculations come from the backend. Kotlin formats and filters the returned values; it does not reproduce the original scanner calculation.
