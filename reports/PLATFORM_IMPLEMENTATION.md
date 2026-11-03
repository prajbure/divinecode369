# DIVINE CODE 369 unified Android + web platform

Developed by ER PRAJWAL AMBURE.

## Stage 1 — audited baseline

The production application is FastAPI with a static ES-module frontend. The React/Vite tree is a legacy presentation, not the served terminal. `app.main` owns one `MarketService`, one `IPOGuruClient`/`IPOService`, and one `ConnectionManager`. Mobile adapters must reuse those exact instances. Existing Kite OAuth, administrator session cookies, CSRF, single-use state and protected reads remain in place.

The scanner source and approved universe are preservation boundaries: 16 sectors, 160 memberships, 148 unique symbols and 147 eligible scan candidates. No order/application execution is implemented. Historical retention and model training remain disabled unless separately configured by the owner.

Existing IPO normalization already supplies price-band-based GMP estimates, final-issue-price listing returns, timestamps, financials, official registrar validation and Standard-plan resources. The new clients reuse those normalized records and shared cache.

Some advanced market analytics currently run in `static/intelligence-core.js`. Their backend equivalents will become the shared presentation contract; Kotlin will format values, not recalculate financial signals. Existing JS unit cases remain useful parity fixtures.

No Android/JDK/SDK/Gradle installation was found. Build tools are being installed into the ignored `.qa/android-tools` directory, using verified official archives. Android platform installation requires the owner's SDK license acceptance. The proposed release namespace is `in.divinecode369.app`; debug uses a `.debug` suffix. Domain administration is established through the existing deployment. Play package availability cannot be certified without the owner's Play Console; no publication or release signing is authorized.

Stage 1 gate: 45 existing preservation, sector, scan-auth and IPO tests passed (3.170 seconds). Existing unrelated report changes and the deleted environment template are preserved.

## Architecture decisions

- One backend, existing provider instances, additive `/api/v1/mobile` adapters and an exported OpenAPI contract.
- Native Kotlin/Compose/Material 3 app with Hilt, Retrofit/OkHttp, Coroutines/Flow, Room (user-owned records only), DataStore (non-secret preferences), Android Keystore encryption (mobile credentials), and constrained WorkManager synchronization.
- Browser-approved, PKCE-bound device sign-in issues short-lived scoped access credentials and rotating refresh credentials. A mobile token grants personal-data operations and approved private reads, never website administrator capabilities. Website cookies and CSRF stay separate.
- Public market and IPO pages remain public. Personal watchlists and alerts synchronize for the existing owner account; no unrequested multi-user registration is introduced.
- Provider feeds are not persisted on the device. Offline user-owned saved symbols, IPO identifiers, alert rules and preferences remain available; feed snapshots are in memory and explicitly stale/offline.
- Alerts are evaluated on the server against its shared cached overview. Delivery uses an authenticated inbox and opt-in local Android notifications. Firebase/FCM is absent until configured and explicitly approved.
- Release keys stay outside source control. Android App Links require an operator-provided release certificate fingerprint. No fabricated verified links or Play availability claims.

## Stage gates

| Stage | Scope | Status |
| --- | --- | --- |
| 1 | Repository/API/provider/auth/build audit | Passed baseline gate |
| 2 | Native foundation, design system, navigation, device login | Source implemented; browser/server device flow verified; native build pending SDK |
| 3 | Shared typed IPO contract and premium IPO screens | API and web verified; native screens implemented, device validation pending |
| 4 | Shared scanner/sector/stock analytics and native screens | Original files unchanged; 20 analytics parity fixtures pass; native execution pending |
| 5 | Synchronized personal data, alerts, settings | Server/browser behavior verified; Room/Keystore/notification execution pending |
| 6 | Concise responsive website and mobile IPO cards | 33 real Chrome checks pass at phone/tablet/desktop widths |
| 7 | Security, contract, browser, native tests | Python/JS/browser/source checks pass; Android compilation/lint/tests not completed |
| 8 | Debug APK, installation, release preparation | Actual build blocked by unaccepted SDK licenses; no APK or release artifact |

## Operational constraints

The existing hosting plan and provider subscriptions are retained. The earlier Render deployment used ephemeral SQLite storage; durable cross-device server records require a persistent deployment volume/database. Device Room and web user-owned local storage can retain pending personal changes, but ephemeral hosting is not represented as durable storage. No paid hosting upgrade is performed without authorization.

