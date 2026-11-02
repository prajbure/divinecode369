# DIVINE CODE 369

**Market Intelligence by Shubham DK** — the existing FastAPI / Zerodha Kite opening scanner, upgraded with a neon terminal interface, shared streaming quotes, private research storage and a calibrated prediction lab. No order execution is implemented.

## Run the existing application

Use Python 3.10+ and the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The existing **Run Open Match Scanner** VS Code task starts this same application. `npm run dev` also starts the existing Python backend, with reload enabled; it no longer opens the unrelated legacy React marketing frontend.

Keep existing credentials in `.env`. See [.env.example](./.env.example) for documented options; **do not replace a working credential file with the template**. Renew the daily Kite session through **Connect Kite**. Login now uses a short-lived HttpOnly state cookie; begin login in the same browser that receives the callback. Tokens and secrets stay on the server.

The browser that completes Kite login can run opening scans remotely using a signed HttpOnly session cookie, valid for up to 12 hours. Reloads and page navigation preserve that access. A backend restart or a changed Kite session invalidates it; reconnect Kite in that browser when prompted. The cookie authorizes scans only. Watchlist changes, historical imports and model actions still require localhost access or an administrator token.

## Interface and routes

- `/`: compact IST clock above the live ticker, new bull/bear hero, opening-match statistics, 16 sector cards, the opening scanner, movement chart and AI preview.
- `/sectors` and `/sectors/{id}`: every approved sector, its own illustration, unique-stock breadth, and all requested entries in the table.
- `/scanner`: all 160 configured entries, exact/near/bullish/bearish filters, search, sorting, absolute opening-difference controls, pagination and CSV export.
- `/stocks/{symbol}`: actual quote, opening reference, forecast state and historical context.
- `/live-market`: feed health, stock movements and optional on-demand index quotes.
- `/history`: original eight-session history, stored candle queries and explicitly authorized historical imports.
- `/ai-predictions`: training status, coverage, model evidence, calibrated forecasts and realized outcomes.
- `/settings`: provider capabilities, retention policy, remote administration and the separate personal watchlist.

The approved [sector universe](./static/sector-universe.json) is unchanged: **16 groups × 10 entries = 160 entries**, **148 unique symbols**, **147 scan candidates** after excluding the configured suspension. Repeated BPCL and LODHA entries remain. Quote requests and sector averages use unique symbols. Unavailable symbols remain displayed; replacements are never added automatically.

## Exact opening rules and live data

Only an exact decimal `open - previous_close == 0` is **EXACT MATCH**. A nonzero absolute difference up to `MAX_DIFFERENCE` is **NEAR MATCH**. Missing, zero or invalid opening prices are never matches. Live last-price movement is distinct from opening gaps and from forecasts.

[MarketService](./app/market.py) maintains one approved subscription set, in-memory cache and batched REST fallback per server process. Optional Kite full-mode WebSocket data uses exchange timestamps, reconnects with backoff and falls back to REST. Quotes are streamed to browsers using Server-Sent Events with automatic browser reconnection and heartbeat comments. Browsers without working SSE poll the shared cache, without creating extra provider subscriptions. Updates are coalesced to at most one browser snapshot every two seconds; the clock advances independently every second.

Regular-session fallback defaults to 10 seconds, constrained to at least 3 seconds. Outside session hours the service refreshes at most every five minutes. Provider REST requests share a conservative one-request-per-second budget. Index context is explicitly on demand and cached for 30 seconds. No raw tick stream is stored.

The first official open/reference close for an exchange-dated session is frozen. Later ticks update last prices, percentages, breadth and ticker order without recalculating opening matches. Authorized scan persistence can restore opening anchors after restart; with retention disabled the anchor exists only in memory. A new exchange trading date clears the previous session's in-memory anchors.

Quote freshness uses **provider timestamps**, never the fetch clock. Missing timestamps are unknown, old quotes are stale, and closed-session quotes are labeled closed. A socket connection alone does not make a quote live. The current implementation can verify successful streaming and historical HTTP requests; it cannot infer contractual data retention/redistribution rights or market-depth entitlement.

## Exchange calendar

[The official 2026 NSE Capital Market calendar](./data/nse-calendar-2026.json) includes the annual trading-holiday circular, the January 15 amendment, the Sunday February 1 Budget session and the November 8 Muhurat session. Each entry has exchange-source provenance. Bank/settlement holidays are not treated as equity trading holidays.

[Session evaluation](./app/calendar.py) handles weekends, pre-open, continuous trading, closing and post-close periods in Asia/Kolkata. The special Muhurat window also identifies the separate CAS auction transition. Navbar, clock strip, scanner and ticker share this status. Quote freshness is independent of the session label.

