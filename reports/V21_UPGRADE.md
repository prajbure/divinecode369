# DIVINE CODE 369 — V2.1 upgrade

Developed by ER PRAJWAL AMBURE.

## Release scope

This upgrades the existing FastAPI application and static JavaScript/CSS frontend in place. It preserves the original scanner, routes, settings, journal, watchlist, logos and sector artwork. No AI training, trading or IPO applications are enabled.

- Two-row sticky navigation, responsive More menu, one permanent IST clock beside the logo, and removal of the duplicate market-time strip.
- Comfortable default typography with persistent Compact, Comfortable and Large density settings.
- Backend connection manager and detailed health views, separate authentication, network and freshness states, official Kite login/recheck/disconnect, validated session restoration and bounded feed reconnection.
- Independent IPO Intelligence immediately after AI Predictions: overview, GMP, subscription, details, allotment links, comparison, calendar, listing performance, local alerts and explainable research scores. Missing or unauthorized provider fields remain unavailable.
- Shared IPO caching, scope checks, request deduplication, persistent quota accounting, backend refresh scheduling and stale-data labels.
- Optional stock intelligence, sector breadth/dispersion, opening/price/volume observations, explainable opportunity scoring, alerts, risk calculator and SQLite journal.

## Preservation checks

The protected universe still contains exactly 16 sectors, 160 memberships and 148 unique instruments. Its SHA-256 remains:

`61a211782942ffa56623e6dcf552f9952847300f07fdb157b61399e8bf564cad`

The original scanner implementation is unchanged. Original sector mappings and artwork pass integrity checks. Retention authorization and automatic model training remain disabled. Existing research, journal and settings records are preserved. The user changed backend environment configuration during the upgrade; that file was never rewritten by the upgrade.

## Actual verification

[Full check results](./v21-final-checks.json): **430 checks passed**, including 127 Python tests, 10 formatting, 35 intelligence, 100 original browser, 5 clock, 17 IPO frontend, 66 IPO browser and 70 V2.1 browser checks. Static build, TypeScript checks and integrity verification passed.

[Kite restoration check](./v21-session-restoration.json): a real saved local session survived a cold backend restart and an authenticated profile validation. The market was closed; this is not a claim of live tick testing.

[IPO account check](./v21-ipo-account-check.json): the configured key successfully authenticated with the documented `/me` endpoint. The actual account reports **Free**, scopes `calendar`, `details`, `gmp`, limits **1 request/minute and 10/day**. Standard-only history, subscriptions, full financials and anchors require appropriate purchased access. Deploying the site does not change that plan.

Browser checks cover desktop, tablet and mobile widths, all 16 sector routes, long-page scrolling, one clock, keyboard navigation and the IPO tab position. Data-rich IPO screenshots use clearly labelled deterministic fixtures; they are not live provider results.

## Screenshots

- [Desktop dashboard](./v21-dashboard-desktop.png)
- [Mobile dashboard](./v21-dashboard-mobile.png)
- [Mobile navigation](./v21-navigation-mobile.png)
- [Connection dropdown](./v21-connection-dropdown.png)
- [Connection manager](./v21-connection-manager.png)
- [Data health](./v21-data-health.png)
- [Sector intelligence](./v21-sector-intelligence.png)
- [Sticky clock after scrolling](./v21-sticky-clock.png)
- [IPO integration disabled locally](./v21-ipo-unconfigured.png)
- [GMP history — fixture](./ipo-gmp-chart-fixture.png)
- [Subscription — fixture](./ipo-subscription-fixture.png)

## Backend configuration

Set secrets only in the backend environment or Render Environment page. Do not commit environment files or put credentials into browser storage.

```text
IPOGURU_API_KEY=<your private key>
IPOGURU_BASE_URL=https://www.ipoguru.in/api/v2
IPOGURU_ENABLED=true
DATA_RETENTION_AUTHORIZED=false
AUTO_RETRAIN_ENABLED=false
```

The local provider remains disabled unless the user changes its existing configuration. Production activation needs the key configured separately in Render. Account scopes, not the page URL or plan label requested in a prompt, determine available features. Visible attribution links to [IPO Guru](https://www.ipoguru.in/). See the [official API documentation](https://www.ipoguru.in/ipo-gmp-details-developer-api).

Keep existing Kite backend credentials and the registered callback URL. Complete the official daily login when required. Passwords, TOTP and CAPTCHA are never automated. Windows session persistence uses current-user DPAPI encryption and an ignored private directory. On Linux/Render this release uses memory-only Kite sessions when encrypted persistence is unavailable, and reports that limitation explicitly: a restart requires official login. No local token is uploaded as part of deployment.

Render runs the existing Python build/start commands. Its persistent storage availability depends on the existing service configuration; no paid hosting change is included. On ephemeral storage, SQLite additions and local quota metadata can be lost on redeployment. Configure an existing persistent disk before relying on durable hosted journals. The local database is not uploaded or replaced.

## Windows startup

From the existing project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. For verification, run `node scripts/verify_v21.mjs` while the local application is running.

## Rollback

The pre-V2.1 checkpoint is commit `aa082bec866dc647356214589d14ab7f1821823c`, also named `rollback/pre-v21`. Render can redeploy its previous successful release without changing local user data. To inspect the checkpoint safely in a separate folder:

```powershell
git worktree add ..\divine-v21-rollback rollback/pre-v21
```

The ignored `.qa/pre-v21.sqlite3` file is the local database checkpoint. Stop the backend and make a new backup of current user data before any deliberate database restoration. Do not overwrite the current environment file or private session directory.

## Remaining limits

Validated historical candles, comparable volume baselines, market depth and provider VWAP are required for corresponding observations; incomplete data is never fabricated. GMP is unofficial and speculative. Research scores measure rule-based relevance, not profit probability or investment recommendations. Personal allotment checks open official registrar websites and do not collect PAN or application secrets.

Deployment verification is recorded separately in the release deployment report after the hosted version is observed.
