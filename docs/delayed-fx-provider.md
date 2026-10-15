# Preferred delayed USD/KRW provider for the non-commercial demo

This decision supersedes the earlier five-minute primary-feed requirement and
inactive-exchangerate.dev notes. exchangerate.dev Free is the preferred
latest-available source; FRED DEXKOUS remains the delayed fallback/reference.
These are indicative simulated inputs, never real dealing or settlement quotes.
No AWS configuration or deployed provider was changed by this implementation.

## Source, timestamps and acceptance

The [official API documentation](https://exchangerate.dev/docs/api-reference)
documents a 900-second Free-feed delay. Request only USD/KRW from
`https://api.exchangerate.dev/v1/latest/USD?symbols=KRW`, with the existing
`EXCHANGERATE_API_KEY` environment variable in a Bearer header. The repository-root
`.env` remains ignored and untracked; no key is written into examples or source.
Redirects are disabled, timeouts are bounded, and error bodies/credentials are
never logged or returned. A missing key uses the validated FRED fallback.

Use `effective_at.KRW` as the observation timestamp. Never substitute the served
`timestamp`, `data_updated_at`, or local retrieval time for it. Preserve all four
separately. Require the Free delay header `X-Price-Delay-Seconds: 900`, correct USD
base/KRW quote, a positive finite Decimal rate, provider `stale.KRW` exactly false,
`sources.KRW=live` in the provider's terminology, recognized market session, and
consistent timezone-aware timestamps. The provider's `live` enum is not displayed
as a real-time claim; the application's source is explicitly 15-minute delayed.

Independently enforce:

- Observation age <=1,800 seconds (30 minutes).
- Retrieval age <=900 seconds (15 minutes).
- Response age at retrieval <=900 seconds; no future or inconsistent timestamps.
- The original observation date agrees with its UTC observation timestamp.

The 30-minute ceiling allows the documented 15-minute delay, up to ten minutes
of cache reuse, and five minutes of timing margin. This is an application safety
limit, not a latency SLA. Provider `stale=false` alone never authorizes use. Daily
responses and weekend/closed-session observations exceeding the same age limit
are rejected; their dates are never rolled forward. FRED keeps its existing
independent limits: observation <=10 calendar days, retrieval <=6 hours, cache
refresh after one hour. An invalid preferred quote uses FRED only if FRED passes
its own checks; if both are invalid, required FX valuation/conversion fails closed.
The legacy Twelve Data adapter retains its original 300-second checks.

## Refresh, quota and configuration

Default preferred adapter: `PAPER_FX_PRIMARY_PROVIDER=exchangerate_dev`.
An explicitly empty value permits a FRED-only rollback. The legacy licensed
adapter remains opt-in; no paid provider is enabled. The existing license flag
still applies to that legacy adapter, not to the explicitly authorized demo
choice. `EXCHANGERATE_API_KEY` is never renamed or copied.

The shared server-side rate cache refreshes on demand after 600 seconds, serialized
within the existing single API worker. This is not a new background scheduler.
A steady load produces approximately 4,320 calls per 30 days (4,464 per 31 days),
which fits even the lower 5,000/month figure appearing in official documentation;
account-specific quotas may differ. There are no per-user upstream refreshes.
HTTP 429 respects Retry-After (seconds or HTTP-date), with a ten-minute minimum
backoff and 31-day upper bound. Other failures also back off ten minutes. Cache
and backoff behavior do not bypass age validation. No live quota-exhaustion test
is performed.

Compose/template files pass the existing key variable and preferred adapter to a
future approved deployment; the actual AWS environment file is unchanged.

## Immutable history and UI

New rates append to the existing `paper_fx_rates` and `paper_fx_metadata` tables.
The new additive `paper_fx_provider_context` table stores immutable provider
context by rate ID. A database UPDATE trigger protects it, matching existing FX
and execution-history safeguards. Startup creates the table without modifying
existing rate, execution, portfolio or identity rows. No account reset is needed.

Existing cost/FX execution JSON captures the exact rate and metadata used. A
later provider switch changes current valuation inputs, not execution rates,
costs or historical P&L bases. The accounting layer still consumes normalized
Decimal rates and immutable rate IDs through the same provider abstraction.
Age is checked at use time; dynamic observation-age counters are deliberately
excluded from canonical settlement previews so a passing second cannot silently
change an approved plan. The confirmation screen now retains its complete
reviewed preview through final submission.

The UI displays delayed status in the portfolio FX summary, original observation
and retrieval timestamps in details/review, and historical execution timestamps
in execution conditions. It retains FRED's daily-reference wording. The visible
Free-plan attribution is exactly [Rates by Exchangerate.dev](https://exchangerate.dev)
on screens showing current or recorded exchangerate.dev rates. Legacy records
retain their own provider attribution. The [provider terms](https://exchangerate.dev/terms)
remain applicable; this demo decision does not establish broader export,
commercial redistribution or real-execution permissions. Reassess those uses
before changing the product scope.