Calendar coverage ends on 2026-12-31. Add the next official annual file and subsequent amendments before relying on future-year market status; unknown years fail closed as **Calendar unavailable**. Manually verified operator overrides remain available through `MARKET_HOLIDAYS`, `MARKET_SPECIAL_SESSIONS` and `MARKET_CALENDAR_VERIFIED_THROUGH`. These are operational settings, not a substitute for reviewing new exchange circulars. The opening scan follows the configured official session opening time, including special sessions.

## Historical storage and provider permissions

There was no database in the original app. [Store](./app/storage.py) adds SQLite with WAL, foreign keys, indexes and idempotent schema initialization. The private default file is `data/divine.sqlite3`; it is ignored by Git. Tables cover instruments, ordered sector memberships (including duplicates), daily/intraday OHLCV candles, aggregated quote snapshots, immutable scan results, model versions, evaluation metrics, rejected evaluations, predictions and verified capability observations.

Historical access and data retention are separate settings, **disabled by default**:

```dotenv
HISTORICAL_ENABLED=true
DATA_RETENTION_AUTHORIZED=true
# Enable intraday only if separately authorized:
INTRADAY_ENABLED=false
```

Enable these only after confirming the account's provider/exchange rights. A successful historical request proves endpoint access, not retention or redistribution permission. No rights are inferred from an API key. The original transient eight-session historical viewer remains available without persistent storage.

The configured paid historical API was verified with successful transient OHLCV requests. `HISTORICAL_ENABLED=true` now records that capability locally. **`DATA_RETENTION_AUTHORIZED=false` remains unchanged pending the owner's explicit confirmation of permitted storage and ML use.** Intraday storage, automatic history updates and scheduled retraining remain disabled.

From **History**, select an approved instrument or the full approved candidate universe, interval and range, then queue a backfill. [The import service](./app/imports.py) persists jobs, per-symbol cursors, committed batches, retry attempts, skipped instruments and last successful batch timestamps in the existing SQLite database. Failed or interrupted jobs support resume; active jobs support cancellation. Replayed batches are idempotent. Both request-time and write-time authorization are enforced.

Daily imports support 1–1,825 calendar days in conservative 180-day requests and exclude unfinished sessions. Intraday imports are separately gated and limited to 30 calendar days, with smaller provider-safe chunks. Finite and consistent OHLCV values are required. Provider requests share the quote adapter's rate budget; no historical requests are made per market tick. The UI reports missing data rather than filling prices.

**Incremental update** overlaps the latest stored sessions to catch provider corrections. After an authorized initial backfill, `HISTORY_AUTO_UPDATE_ENABLED=true` schedules incremental updates at 18:20 IST on known trading days for instruments already stored in the approved universe. It never starts an initial paid backfill on its own. Keep the server running for schedules. Imports do not imply that an AI model has passed validation.

[The reconciliation report](./reports/instrument-reconciliation.md) explains all approved entries and explicit same-company aliases. Run `npm run reconcile -- --refresh` with a connected Kite session to regenerate the JSON/Markdown audit. An unavailable or suspended NSE member is not replaced with a different exchange or issuer. The separate personal watchlist still supports the original transient historical viewer.

Retention defaults: 1,825 days daily candles/scans, 30 days intraday, seven days aggregated snapshots. Snapshots are sampled at a configurable interval (minimum 60 seconds, default 300), only for verified live quotes. Daily maintenance prunes expired rows. Configure `DATABASE_PATH` and `MODEL_DIRECTORY` on a persistent private volume for production, and back them up. Existing Render free hosting uses ephemeral storage and may sleep; it cannot guarantee persistence or scheduled execution. Do not run multiple Uvicorn workers: each process would otherwise create its own provider subscription and scheduler.

## DIVINE AI — Market Prediction Lab

[PredictionLab](./app/predictions.py) uses NumPy/scikit-learn/joblib. It compares **Logistic Regression** and **Random Forest**, with no optional deep-learning or XGBoost dependency. Models are research classifiers, not trading agents.

Features use completed candles only: 1/5/20-session returns, volatility, volume ratio, opening gap, moving-average distances, ATR, RSI, MACD, sector momentum and available-universe breadth. Long missing-data runs and suspicious unadjusted price jumps are excluded. Cross-sector features use only the same completed date. The dataset uses the current approved universe, so survivorship bias and provider corporate-action adjustment limitations remain.

The target is explicitly **next trading session's open-to-close direction**. It is not a prediction of today's live quote or a close-to-close executable strategy. The training workflow:

1. Loads validated authorized daily candles. Requires at least 180 feature dates and 300 labeled observations; around 240 completed candles per stock starts feature coverage. Each calibration/training fold also needs sufficient observations in both classes, so these minimums do not guarantee trainability.
2. Reserves the final 25% of dates as an untouched out-of-sample test period. Purges labels crossing split boundaries.
3. Compares candidates using three chronological walk-forward folds with a session gap. Each fold fits its scaler/model on its earlier training subset and a Platt calibrator on the final chronological 20% of that subset.
4. Selects by mean validation Brier score, then evaluates the selected calibrated model once on the reserved test period.
5. Saves a model only with at least 30 test sessions, defined ROC-AUC ≥ 0.5, and Brier score better than the fixed training-prior baseline. Failed evaluations are recorded; no new forecasts are published from a rejected model.
6. Saves a private versioned artifact, metrics and predictions. The final model is not refit on the held-out test period. Inference only uses the latest completed input date. Predictions are deduplicated by version, instrument, input date and horizon; subsequent inference reconciles realized next-session returns.

Metrics include directional accuracy, precision, recall, F1, ROC-AUC, log loss, Brier score, calibration error/bins, majority-prior and no-change baselines, sample coverage, costed research returns and drawdown. The strategy uses equal allocations, next-session open/close execution, a 55% probability threshold, cash for untraded allocations and configurable round-trip fees plus slippage. Verified BE trade-for-trade instruments are excluded from this intraday strategy backtest and remain in cash; direction forecasts are still clearly labeled research. Liquidity, borrow availability and capacity are not guaranteed. MAE/RMSE and predicted return ranges are explicitly unavailable for these classifiers.

Training can be triggered in the lab; it runs off the HTTP request thread. `AUTO_RETRAIN_ENABLED=true` attempts retraining at 18:30 IST only when at least `TRAINING_MIN_NEW_SESSIONS` (default 20) new stored feature sessions exist. Historical imports are explicit; there is no automatic paid backfill. Use **Generate forecasts** after importing new authorized data. An empty or rejected dataset shows **Prediction unavailable — insufficient validated historical data.** No accuracy, profits or forecasts are invented.

## Security and deployment

- Keep `.env`, SQLite files, model artifacts and admin tokens private and out of Git. The existing credentials were not overwritten.
- Local mutations require a loopback client and host. Remote opening scans also accept the signed browser session issued after successful Kite login. Other remote mutation/import/training calls require a server-configured `ADMIN_TOKEN`, entered into Settings for that browser tab only or supplied as `Authorization: Bearer …`. Cross-origin mutations are rejected. Provider tokens are never stored in browser storage.
- Use HTTPS and private network/access control for hosted use. The application is a **single-owner research terminal**, not a multi-user data redistribution service. Read endpoints are not a substitute for a deployment access gateway. Configure trusted proxy/client forwarding correctly; do not expose it publicly without your own access control and provider permission.
- Provider errors are redacted; secrets remain server-side. Full WebSocket mode is requested only for the approved tokens. Market depth is not requested or advertised as supported.
- No order placement endpoints exist.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static/app.js
npm run typecheck
npm run test:frontend
npm run build
npm run build:legacy
# With the FastAPI app running, and installed Chrome:
node tests/browser.mjs
```

The Python suite covers unchanged universe/matching rules, opening anchors, exchange dates/holidays/special sessions, freshness, sorted performers, retention/deduplication, routes, OAuth state, SSE updates/heartbeat, feature-prefix invariance, walk-forward/OOS training, model artifacts, inference and unavailable states. Synthetic data exists **only inside isolated tests**; it is never loaded into the application database or shown as market data.

The dependency-free Node browser suite uses installed Chrome and checks live SSE updates, independent clock, ticker pause/resume/sorting, colors, desktop/tablet/mobile layouts, scanner controls, reduced motion and resource/runtime errors. Set `CHROME_EXECUTABLE` for another Chrome path and `DIVINE_TEST_URL` for another local server. Temporary QA outputs are ignored by Git.

`npm run build` validates and packages the **actual scanner interface** into `dist/terminal`; that package still requires FastAPI for APIs/auth/SSE and is not a standalone demo. The legacy React source is retained. TypeScript 5.9.3 is pinned in the existing npm lockfile. `npm run typecheck` checks application sources; `skipLibCheck` avoids unrelated published third-party declaration errors. `npm run build:legacy` verifies that retained frontend in the ignored QA directory and preserves its existing tracked deployment files.

## Original artwork

Sixteen original transparent illustrations were individually generated with the built-in image-generation tool, then optimized to 384px WebP (about 536 KiB total). [Artwork subjects and prompt set](./static/sectors/artwork.json) and the [optimization helper](./scripts/optimize_artwork.py) are included. The dashboard hero now uses two original AI-generated realistic bull/bear images with transparent backgrounds. Responsive WebP pairs total about 427 KiB for desktop or 124 KiB for mobile. [Exact hero prompts](./static/hero/artwork.json) and [optimization script](./scripts/optimize_hero.py) are included. Decorative chart graphics are explicitly labeled and never presented as market observations. The old hero SVG is no longer loaded.

See [COMPLETION_REPORT.md](./COMPLETION_REPORT.md) for the latest completion results, and [IMPLEMENTATION.md](./IMPLEMENTATION.md) for the implementation inventory, verification results and remaining operational setup.