Detailed stage results, exact dependency versions, artifact hashes and installation instructions will be appended as they are verified.

## Root cause and retained authorization fix

The original owner actions called administrative routes without a server-verified browser login. A backend-only token/localhost gate could not authorize the deployed browser securely. The earlier authentication repair (base commit `1c194844e874a64e6f285daf829117dae2f97c00`) introduced server-side password verification, opaque Secure/HttpOnly/SameSite cookies, CSRF checks and revocation. A blanket cross-site check also rejected the legitimate Kite top-level return; its narrowly defined callback exception still requires the owner session, state cookie and single-use server-bound state. That fix remains in place.

This platform change does not grant an Android credential access to `/api/scan`, Kite reconnect/disconnect, provider verification, credential changes, imports or training. Browser approval gives it only market/IPO/research reads and personal-data writes. Owner password/key rotation invalidates both approvals and device credential families. Website mutations retain cookie/Origin/CSRF requirements. There is no localhost authorization exception.

## Implemented behavior

- Native Compose/Material 3 screens with Home, Scanner, Market, IPO and More navigation; nested sector, stock and IPO details; account connection, watchlists, alerts, health, history, settings and prediction status. Provider administration opens the existing owner browser. Native UI execution remains unverified.
- IPO phases, board filters, search/pagination, price band/GMP/subscription cards, watch/share actions and seven detail sections. Allotted requires a provider confirmation rather than an elapsed expected date. Original calendar, comparison, research, anchor and local alert tools remain available on the website.
- Shared Python sector/regime/opening/volume/relevance calculations. Existing JS numeric rules match across 20 deterministic fixtures. Volume observation runs once every five seconds on the backend, independently of client reads. The scanner file itself is unchanged. Archived GMP versus actual listing comparison also runs server-side.
- Typed `/api/v1/mobile` adapters and [OpenAPI](../contracts/mobile-v1.openapi.json), with generated [Kotlin models](../android/app/src/main/java/in/divinecode369/app/data/api/MobileModels.kt), pagination/filtering/sorting, timestamps, stale/unavailable flags and documented cookie/bearer alternatives. Large JSON snapshots are compressed; the existing SSE path and authentication responses are excluded.
- Owner-approved PKCE device flow, hashed server credentials, 15-minute access, rotating seven-day refresh, 30-day absolute family lifetime, reuse detection, owner revocation and per-peer request limits. Public dashboard/scanner/IPO access remains as before.
- Shared personal watchlists and alert rules, deletion tombstones, preferences and event inbox. Backend evaluation reads the existing cache/snapshot once per minute; it makes no provider requests. GMP changes need a fresh source and an in-memory baseline; subscription thresholds need a recent verified category total. Stock alerts need live verified quotes and an open session. Expected schedule notifications are labeled as expected/scheduled.
- Android Room holds only user-owned records, DataStore holds non-secret preferences and Android Keystore encrypts session material. Worker synchronization/inbox delivery uses constraints/backoff and opt-in notification permission. These Android runtime properties still require device validation.
- Compact web hero, phone bottom navigation, original sector assets/navigation, concise IPO cards and expandable research/provider diagnostics. Settings exposes synchronized preferences and approved-device revocation. A privacy page is provided.

## Actual verification

| Check | Actual result |
| --- | --- |
| Initial preservation gate | 45 tests passed, 3.170 s |
| Repeated stage API/preservation gates | 60, then 62 tests passed as features were added |
| Final full Python suite | 179 tests passed, 32.092 s |
| Final focused mobile/events/parity checks | 24 passed, 7.223 s; includes compressed real ASGI snapshot and uncompressed authentication response |
| JavaScript formatting, intelligence, IPO, clock and admin request helpers | 79 checks passed (10 + 35 + 17 + 5 + 12) |
| Real Chrome HTTPS administrator regression | 20 checks passed, including simulated cross-site provider navigation and exactly one exchange |
| Real Chrome platform journey | 33 checks passed: device code/approval, PKCE scoped access/logout, cookie CSRF, IPO filters/details/watchlist/alerts, 320/375/768/1440 px layout, sectors and clock |
| Client/source preservation and secret checks | 13 passed; [audit JSON](PLATFORM_AUDIT.json) |
| Website packaging | `npm run build` passed; packages the actual FastAPI-served static UI |
| Kotlin syntax parser | 20 Kotlin files, zero syntax errors; this is not Android compilation |
| Gradle wrapper/project configuration | Passed using JDK 21 and Gradle 8.13 |
| Actual Android assembleDebug attempt | Failed before compilation: licenses missing for `platforms;android-36` and `build-tools;35.0.0` |
| Android JVM tests, lint, instrumentation, APK installation/startup/App Links | Not run successfully; pending SDK/emulator/device |
| Live provider exchange, trading, IPO applications | Not performed |

