# Approved instrument reconciliation

Generated 2026-11-02T09:19:23.830930+00:00. Approved unchanged sector configuration + last verified Kite instrument master + cited issuer/exchange notices.

| Measure | Count |
| --- | --- |
| Configured sector entries | 160 |
| Unique requested instruments | 148 |
| Scan candidates (known suspension excluded) | 147 |
| Verified Kite instruments | 146 |
| Exact symbols | 142 |
| Explicit same-company aliases | 4 |
| Additional duplicate memberships | 12 |
| Unavailable or suspended | 2 |
| Unresolved aliases | 0 |

Approved membership keys stay unchanged. Verified same-company quote aliases are displayed explicitly. No BSE substitute, new company or invented quote is introduced.

## Resolutions and unavailable members

| Configured symbol | Verified provider symbol | State | Resolution | Explanation | Source |
| --- | --- | --- | --- | --- | --- |
| NSE:HFCL | NSE:HFCL-BE | verified | series | Same HFCL issuer in NSE BE (trade-for-trade) series; the approved sector entry stays HFCL. | [evidence](https://www.nseindia.com/market-data/lower-band-hitters) |
| NSE:LTIM | NSE:LTM | verified | renamed | NSE symbol changed from LTIM to LTM effective 2026-02-27; same listed issuer. | [evidence](https://nsearchives.nseindia.com/content/circulars/CML72948.pdf) |
| NSE:REC | NSE:RECLTD | verified | alias | Approved shorthand REC resolves to REC Limited's listed NSE symbol RECLTD. | [evidence](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_GOVERNANCE_152035_22042026122116_iXBRL_WEB.html) |
| NSE:SPICEJET | -- | unavailable | not_listed_on_nse | Issuer disclosure states NSE permission was withdrawn effective 2023-05-02; BSE listing is not substituted for the approved NSE entry. | [evidence](https://corporate.spicejet.com/Content/pdf/BSEIntimation_PD_20092024_signed.pdf) |
| NSE:STLTECH | NSE:STLTECH-BE | verified | series | Same Sterlite Technologies issuer in NSE BE series; the approved sector entry stays STLTECH. | [evidence](https://www.nseindia.com/get-quote/equity/STLTECH/Sterlite-Technologies-Limited) |
| NSE:TV18BRDCST | -- | suspended | suspended | Existing approved configuration marks this issuer suspended. Retained in membership; never subscribed as a live instrument. | [evidence](https://www.nseindia.com/get-quotes/equity?symbol=TV18BRDCST) |

## Duplicate memberships

| Instrument | Memberships | Extra entries |
| --- | --- | --- |
| NSE:HDFCBANK | Banking & Financial Services #1; Nifty Top Liquid Stocks (F&O) #2 | 1 |
| NSE:ICICIBANK | Banking & Financial Services #2; Nifty Top Liquid Stocks (F&O) #3 | 1 |
| NSE:SBIN | Banking & Financial Services #6; Nifty Top Liquid Stocks (F&O) #9 | 1 |
| NSE:TCS | IT Services #1; Nifty Top Liquid Stocks (F&O) #5 | 1 |
| NSE:INFY | IT Services #2; Nifty Top Liquid Stocks (F&O) #4 | 1 |
| NSE:RELIANCE | Oil & Gas #1; Nifty Top Liquid Stocks (F&O) #1 | 1 |
| NSE:BPCL | Oil & Gas #4; Oil & Gas #8 | 1 |
| NSE:TMPV | Automobile #3; Nifty Top Liquid Stocks (F&O) #10 | 1 |
| NSE:ITC | FMCG #2; Nifty Top Liquid Stocks (F&O) #7 | 1 |
| NSE:LT | Power & Infrastructure #5; Nifty Top Liquid Stocks (F&O) #8 | 1 |
| NSE:LODHA | Realty (Real Estate) #8; Realty (Real Estate) #9 | 1 |
| NSE:BHARTIARTL | Telecom #1; Nifty Top Liquid Stocks (F&O) #6 | 1 |

## Complete audit

[Machine-readable report](./instrument-reconciliation.json) includes all instruments, memberships, evidence and verification timestamps. Unverified metadata is labeled unverified; no missing company is substituted.
