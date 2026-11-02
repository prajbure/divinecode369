# DIVINE CODE 369 — IPO Intelligence

Developed by ER PRAJWAL AMBURE. Added to the existing FastAPI/static application in place, for local personal use. No deployment was performed.

## Open the terminal

Use **http://127.0.0.1:8000/ipo**. The main navigation places **IPO Intelligence immediately after AI Predictions** and before History. The existing logo, branding and single sticky IST clock serve every IPO screen. IPO rendering also works when the stock status endpoint fails.

The integration is currently **disabled and unconfigured**. No real IPO Guru request or live IPO integration check was performed. The connected Kite feed was unavailable during acceptance testing; Kite behavior was checked with existing mocked regression/reconnect tests and unchanged provider source.

## Implemented screens

- **Overview:** eight summary cards, company search, board/status filters, sorting, status badges, minimum investment, source freshness and backend request-budget information. Recent closed/listed counts use 30 days within the provider's three-month calendar window. Awaiting-allotment counts use expected future/today dates, not a claim that allotment is announced.
- **GMP Tracker:** rupee GMP, percentage, price band, final issue price, arithmetic listing estimate, source timestamps and day-wise SVG history. Missing readings remain gaps. Zero and missing values remain distinct. GMP is prominently labelled unofficial and speculative.
- **Subscription:** current QIB, NII/HNI, retail, employee, shareholder, anchor/other supplied categories, totals, subcategories, source timestamps and readable comparison bars. No historical subscription endpoint is called.
- **Company details:** issue terms, schedule, business description, reported financial statements, KPIs, promoters, strengths, risks, objects of issue and available document links. GMP history, subscriptions and anchor allocations load on demand. Unsupported or absent sections say unavailable.
- **Allotment:** expected dates, provider-supplied basis-of-allotment confirmation when present, registrar names and allowlisted HTTPS registrar links. No PAN, OTP, bank credentials or application secrets are requested. Unknown registrar domains are withheld pending verification.
- **Listing Performance:** actual listing price and returns against the final issue price; provider-supplied current price with separate freshness. Archived GMP comparison is optional and requires a pre-listing daily reading, archive cap, final issue price, listing date and actual listing price. Incompatible price bases are rejected. This is archived arithmetic, not a forecast recorded by this application.
- **Comparison:** up to five IPOs with price, issue size, lot size, investment, subscription, reported financials, valuation KPIs, risks, strengths and dates. Selection is local; provider financial payloads are not saved in browser storage.
- **Calendar:** published opening, closing, expected allotment and expected listing dates.
- **Research Radar:** fixed 100-point rule relevance with supporting, contradictory and missing factors. Comparable annual revenue growth: 25; positive annual PAT: 25; subscription ≥1×: 20; positive non-stale timestamped GMP: 10; four company disclosure sections: 5 each. Missing factors receive zero. Valuation is not scored without a verified peer benchmark. No AI, investment recommendation or profit probability is implied.
- **Alerts:** optional opening/closing/allotment/listing date, GMP-threshold and subscription-update alerts; local preferences, cooldowns, duplicate suppression, session history in IST and permission-based browser notifications. Alerts evaluate data loaded during use; they do not run a background polling service. Alert history and observed financial values remain in memory.

## Backend and quota handling

