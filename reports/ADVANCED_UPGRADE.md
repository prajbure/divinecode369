# DIVINE CODE 369 — advanced in-place upgrade

Completed locally on 2 November 2026 in the existing FastAPI application at **http://127.0.0.1:8000/**. No new project, framework replacement, public deployment, order integration, production AI training or historical import was performed.

## Preservation and rollback

The [baseline audit](./advanced-upgrade-baseline.json) records all original sector definitions in order, all 160 stock memberships, all 148 unique configured symbols, the active dependencies, original 37 route registrations, scanner formulas and hashes for 41 protected files. This includes every original image/illustration, the scanner source, watchlist, aliases and calendar.

The sector-universe SHA-256 remains:

```text
61a211782942ffa56623e6dcf552f9952847300f07fdb157b61399e8bf564cad
```

The exact matcher still uses positive finite official prices and Decimal subtraction. Only an exact zero difference matches; a nonzero absolute difference up to the existing configured maximum is near. [The scanner source](../app/scanner.py) is byte-for-byte unchanged. The default presentation now groups exact matches first, then near matches by absolute difference; sortable headings remain available, and **Matches first** restores the default order.

The [final integrity report](./advanced-runtime-integrity.json) confirms:

- All 41 protected files and the private credential file are unchanged.
- 148 instrument records and 160 membership records remain.
- Complete original rows in candles, snapshots, scan results, imports, models, metrics, predictions and training evaluations are unchanged.
- SQLite integrity check: **ok**.
- Retention authorization and automatic retraining remain **false**.
- No artificial journal entries were inserted into the application database.

Rollback checkpoint: Git branch `rollback/advanced-upgrade-a85f4bb`, offline bundle `../.qa/advanced-upgrade-checkpoint.bundle`, and an online SQLite backup at `../.qa/advanced-checkpoint.sqlite3`. Credentials were not copied into the report or bundle.

For a code-only rollback, first stop the local server and review any later edits, then restore the modified original files from that branch:

```powershell
git restore --source=rollback/advanced-upgrade-a85f4bb -- app/main.py app/market.py app/provider.py scripts/build.mjs static/app.js static/index.html tests/browser.mjs tests/test_market_pipeline.py
```

Additional unreferenced modules can remain on disk. A code rollback does not drop the journal table or restore the database. Preserve any newly entered journal records before considering a database restore.

## Implemented improvements

### Readability and persistent header

- Additive typography/spacing stylesheet over the original neon theme. Larger navigation, page headings, sector titles, stock-name links, symbols, prices, differences, KPI values, history headings, controls, statuses and notes.
- Compact, Comfortable (default) and Large density settings, persisted locally. Density changes real CSS typography and spacing; no page transform or zoom.
- Primary controls have at least 44px targets. Tables scroll within their own containers; expanded forms fit narrow screens. The small-screen Kite control retains an accessible name.
- A 24-hour **HH:MM:SS LIVE IST** clock sits immediately beside the original brand in the sticky global header. The original body clock remains. Both use one guarded interval, with Asia/Kolkata formatting independent of browser timezone and market feed.
- Header height is measured by one ResizeObserver. Scroll margins account for it; table headings stay within their own scrolling containers below the global header. At 320px, connection controls use a second header row.
- The header clock has `aria-live="off"`, so screen readers do not announce every second. Focus styles, skip navigation and the existing responsive menu remain.

### Sector and regime intelligence

- Expandable intelligence on every original sector page: unique-constituent advances/declines/unchanged counts, average, median, advance breadth, gap counts, strongest/weakest constituent, freshness and optional volume/VWAP coverage.
- The Sector Strength Radar compares all 16 original custom baskets and explicitly distinguishes them from official NSE sector indices. Duplicate memberships inside a basket count once; cross-sector memberships remain.
- Participation labels distinguish broad-based moves, top-two concentration and mixed participation. Raw coverage and denominators are shown.
- Market Regime uses transparent thresholds for breadth, mean/median movement, basket participation and coverage. Results include supporting observations, contradictions and unavailable inputs. Scope is the approved sector universe, not the separate personal watchlist or the whole exchange.
- Optional benchmark context uses the existing on-demand Kite index endpoint. High/low volatility classifications require a valid live INDIA VIX timestamp no older than 60 seconds. No extra background index polling is added.

