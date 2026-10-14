# Live market-data verification — 2026-10-14

Controlled manual refresh with real configured providers. UTC retrieval timestamps are shown below (add nine hours for Asia/Seoul). No observations were fabricated or filled to advance the common inference date. Deployment model SHA256 checksums remained unchanged.

| Market | Refresh | Observation date used by model | MSI | Stress threshold | 10D score / 100 | Stress event | Warning | Freshness |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| us | SUCCESS | 2026-10-09 | -1.159 | 1.292 | 11.9 | False | False | DELAYED |
| korea | SUCCESS | 2026-10-13 | 0.744 | 1.116 | 37.8 | False | False | CURRENT |

| Market | Series | Source | Latest value | Latest observation | Expected observation | Retrieved at (UTC) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| us | SPY | Yahoo Finance | 778.0999755859375 | 2026-10-12 | 2026-10-12 | 2026-10-14T00:17:22.935311+00:00 | CURRENT |
| us | VIX | Yahoo Finance | 15.270000457763672 | 2026-10-13 | 2026-10-12 | 2026-10-14T00:17:23.652274+00:00 | CURRENT |
| us | DBAA | FRED | 6.69 | 2026-10-09 | 2026-10-12 | 2026-10-14T00:17:25.378630+00:00 | DELAYED |
| us | DGS10 | FRED | 5.24 | 2026-10-09 | 2026-10-09 | 2026-10-14T00:17:25.432567+00:00 | CURRENT |
| korea | KOSPI200 | KRX | 942.07 | 2026-10-13 | 2026-10-13 | 2026-10-14T00:17:30.348696+00:00 | CURRENT |
| korea | VKOSPI | KRX | 48.53 | 2026-10-13 | 2026-10-13 | 2026-10-14T00:17:32.324925+00:00 | CURRENT |
| korea | Korea_Treasury_3Y | BOK ECOS | 3.857 | 2026-10-13 | 2026-10-13 | 2026-10-14T00:17:32.962382+00:00 | CURRENT |
| korea | Korea_Corporate_AAminus_3Y | BOK ECOS | 4.527 | 2026-10-13 | 2026-10-13 | 2026-10-14T00:17:33.639250+00:00 | CURRENT |

Latest series values may be newer than the snapshot indicators: the latter use the real common observation date shown in the first table. The U.S. credit lag is visible and does not become CURRENT merely because equity/volatility are fresh.

October 12 is a Board holiday even though NYSE was open. DGS10 excludes Board holidays; DBAA retains a conservative NYSE expectation because a reliable Moody’s publication SLA is not configured. The official [H.15 release](https://www.federalreserve.gov/releases/h15/) excludes holidays; [FRED DBAA](https://fred.stlouisfed.org/series/DBAA) and [FRED DGS10](https://fred.stlouisfed.org/series/DGS10) independently showed October 9 as the latest credit observation during verification.

Both ledger jobs completed SUCCESS with publication; per-series attempt histories and the full local report are retained in ignored `data/operations/live-verification-2026-10-14.json`. KRX attempt counts include independent per-session HTTP requests across the revision window, not ten retries for one request.

Scheduler health reports RAN for the expected session because manual refresh counts as execution, but heartbeat_fresh=false: the production scheduler is not running in this review environment. This verifies live refresh, not production uptime.
