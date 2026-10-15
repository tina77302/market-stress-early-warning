# Real stress-evidence verification scope

Both real-data evidence paths were verified locally on October 15, 2026 using
new disposable users, genuine validated quotes, reviewed settlement previews,
simulated orders and the existing authenticated analytics endpoint. Existing
accounts and AWS were not changed. The source methodology is documented in
[reviewed evidence and lifecycle](real-stress-evidence.md).

| Market | Verified chain |
|---|---|
| U.S. | NVDA security history → XLK sector / SOXX industry context → actual USD-equity exposure → historical sensitivity → conditional 10D distribution |
| Korea | SK hynix (`000660.KS`) security history → KODEX IT (`266370.KS`) / semiconductor (`091160.KS`) context → reviewed USD→KRW funding and costs → actual exposure → historical sensitivity → conditional 10D distribution |

Both positive paths met the unchanged central/range and downside sample minima.
The security-level histories were preferred; proxies and industry benchmarks
remained separately identified. No fabricated prices, classifications, model
outputs, future FX paths or recommendations were introduced.

The underlying models and model SHA-256 identities were unchanged:

- U.S. XGBoost: `90c51c245ebe62b58f804098a7a7045b60fb64ef83da72d4c9a049cf8d5eeb0d`.
- Korea XGBoost: `42c3026386a58b25df337a431fbd5a793e93665a3d9a3f2cf22be4cfcc9186e3`.

## Browser follow-up

Chromium desktop 1440/1640px and responsive 390px views were captured and visually
inspected in English and Korean. Checks covered search by ticker/company name,
auto quotes, quantity estimates, explicit conversion, fees beside final submit,
cash/share limits, actual versus conditional history, all five exposure
dimensions, uncovered Samsung and one account holding both markets.

Uncovered Samsung retained unknown classification and unavailable portfolio
scenarios. Mixed-market holdings retained separate contributions and withheld a
combined outlook. A separate disposable process with the preferred key withheld
verified actual FRED failover; real credentials were not exposed or changed.

The NVDA positive-state capture preceded the 17:00 KST U.S. publication boundary.
Afterward FRED DBAA/DGS10 observations still ended October 13; a normal isolated
refresh succeeded but U.S. health was DELAYED and conditional results were
correctly withheld. Korea remained current on October 14. The final U.S.
positive-state presentation should be rechecked when upstream inputs catch up.
Physical mobile keyboards, Safari/Firefox and genuine multi-day account history
remain additional browser checks.

## Private artifacts and rights

Exact numerical reports, event outcomes, raw histories/receipts and archives stay
under ignored `data/paper/stress-evidence/`. Browser screenshots and QA reports
stay under ignored `data/paper/browser-qa/`. Disposable database paths, account
records and runtime credentials are not repository assets. The public source
record deliberately omits their host-specific paths and numerical return tables.
A fresh checkout therefore cannot reproduce the positive paths without approved
local data and fresh validated snapshots.

These are historical conditional scenarios, not forecasts. Source review and
local evaluation approval do not confirm public display/redistribution rights.
`public_display_rights=not_confirmed` remains in evidence provenance. Private
bundles are not included in Git or staging artifact exports. No evidence coverage
was expanded, no provider research was added, and no account reset, commit, push
or AWS deployment was performed during this verification.