The official [IPO Guru v2 documentation](https://www.ipoguru.in/ipo-gmp-details-developer-api) was reviewed on 2 November 2026. Standard publishes 1,000 requests/day and 20/minute, including day-wise GMP history, current subscriptions and anchors. Actual plan, scopes and limits are verified through `/me`; free/lapsed accounts receive their lower returned limits. Intraday GMP, subscription history, OFS and unlisted data are outside this integration. Personal allotment API checking is unavailable on all plans.

Only these provider resources are allowed: `/me`, `/ipos`, `/gmp`, `/ipos/{slug}`, `/ipos/{slug}/gmp/history`, `/ipos/{slug}/subscription`, `/ipos/{slug}/anchors`.

- The key is sent only in the backend `X-API-KEY` header. Redirects are disabled and the configured HTTPS origin must match the official v2 origin.
- Shared memory caching defaults to 15 minutes; minimum 5 minutes. Low remaining budget extends cache reuse to one hour. `/me` verification is cached for six hours. Browser refresh respects the shared cache; it does not force a provider request.
- A lock deduplicates concurrent cache misses. Bulk `/gmp` replaces per-company GMP polling. Detail resources load only when needed. There are no IPO polling intervals.
- A separate ignored SQLite quota ledger survives restarts and records only hashed key identity, request times, daily counts and remaining budget. It contains no raw IPO responses or credentials. Provider rate-limit headers constrain the remaining budget. Reset follows midnight IST.
- 401/403 stop authentication retries until explicit verification or server restart. A 402 blocks the denied scope until explicit verification. Burst 429 honors Retry-After; daily exhaustion waits for the next IST day. Outages use deferred exponential backoff: 15, 30, 60 seconds up to 15 minutes. A later on-demand request retries after the delay; no worker sleeps or browser retry loops are added.
- Cached fallback responses carry an error and stale flag. Source freshness is independent of fetch time and ages through the existing clock without another timer. Missing source timestamps stay unknown.
- Cache/deduplication is per server process. Run the existing **single-worker** local startup. Multiple workers share quota reservations but do not share the memory cache. Other applications using the same key can consume quota; response headers reconcile the remaining budget when available.
- IPO data is normalized into personal UI responses; no competing raw feed, persistent IPO data archive, order execution, IPO application automation or training is added.

Readable attribution appears on every IPO screen: **Data by IPO Guru — https://www.ipoguru.in/**.

## Configure securely

[Configuration defaults](../app/config.py) and the [.env.example](../.env.example) contain:

```dotenv
IPOGURU_API_KEY=
IPOGURU_BASE_URL=https://www.ipoguru.in/api/v2
IPOGURU_ENABLED=false
IPOGURU_CACHE_SECONDS=900
```

Supply your own key only in the backend environment, then explicitly enable the integration and restart the local server. Do not put it in JavaScript, screenshots, chat, Git or a URL. Existing local credentials were not edited. With no valid configuration, the IPO page remains usable and honest about unavailable data.

In Windows PowerShell, stop the existing server task first, then use the existing virtual environment:

```powershell
Set-Location "C:\Users\prajw\Downloads\open_match_scanner_updated\open_match_scanner"
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

To enable IPO Guru for that PowerShell session without writing or echoing the key:

```powershell
$ipoSecret = Read-Host "IPO Guru API key" -AsSecureString
$env:IPOGURU_API_KEY = [System.Net.NetworkCredential]::new("", $ipoSecret).Password
$env:IPOGURU_BASE_URL = "https://www.ipoguru.in/api/v2"
$env:IPOGURU_ENABLED = "true"
$env:IPOGURU_CACHE_SECONDS = "900"
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `/ipo` and use **Verify provider**. The backend validates `/me`; watch the displayed plan, quota and scope errors. This action consumes one request. Correcting environment credentials requires a server restart. Remote verification uses the existing admin authorization; local verification uses the existing loopback policy.

## Preservation and rollback checkpoint

- Local checkpoint commit: `a7ac0338d7f7c1ce85ef6825ef0625876784ca25`; branch `rollback/pre-ipo-upgrade`.
- [Audit manifest](./ipo-baseline.json) records all pre-IPO application/static hashes, exact sector definitions and original routes. An online SQLite backup and private credential-file hash are retained in ignored local QA storage.
- [Integrity result](./ipo-integrity.json): all 63 protected pre-existing app/static files outside the four intentional integration files match their baseline. All original routes and all database table contents are preserved. SQLite integrity is `ok`; the existing credential file is unchanged.
- Exactly **16 sectors / 160 memberships / 148 unique symbols**. The exact/near scanner source, Kite provider, market pipeline, storage, original images and brand assets remain unchanged.
- Original universe SHA-256: `61a211782942ffa56623e6dcf552f9952847300f07fdb157b61399e8bf564cad`.
- `DATA_RETENTION_AUTHORIZED=false`; automatic training remains disabled. Existing AI Prediction features remain present.

The checkpoint is a reviewable local commit. Do not overwrite current user database records when rolling back code; keep the online backup separate and review any data restore explicitly.

## Changed files

Existing integration files:

- [.env.example](../.env.example) — blank opt-in configuration example.
- [app/config.py](../app/config.py) — separate IPO environment defaults.
- [app/main.py](../app/main.py) — include the dedicated IPO router.
- [static/index.html](../static/index.html) — one navigation entry and stylesheet.
- [static/app.js](../static/app.js) — IPO route mounting, independent initialization and reuse of the clock for freshness labels.
- [scripts/build.mjs](../scripts/build.mjs) — include IPO JavaScript syntax checks in the existing static build.

New implementation:

- [app/ipoguru.py](../app/ipoguru.py), [app/ipo_service.py](../app/ipo_service.py), [app/ipo_routes.py](../app/ipo_routes.py).
- [static/ipo.js](../static/ipo.js), [static/ipo-core.js](../static/ipo-core.js), [static/ipo.css](../static/ipo.css).
- [tests/test_ipo.py](../tests/test_ipo.py), [tests/ipo_frontend.mjs](../tests/ipo_frontend.mjs), [tests/ipo_browser.mjs](../tests/ipo_browser.mjs), [tests/ipo_fixture.py](../tests/ipo_fixture.py).
- [scripts/audit_ipo_upgrade.py](../scripts/audit_ipo_upgrade.py), [scripts/verify_ipo_integrity.py](../scripts/verify_ipo_integrity.py), [scripts/verify_ipo.mjs](../scripts/verify_ipo.mjs).
- This report, IPO audit/check-result JSON files and the screenshots below. Stage regression results are saved as `advanced-ipo-*-checks.json` alongside them.

## Actual validation

Pre-change baseline: **66 Python + 10 formatting + 33 intelligence + 100 original Chrome browser checks = 209 passed**. Backend and UI stages also passed the existing regression suites.

Final acceptance results are recorded in [ipo-final-checks.json](./ipo-final-checks.json), [regression checks](./advanced-ipo-final-checks.json), [IPO Chrome checks](./ipo-browser-checks.json) and [integrity checks](./ipo-integrity.json). The final runner executes all suites, fixture generation, integrity verification, static build and TypeScript checking:

| Suite | Passed |
| --- | ---: |
| Python (66 existing + 30 IPO) | 96 |
| Original financial formatting | 10 |
| Existing intelligence rules | 33 |
| Original Chrome regression checks | 100 |
| IPO formatting, charts, alerts and comparisons | 17 |
| IPO Chrome acceptance checks | 66 |
| **Total** | **322** |

Static build, TypeScript validation, whitespace checking and editor diagnostics also passed. No live IPO market-data testing is claimed.

```powershell
node scripts/verify_ipo.mjs
```

Browser validation includes all nine IPO screens; 1440, 768, 375 and 320px layouts; horizontal financial-table scrolling; clock visibility at the bottom of every screen; a Los Angeles browser time zone; one clock interval after navigation; stock-status failure isolation; reserved subscription categories and genuine zero values; five-IPO comparison limit; official registrar links; alerts and local preferences. Provider response tests cover scopes, malformed fields, concurrency, authentication failures, outages, burst/daily limits, restart persistence and source timestamps.

## Screenshots

The first image shows the actual unconfigured local app. All other screenshots are explicitly labelled **TEST FIXTURE DATA — NOT LIVE MARKET DATA** and use isolated browser interception. These examples never enter the production app, scanner universe or database.

- [Actual IPO dashboard — provider unconfigured](./ipo-dashboard-unconfigured.png).
- [IPO dashboard — desktop fixture](./ipo-dashboard-desktop-fixture.png).
- [IPO dashboard — mobile fixture](./ipo-dashboard-mobile-fixture.png).
- [Day-wise GMP chart — fixture](./ipo-gmp-chart-fixture.png).
- [Subscription dashboard — fixture](./ipo-subscription-fixture.png).
- [Sticky IST clock during scrolling — fixture](./ipo-sticky-clock-fixture.png).

## Remaining limits

A valid backend key and successful `/me` response are still required for live IPO data. Published fields, document links, financial metrics and source timestamps may be absent or delayed; unavailable is not zero. Unknown registrar domains need verification before being allowed. Current listed prices come only from the IPO provider when returned; no new Kite subscriptions or IPO additions to the protected universe are made. No historical subscription charts, intraday GMP, OFS bid book, unlisted/pre-IPO prices or personal allotment API checks are enabled. Browser notifications require permission and an open application; this is not an always-on alert service. No Render deployment or public publication was performed.
