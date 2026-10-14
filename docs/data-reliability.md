# Validated market snapshots

See `data-reliability-audit.md` for the original pipeline inventory. The operational package is `src/operations`; original research calculations, targets, thresholds, model artifacts and validation results remain unchanged.

## Refresh and recovery

```
python -m src.operations refresh --market both
python -m src.operations health --market both
python -m src.operations history --market both
python -m src.operations schedule --once
```

First setup requires existing historical data and trained deployment models. To establish a historical last-known-good snapshot before providers succeed, an operator can explicitly run `python -m src.operations adopt-local --market both`. This validates/recomputes cached observations in isolation, marks retrieval provenance unknown and never treats adoption as current. No legacy model score is blindly trusted. The U.S. cache has only a derived credit spread: independent DBAA/DGS10 provenance becomes available after the first provider refresh.

Each independent series is fetched with up to three attempts per request and 1/2-second exponential delays. HTTP connection/timeouts, 429/5xx and empty expected-session responses are transient. Schema, units, auth errors, duplicate/order/date/numeric/finite violations are permanent. Attempt records contain sanitized errors, never ECOS URLs or keys. KRX requests at most 90 calendar days with a 14-day revision overlap; larger gaps require explicit historical backfill. Yahoo/FRED/ECOS re-fetch complete history, accepting revisions without changing feature definitions. ECOS pagination overflow fails closed.

Raw history, calculation logs and features are staged in an immutable per-job directory. The worker runs unchanged existing cleaner/feature/MSI/threshold calculations in a separate process with redirected paths, and uses existing deployment models. Nothing trains or writes to live research output files. 400 common observations are required for existing warm-up/threshold logic. Source identifiers and expected units are fixed by provider contracts; ECOS also verifies response series IDs/units.

U.S. historical VIX/credit filling remains limited to the existing cleaner's five observations. The current candidate date must be a real observation in every critical input; history is cut at that common date before calculations. Korea introduces no fill: missing input on an equity observation date fails validation rather than shortening the rolling calendar. Extreme positive price/volatility moves are accepted; moves of 30% or more raise a nonblocking review flag. Finite features, exact existing model feature names/order, aligned finite MSI/thresholds, valid unrounded output and unchanged model checksum are required before publication.

One SQLite transaction inserts the validated snapshot, changes the market pointer and completes the job. SHA256 validates stored payload integrity. Date regression and non-finite payloads are rejected. Identical payload publication is idempotent; same-date revisions can produce new audited versions. A per-market OS lock serializes processes. Interrupted jobs become ERROR when the next worker obtains their lock. Failure never changes the pointer. U.S. and Korea refresh independently.

## Scheduler and freshness

Production Docker Compose enables `MARKET_REFRESH_ENABLED=true` by default; local `.env.example` leaves scheduling disabled. API startup launches the poller only when enabled. A standalone scheduler is also supported. Every startup/poll compares the expected due exchange session, job ledger and committed snapshot, allowing missed-window catch-up. Failed/delayed refreshes retry after 30 minutes; polling occurs every minute. Multi-worker API instances share the same lock and storage.

Exchange calendars use XNYS/XKRX holidays and early closes. Due deadlines are exchange close +12h for U.S. end-of-day/FRED inputs, +6h for Korea. Before that deadline the previous due session remains expected. These allowances are operational policy, not provider publication guarantees; review them against provider SLAs before launch. Calendar errors fail closed. The ledger persists heartbeat, expected session/deadline, last run and run-session. Health derives MISSED independently from data age and reports a heartbeat older than five minutes. Manual refresh counts as a job run but does not disguise an old scheduler heartbeat. External monitoring must poll health to detect a completely stopped service.

## Serving and monitoring

`/api/latest` and `/api/korea/latest` read committed snapshots, preserving numeric fields and adding `data_health`. They never infer from mutable CSVs. No valid snapshot returns 503. Stale/delayed/partial/error responses retain real observation dates and explicit `is_current=false`. Frontend classifications fail closed when health is absent/noncurrent, with bilingual notices and source dates. Historical OOS research endpoints stay unchanged; old SHAP is hidden if its date differs from the displayed snapshot. No Free/Pro branching exists: both use the same market pointers.

Public `/api/data-health` reports sources, retrieval times, expected dates, last job and scheduler health. Protected `/api/admin/data-health` includes bounded job/attempt history and alert outbox summaries; the Admin Console exposes them read-only. Job records include job_id, market, start/end, status, provider/series attempts, latest date, error type/message and publication result.

Alerts persist to an outbox for refresh failures, stale inputs, absent snapshots, repeated failures and unusual moves. No emails/SMS are sent. A future delivery worker can fan out to all role=admin users and mark successful deliveries; no delivery credentials are configured.

Persist/back up `data/operations` (override: `MARKET_OPERATIONS_DIR`). This locking/SQLite design targets one host with a local persistent filesystem. Multiple hosts need a shared transactional database/distributed locks; SQLite over NFS is unsupported. Staging/job retention is currently unbounded: add an audited retention/backup policy before long-running paid deployment. Never delete a directory referenced by a current snapshot. Keep holiday calendars updated.