### Opening, volume and price structure

- Optional opening-gap percentage, gap-up/down/flat labels and same-session gap-fill progress. These do not change the original opening-difference calculation or official opening anchor.
- Provider-supplied average traded price supports VWAP and distance only when volume and provenance are valid. Day high/low supports intraday range position. Actual supplied bid/ask data supports spread and quantity imbalance; no depth values are invented.
- Cumulative volume is separate from observed-window activity rates, rate ratios/acceleration and normalized price momentum. Rates require fresh, ordered observations at least five seconds apart and reset after gaps, counter decreases, session changes and transport changes. These ratios are explicitly **not historical relative volume or institutional flow**.
- Five- and fifteen-minute opening-range functions require every completed one-minute Kite candle from the official session open. They support completed-candle breakout/breakdown, failed breaks and retests. Consecutive complete candles support higher/lower highs and lows, consolidation and range expansion.
- Previous high/low requires the exact previous verified trading session's authorized stored daily candle, not today's quote high/low.
- The private **Load authorized stored candles** action reads already stored, authorized data only. It performs no provider download and never enables retention. With retention disabled it returns an explicit unavailable reason.
- Opening anchors now respect the published special-session opening time and reject new anchors on verified closed days. Existing unknown-calendar behavior is retained; quote freshness remains unknown when calendar coverage is unavailable.