Browser evidence is in [PLATFORM_BROWSER.json](PLATFORM_BROWSER.json), [phone fixture capture](platform-ipo-phone-fixture.png) and [desktop fixture capture](platform-ipo-desktop-fixture.png). Fixture companies are explicitly labeled TEST FIXTURE; they are not live IPO validation. Live deployment checks are recorded separately after deployment.

The original scanner SHA-256 is `cedf41dd728d97b9221261fc8af7772ca005d016e542f7f5c86983b76e699f6d`. The original sector JSON SHA-256 remains `61a211782942ffa56623e6dcf552f9952847300f07fdb157b61399e8bf564cad`. Neither file was edited.

## Changed files

- Backend: [main](../app/main.py), [configuration](../app/config.py), [credential redaction](../app/logging_filters.py), [mobile authentication](../app/mobile_auth.py), [API adapters](../app/mobile_api.py), [schemas](../app/mobile_models.py), [OpenAPI security](../app/mobile_openapi.py), [snapshot compression](../app/mobile_compression.py), [personal records/events](../app/personal.py), [market analytics](../app/market_intelligence.py), [listing comparison](../app/ipo_comparison.py).
- Web: [entry HTML](../static/index.html), [application](../static/app.js), [admin helpers](../static/admin-auth.js), [command center](../static/command-center.js), [existing IPO tools](../static/ipo.js), [premium IPO](../static/ipo-premium.js), [personal tools](../static/platform-personal.js), [platform styles](../static/platform.css), [approval page](../static/mobile-connect.html), [approval logic](../static/mobile-connect.js), [privacy](../static/privacy.html).
- Android: [project and build instructions](../android/README.md), [app Gradle configuration](../android/app/build.gradle.kts), [manifest](../android/app/src/main/AndroidManifest.xml), and the core/data/UI, icon/theme/security, unit and instrumented-test sources under [app source](../android/app/src).
- Tooling/contracts: [SDK setup](../scripts/setup_android.ps1), [build runner](../scripts/android_build.ps1), [contract generator](../scripts/mobile_contract.py), [source audit](../scripts/platform_audit.py), [web build](../scripts/build.mjs), [generated contract](../contracts/mobile-v1.openapi.json), [ignore rules](../.gitignore), and [persistent-mount guide](../deploy/PERSISTENCE.md).
- Tests: [mobile security/API](../tests/test_mobile.py), [shared analytics](../tests/test_market_intelligence.py), [personal events](../tests/test_personal_events.py), [JS parity fixture](../tests/analytics-parity.mjs), [Chrome helper](../tests/browser_client.mjs), [platform browser journey](../tests/platform_browser.mjs), [mocked HTTPS server](../tests/platform_fixture.py).

Pre-existing unrelated report changes and the deleted environment template are not part of this change.

## Remaining release gates

1. Owner SDK license acceptance. [Build instructions](../android/README.md) are ready; no license was accepted by the agent, and no APK/signature/install or Android test pass is claimed.
2. Durable server storage. [Concrete mount configuration](../deploy/PERSISTENCE.md) is prepared. The current blueprint declares no disk, and no hosting-plan or billing change was made. Local SQLite reopen tests do not establish durability across Render replacement.
3. Run the Android unit/lint/instrumented suite and inspect the APK on a dedicated emulator/device, including permissions, cold startup, process recreation, back navigation, font scaling and tablet behavior. Prepared Android tests have not run.
4. Verify the final package in the owner's Play Console, configure owner signing and the public certificate fingerprint, and validate App Links. No release key or Play publication was created.

The execution tool rejected a final native presentation-edit script with only `rejected by user` as its reason. That script was not rerun. The existing native source and all independent verification remain available for review.

Official compatibility references: [AGP 8.13](https://developer.android.com/build/releases/agp-8-13-0-release-notes), [Compose BOM](https://developer.android.com/develop/ui/compose/bom/bom-mapping), [Hilt Gradle setup](https://dagger.dev/hilt/gradle-setup.html), [Android SDK terms](https://developer.android.com/studio/terms), [Render persistent disks](https://render.com/docs/disks).