## Verification

`tests/test_market_operations.py` covers invalid observations, crash/spike acceptance, retry bounds, atomic rollback/idempotency, date-regression prevention, failure preservation, concurrent lock exclusion, no current fill, Korea gaps, incomplete features, holidays, scheduler catch-up and per-source freshness. Tests use temporary storage, never production accounts. Live findings are in `data-reliability-live-verification.md`.

## Resume verification — 2026-10-14

Resumed commit `21b1852` on `wip/data-automation`; retained the existing operations architecture. The handoff's missing successful-job report, volatile snapshot identity, and indefinite DELAYED classification were confirmed in code and corrected. No financial calculation, feature specification, model weight, warning threshold or research result was changed.

Retrieval now runs through the latest closed exchange session, while freshness remains relative to a separately calculated due session. Thus newer available observations are retained even before their publication allowance expires. Each provider-validated series includes latest value, observation date, source, retrieval time, expected date and status; `used_observation_date` identifies the common inference date separately. Snapshot API fields explicitly separate `market_observation_date`, `data_retrieved_at` and `model_inference_at`. Legacy snapshots expose unknown inference time as null.

Expected dates use XNYS/XKRX with the existing close+12h / close+6h allowances. DGS10 rolls the due date back over Board federal holidays using the federal business-day calendar: H.15 does not publish on Board holidays. DBAA conservatively retains the NYSE due date; Moody's independent publication SLA/holiday contract is not configured. This can conservatively report DELAYED during a legitimate Moody's holiday; it never certifies unknown freshness as CURRENT. Provider contracts and allowance policy still need operator review before launch. Sources: [H.15](https://www.federalreserve.gov/releases/h15/), [Board holiday calendar](https://www.federalreserve.gov/aboutthefed/k8.htm), [FRED DBAA](https://fred.stlouisfed.org/series/DBAA).

Overall status rules, in precedence order:

1. No committed valid snapshot: ERROR and latest API returns 503.
2. Latest refresh failed: PARTIAL when some required channels succeeded and others failed; otherwise ERROR. A calculation/inference failure after all channels succeed is ERROR. The committed snapshot stays available and `is_current=false`.
3. CURRENT requires provider-validated provenance, metadata for every required series, known retrieval timestamps, every source at its independently expected date, and a common inference date at least the minimum of those expected dates.
4. DELAYED means a successful refresh for the currently expected session retrieved all required channels but one or more remain behind. It is never current. A required input more than five due exchange sessions behind is rejected, retaining Last Known Good; five sessions is an operational safety policy, not a model parameter.
5. STALE means the retained snapshot cannot establish current coverage and there has been no successful refresh for the current expected session, or provenance/required metadata are incomplete. A previous successful job cannot keep a snapshot DELAYED indefinitely as new sessions become due.

The immutable snapshot retains its original retrieval/inference timestamps on duplicate content; the latest successful refresh's retrieval results remain in the durable job report and `latest_attempt_series`. Identical data/results reuse the committed snapshot even when job IDs, retrieval times or staging paths differ. Source-history SHA256 preserves revision identity. Same-date actual source revisions remain auditable versions. Successful publication and its complete series report commit together. Outbox failure after commit is recorded as `alert_error_type` and cannot relabel a published job ERROR.

Scheduler polls and startup checks distinguish missed sessions from failed attempts, retry failures/delayed coverage after 30 minutes, and retry a failed latest job even if Last Known Good still covers the due session. Manual refresh does not manufacture scheduler heartbeat. Concurrent same-market jobs exit ALREADY_RUNNING; markets have independent locks. Publication requires a ledger job belonging to that market. API/admin tests cover metadata, public health, and unauthenticated admin-health rejection; admin authentication finalization remains a separate task.

Added the previously missing API/frontend Dockerfiles, minimal build contexts and Compose restart policies. The scheduler runs inside the enabled server API lifecycle, independently of a client browser/editor/laptop. Docker Desktop integration is unavailable in this WSL environment, so image build and continuously deployed scheduling are **not verified**. A reachable persistent deployment and external watchdog remain required. No production service was deployed or enabled during review.

Frontend source review confirms Overview, U.S., Korea and Compare consume health, suppress noncurrent live classifications, retain distinct market dates, and display non-alarming notices. Current snapshots now also show explicit CURRENT and Data through labels; the comparison table exposes each market's data status. Admin health remains read-only. Paper execution quotes still use their separate quote service/timestamps. TypeScript and the production Next.js build passed; interactive browser checks were unavailable.

The final tests include real staged feature/inference failure injection, both-market lifecycle and failure matrices, severe stale rejection, bounded transient retries, permanent schema failures, transactional rollback, duplicate prevention, real refresh collision, independent locks, interrupted job recovery, scheduler background execution/catch-up/retry, exchange holidays, Treasury holidays, weekends, explicit timezone/DST behavior, API freshness and existing Paper/Admin regressions. The environment smoke test that fits a dummy model is deliberately excluded; no training is invoked. Live provider results and timestamps are in `data-reliability-live-verification.md`.