Kite field mappings were checked against the official [market-quote documentation](https://kite.trade/docs/connect/v3/market-data-and-instruments/) and [WebSocket documentation](https://kite.trade/docs/connect/v3/websocket/). Fields are conditional on what the provider actually returns; endpoint access is not treated as retention permission.

### Opportunity Radar and confluence

- An optional radar supplements the original scanner, with unique instruments, sectors, LTP, original difference, gap, sector strength, relevance, evidence coverage and quote-quality status.
- Six configurable factors: opening structure, sector participation, price confirmation, observed volume activity, liquidity and freshness.
- Separate supporting, contradictory and unavailable observations with explanations. Failed breaks remove price-confirmation points; stale/closed quotes earn no freshness points.
- Missing factors contribute zero. Weights are never redistributed around unavailable evidence. A score is rule relevance, **not probability of profit**. No BUY/SELL instructions are produced.
- Search, exact/near/fresh/contradiction filters, minimum score, sorting and row limits. Weight preferences persist locally. Expanded evidence stays open across updates.

### Alerts, risk and personal journal

- Optional alert types: original exact/near match, opening-gap threshold, sector-strength changes, completed-candle breakout/breakdown, observed VWAP reclaim, volume-rate activity, stale quote and provider disconnection.
- Alerts default to disabled. Preferences, thresholds and cooldown persist locally. Continuous conditions are deduplicated; session rollover re-arms appropriate alerts. Price-based alerts require verified live quotes during an open session.
- Alert history is bounded to 200 events in tab memory, with the latest 30 displayed and IST timestamps. It is deliberately not persisted as market-data history. Browser notifications require an explicit permission action and are limited per update.
- Risk calculator validates direction, capital, entry, stop, optional target and costs. Integer-paise/BigInt arithmetic avoids floating-point quantity boundary errors. Quantity includes estimated total round-trip charges, per-share round-trip slippage and a cash-capital limit. It shows risk, quantity, value, estimated stop loss, costs and net reward/risk. Gaps/slippage can exceed planned loss.
- Manual trading journal on Dashboard and History, using a new SQLite table `personal_journal_v1` and an index. It supports IST entry time, approved symbol/sector, setup, long/short direction, entry/exit, quantity, stop, target, charges, notes and lessons.
- Safe create/edit/delete, idempotent retry of an unchanged creation identifier, explicit delete confirmation and protected CSV export. Original market tables are not repurposed.
- Decimal net P&L, win rate, average win/loss, profit factor, expectancy and breakdowns by setup, sector and IST entry hour. Open trades are excluded from realized metrics. No-loss/empty cases are explicit rather than infinite or fabricated metrics.
- Journal reads and writes require local owner access or the existing administrator authorization. Manual journal storage does not turn on market-data retention.

### Reliability and data quality

- Data Quality Command Center: session configuration, actual transport, browser connection, last received socket tick, actual active subscriptions, provider timestamp, live/stale/closed/unknown counts, missing symbols, NSE session, last market refresh, last opening scan and provider errors.
- A connected socket or configured token is not presented as proof of fresh quotes.
- Exhausted socket retries release the old ticker for a later reconnect attempt. Callbacks from a replaced socket cannot overwrite the current connection state.
- EventSource startup closes an earlier stream and clears its polling fallback. Existing fallback polling and shared provider caching remain. Clock and AI-status timers are guarded against duplicate initialization.
- Cached date formatting, shared per-update price analysis, bounded alert/context state, limited radar rows and conditional DOM replacement reduce repeated work. At most eight explicitly loaded candle contexts are retained in browser memory.

## Actual verification

| Check | Baseline | Final |
| --- | ---: | ---: |
| Python regression/integration tests | 51 passed | **66 passed** |
| Financial formatting checks | 10 passed | **10 passed** |
| New pure intelligence/risk/alert checks | — | **33 passed** |
| Actual Chrome browser checks | 59 passed | **100 passed** |
| Served scanner build | Existing build retained | **Passed** |
| TypeScript check of retained frontend | — | **Passed** |
| Editor diagnostics | — | **No errors** |
| Git whitespace check | — | **Passed** |
| Original universe and protected-file hashes | Recorded | **Unchanged** |
| SQLite integrity and original stored market rows | Recorded | **Preserved** |

All six implementation stages were tested, repaired where checks failed, and then completed. Machine-readable stage results: [1](./advanced-stage1-checks.json), [2](./advanced-stage2-checks.json), [3](./advanced-stage3-checks.json), [4](./advanced-stage4-checks.json), [5](./advanced-stage5-checks.json), [6](./advanced-stage6-checks.json), [final](./advanced-final-checks.json). Detailed runner logs are under the ignored `.qa/advanced-*` paths.

Browser verification covers desktop 1440px, tablet 768px and phones 375px/320px; expanded personal tools; original table filters/search/sorting; all 16 sector routes; table headings below the sticky header; clock visibility at every sector-page bottom; Los Angeles browser timezone; offline clock progression; one clock timer; actual risk-form arithmetic; private journal reads; disabled-retention handling; advanced filters; density persistence through reload; ticker pause/resume; reduced motion; and no JavaScript/HTTP resource errors during the final run.

Two existing date-dependent tests formerly generated weekend quote fixtures. Their fixtures now use known trading dates while retaining the original immutable-opening/rollover assertions. New tests separately cover a verified closed day and the Muhurat pre-open boundary.

Earlier stage runs used **146 real closed-session instrument observations** from the already connected local server. They were labeled closed, with zero live observations. The backend restart cleared the in-memory daily token, so the final browser run correctly showed unavailable quotes. **No open-market live-stream testing or production model training is claimed.** Synthetic candles/trades used for unit tests stayed in isolated fixtures and temporary test databases.

## Screenshots

These are actual local-browser captures, not mockups.

| View | Screenshot |
| --- | --- |
| Final dashboard, desktop | [Open image](./advanced-dashboard-desktop.png) |
| Final dashboard, mobile | [Open image](./advanced-dashboard-mobile.png) |
| Banking sector, desktop | [Open image](./advanced-sector-desktop.png) |
| Banking sector, mobile | [Open image](./advanced-sector-mobile.png) |
| IT Services expanded intelligence | [Open image](./advanced-sector-intelligence.png) |
| Sticky clock at the bottom of a sector page | [Open image](./advanced-sticky-clock.png) |
| Dashboard before restart, with real closed-session quotes | [Open image](./advanced-dashboard-connected.png) |

## Modified and added files

Modified original files:

| File | Purpose |
| --- | --- |
| [app/main.py](../app/main.py) | Register additive private API router |
| [app/market.py](../app/market.py) | Optional quote fields, subscription/tick health, socket recovery and calendar-aware anchor timing |
| [app/provider.py](../app/provider.py) | Normalize only supplied optional Kite quote fields |
| [static/index.html](../static/index.html) | Persistent header clock, density control, stylesheet and accessible connection label |
| [static/app.js](../static/app.js) | Single clock, density persistence, additive panel hooks, match-first sorting, stream/timer cleanup |
| [scripts/build.mjs](../scripts/build.mjs) | Syntax-check and package additional static modules |
| [tests/browser.mjs](../tests/browser.mjs) | 100 browser checks and requested screenshots |
| [tests/test_market_pipeline.py](../tests/test_market_pipeline.py) | Deterministic trading-day fixtures for original regression assertions |

New implementation files:

| File | Purpose |
| --- | --- |
| [app/advanced.py](../app/advanced.py) | Private journal and authorized stored-context endpoints |
| [app/journal.py](../app/journal.py) | Safe separate journal table, validation, Decimal P&L, analytics and CSV |
| [static/command-center.css](../static/command-center.css) | Additive readability, density and responsive/sticky layout rules |
| [static/intelligence-core.js](../static/intelligence-core.js) | Pure sector/regime/opening/volume/confluence/scoring/alert/risk rules |
| [static/command-center.js](../static/command-center.js) | Optional intelligence panels and existing feed integration |
| [static/personal-tools.js](../static/personal-tools.js) | Alert preferences/history, risk form and manual journal UI |

New audit and test files: [audit script](../scripts/audit_advanced_upgrade.py), [stage runner](../scripts/verify_advanced.mjs), [read-only integrity verifier](../scripts/verify_upgrade_integrity.py), [preservation/reconnect tests](../tests/test_advanced.py), [journal tests](../tests/test_journal.py) and [pure intelligence tests](../tests/intelligence.mjs). This report, audit/result JSON files and screenshots are the documentation deliverables.

## Unsupported or conditional features and limits

- Complete opening ranges, failed breaks/retests, previous-session high/low and candle-derived structure require authorized stored candles with complete coverage. None were imported for this upgrade; the current retention/intraday settings continue to withhold them.
- Historical relative volume remains unavailable: no licensed, comparable same-time historical baseline was loaded. Observed-window activity is a different measure.
- VWAP, spread and supplied-depth imbalance remain unavailable when valid fields are missing. Receiving an optional field does not establish permission to retain or redistribute it; no extra entitlement is assumed.
- Watchlist-derived breadth and dispersion do not describe the whole NSE market. VIX context is on demand and expires from usable live classification after 60 seconds.
- Complete-candle event confirmation uses consecutive available minute candles. It does not reconstruct missed ticks, claim exchange-complete tick coverage, or forecast subsequent profitability.
- Alerts are local to the open browser tab; there is no background server alert delivery. Refreshing clears their event history. Desktop notifications depend on browser permission.
- The risk calculator uses user-entered estimates and a cash-capital constraint; it does not verify broker margin/borrow eligibility, execution prices or actual charges.
- Journal analytics depend entirely on complete and accurate manual entries. The UI shows the latest 500 records; analytics and CSV include the full journal.
- The backend must remain a single worker for the existing shared streaming/session design. The NSE calendar still needs future exchange amendments and the next annual file.
- This upgrade is local and unpushed. The existing Render deployment was not changed. The restarted local process currently needs a new daily Kite login before provider-dependent behavior can be checked again.

## Windows PowerShell startup and verification

The updated app is already running through the existing **Run Open Match Scanner** task. To start it later, first stop any process already serving port 8000, then use the existing project environment:

```powershell
Set-Location 'C:\Users\prajw\Downloads\open_match_scanner_updated\open_match_scanner'
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Alternatively, `npm run dev` starts the same FastAPI application with reload enabled. Backend restarts clear its in-memory daily Kite session; use **Connect Kite** at http://127.0.0.1:8000/ afterward. Preserve the existing private credential file and disabled retention/training settings.

Reproduce the acceptance checks:

```powershell
node scripts/verify_advanced.mjs final
& '.\.venv\Scripts\python.exe' scripts/verify_upgrade_integrity.py
npm run typecheck
npm run build
```

The browser runner requires the existing server and installed Chrome. `CHROME_EXECUTABLE` can select another Chrome installation; `DIVINE_PYTHON` can select the existing project interpreter for the stage runner. No dependency or framework migration is required.
