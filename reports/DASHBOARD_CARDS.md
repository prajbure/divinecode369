# Interactive dashboard stock cards

Implemented 4 November 2026 in the existing DIVINE CODE 369 application.

Developed by ER PRAJWAL AMBURE.

Source commit: `6155f2005f21aa285db8fa140d0b865a517744b7`.

## Behavior

| Dashboard card | Destination | Classification |
| --- | --- | --- |
| Total Stocks | `/scanner?filter=all` | Every unique approved symbol, including unavailable/suspended entries |
| Exact Matches | `/scanner?filter=exact` | Backend `match` flag |
| Near Matches | `/scanner?filter=near` | Backend `near_match` flag |
| Matched Stocks | `/scanner?filter=matched` | Union of backend exact and near flags; one row per symbol |
| Bullish Stocks | `/scanner?filter=bull` | Existing positive daily `change_pct` classification |
| Bearish Stocks | `/scanner?filter=bear` | Existing negative daily `change_pct` classification |
| Verified Live | `/scanner?filter=live` | Backend `quote_status` is `live` |

Dashboard counts and global scanner rows use the same unique-symbol model. All sector associations remain visible; the original sector pages still retain their configured membership entries. The total card currently represents 148 unique stocks across 160 memberships, obtained from the approved universe rather than a hardcoded card count.

Search, sector, sorting, page size, page and optional difference bounds persist in the URL. Browser Back/Forward and refresh restore that state. A disappearing last page is synchronized to the URL during SSE updates, preventing a refresh from unexpectedly selecting an old page.

The existing stock-detail links, financial formatting, CSV export, SSE connection and fallback polling remain in use. Card navigation uses the current shared snapshot and adds no quote-fetch requests. No new provider polling or endpoint was introduced.

Cards are native keyboard-accessible links with focus indicators, hover/press states and directional icons. Exact matches use cyan. The existing scanner table now includes sectors, volume and the backend opening-gap percentage, distinct from daily change percentage. Missing values remain unavailable. Counts of zero are not represented as fabricated observations.

## Local verification

| Check | Result |
| --- | --- |
| Existing Python regression suite | 180 passed, 163.646 seconds |
| Existing JavaScript checks | 79 passed |
| New dashboard consistency checks | 10 passed |
| New HTTPS dashboard browser checks | 68 passed |
| Existing HTTPS administrator browser checks | 20 passed |
| TypeScript typecheck | Passed |
| Website packaging via existing VS Code task | Passed |
| Editor diagnostics on changed application/test files | No errors |
| Independent read-only review | Pagination issue corrected and regression-tested; no remaining findings |

Browser tests use an isolated loopback HTTPS FastAPI fixture with synthetic data classified by the real scanner. They exercise every card, exact/near/matched and movement filters, count consistency, unique-symbol counts, URL refresh, Back/Forward, search, sectors, sorting, stock details, clear filters, empty/unavailable data, keyboard activation, focus retention, actual SSE changes and pagination shrink/expansion. Layouts were checked at 1440, 768, 375 and 320 pixels.

Re-run local dashboard checks with `npm run test:dashboard` and `npm run test:dashboard:browser`. The browser runner uses the configured local Python environment, installed Chrome and the existing ignored test TLS certificate. No production provider credentials or Android tooling are used.

## Preservation

- No backend or Android source, mobile API contract, SDK configuration or hosting configuration changed.
- Existing authentication, CSRF, official provider authorization and original matching tolerance remain unchanged.
- All 16 sectors and 160 ordered memberships remain intact.
- Scanner SHA-256: `cedf41dd728d97b9221261fc8af7772ca005d016e542f7f5c86983b76e699f6d`.
- Sector-universe SHA-256: `61a211782942ffa56623e6dcf552f9952847300f07fdb157b61399e8bf564cad`.
- Unrelated pre-existing workspace changes were excluded from the deployment commit.

## Production verification

The feature commit is live at **https://divinecode369.in**. The existing Render service reports successful auto-deployment `dep-dble73dbedkc73a72kk0` of `6155f20`; no hosting settings were changed.

**34 production checks passed at 2026-11-04 08:00:11 UTC (13:30:11 IST).** The hosted application, new filtering module, stylesheet and approved universe match the committed Git blobs. Each of the seven real production cards opened its expected number of unique records and retained its filter through refresh. Desktop/mobile layouts, the single IST clock, administrator session endpoint and login form, the shared Android overview API, IPO Intelligence and the absence of browser JavaScript exceptions were verified.

The verifier compares Git blobs rather than Windows working-copy bytes so CRLF/LF differences cannot falsely report an old deployment. Nonzero classifications and SSE classification transitions were exercised with the local synthetic fixture; these tests do not claim live-provider prices or a successful real provider-token exchange. Production provider health reported IPO Guru connected and Kite degraded; no provider credentials or authentication were changed.

The read-only verifier is `npm run test:dashboard:production` (append `-- --wait` to wait for the tested source). It compares hosted JavaScript/CSS/universe assets with the local source and checks every card, refresh persistence, mobile layout, shared Android overview endpoint, administrator session/login form, IPO page and JavaScript errors. It does not submit scans, log in, change credentials or contact providers directly.
