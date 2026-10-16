# Korea ingestion freshness and opt-in shadow alignment

This change follows the frozen V1/V2/WATCH/Acute-Shock/Trajectory studies. It changes active download bounds and adds diagnostics, not production models, warning thresholds, APIs, UI, deployment or cron.

## Active date audit

| Path | Before | Scope / after |
| --- | --- | --- |
| `download_krx_indices.py` | 2010-01-04 through hard-coded 2026-10-02; resume at maximum date+1 | Active raw ingestion: runtime completed XKRX session, explicit bounds; retry missing sessions without redownloading all successful later dates; retain partial checkpoints during backfill |
| `download_vkospi.py` | Same fixed end and tail-only resume | Same runtime/explicit controls and hole retry |
| `download_ecos_credit.py` | Fixed 20100104–20261002; outer-merge legs then align to existing KRX dates | Runtime/explicit bounds, original leg arithmetic, no fill; preserve unaligned source dates and retrieval receipts; empty/bounded responses do not erase existing data |
| `test_krx_api.py`, `test_vkospi_api.py` | Fixed 20261002 | Connectivity fixtures only, intentionally retained |
| `test_ecos_credit.py` | Fixed 20260921–20261002 | Connectivity fixture only, intentionally retained |
| `cli/fetch_korea_data.sh` | Dispatch only, no date arguments forwarded | Same commands, forwards ingestion options; keys remain private |
| `cli/batch_fetch_korea_data.sh` | Reporting always reads default raw directory | Same batch/lock/scheduler architecture; reports configured `MARKET_DATA_ROOT` |
| Research event windows/data artifacts | Frozen historical endpoints | Unchanged; fixed dates are not blindly replaced |
| `operations/calendar.py` / `refresh.py` | Own provider cutoff and common-date policy | Unchanged production path, separately diagnosed below |

Runtime defaults use Asia/Seoul and completed market sessions, not execution-host local date. Before the exchange-calendar close (normally15:30) the current session is excluded. Weekends/calendar holidays are skipped. Explicit future/incomplete end dates are rejected. Calendar-library exceptional-closure coverage is imperfect: existing data have two older no-observation dates that the library lists as sessions. Empty API responses on such dates remain empty and are retried; no invented close is written. Do not infer a missing observation must be a network failure.

`--end-date`, `--start-date`, `--data-root`, or `KOREA_END_DATE`, `KOREA_START_DATE`, `MARKET_DATA_ROOT` preserve explicit historical requests. An existing newer checkpoint is not destructively truncated: use a separate root for a historical export. Source receipts distinguish provider responses from a local baseline first read now. No prior publication or system-possession timestamp is fabricated.

## Exact lag mechanism

1. ECOS outer merge retains October15 Treasury with null corporate yield. Same-date subtraction gives null spread. KRX calendar alignment retains that date if the KRX file already contains it; no forward-fill occurs. The unaligned source file and receipts now preserve dates even when the KRX calendar is older.
2. `build_korea_features.load_data()` inner-joins the equity, volatility and credit **date rows**. If credit has no October15 row, the date disappears at the second join. If the aligned credit file has an October15 row with a null spread, the date survives the joins but `main()` raises `Missing values found in Korea raw market channels` **before** feature-column `dropna`. Feature warm-up dropna must not be blamed for that failure.
3. `build_korea_stress_index.main()` likewise inner-joins date rows. A missing date disappears; a present null leg makes the corresponding raw/channel/MSI unavailable, not a valid newer MSI. The loader itself does not as-of-fill credit.
4. Actual operations `refresh.stage_inputs()` saves the full outer `source_history.csv`, finds the last row complete across all four inputs, and truncates inference inputs there. Thus with October15 equity/VKOSPI/Treasury and October14 corporate, it chooses October14. It rejects interior missing rows instead of dropping them and changing rolling windows. This behavior is deliberately unchanged.

## Separate comparison paths

`python -m src.korea.shadow_pipeline` is an opt-in research CLI, not a production API route or automatic batch step.

- **V1 common:** exact source dates, last complete row, no interior holes/imputation. Original17-feature builder, MSI builder and frozen artifact are reused. Metadata preserves the newest source dates, date actually used, cutoff, computation time and why the common origin is older.
- **Experimental AS-OF:** KOSPI200 observations define the reference axis. Each other series joins backward independently. Default age caps are1 exchange session and4 calendar days, configurable data-age controls, not learned warning thresholds. The two spread legs retain separate dates. Rejected stale candidates remain visible but are not reported as actually used. No future observation/publication/retrieval evidence may enter a cutoff. The model was not trained for mixed-date inputs: scores are explicitly unvalidated counterfactual replays, never replacement V1 forecasts.
- **Availability:** known publication time remains nullable; actual retrieval proves possession only at that time. Strict mode requires receipt evidence by cutoff. Proxy mode must be explicitly enabled and is labeled. A local baseline read now establishes possession now, not years earlier.
- **Quality:** FRESH/PARTIALLY_STALE/STALE/INCOMPLETE are separate from UNKNOWN_AVAILABILITY or RETRIEVAL_VERIFIED. The forecast origin and newest market observation are separate fields. A stale/unchanged forecast cannot masquerade as a fresh horizon starting now.

The history is append-only SQLite outside production, with update/delete rejection triggers for forecast and attempt rows. Same cutoff/model/input/path retries reference one forecast and append attempt receipts. A new cutoff appends another forecast. Daily persistence keys use the origin, so retries and same-origin updates are not additional trading days. Trajectory analysis is explicitly NOT_EVALUATED here, not invented. Only existing10D output is replayed; unsupported1D/3D/5D outputs remain null. No WATCH state is created.

## Interpretation and limits

One-day-lag reproduction yields a V1 October14 origin with32.3 Risk Score and .720 MSI. The mixed-leg October15 replay can yield a different score/experimental composite even though the underlying model is unchanged. Holding corporate yield constant while using a newer Treasury yield can **artificially widen the spread**. Newer equity coverage does not establish superior predictions.

The completed current API capture has actual October15 observations for all sources. That observation-date replay yields approximately40.5 and1.049, and exact/AS-OF inputs coincide. These are computations after the event, not proof of pre-event predictions. Prior October15 acute-shock failure conclusions are not overturned. Without source publication vintages and past model releases, historical false-alarm or lead-time gains cannot be certified; replaying today's frozen artifact over its training history would be look-ahead. No such claims are made.

## Validation and scheduler gate

Run focused tests and existing market-operation tests; use an isolated raw-history copy for initial `cli/fetch_korea_data.sh test` and `all`, then compare actual dates and missing legs. HTTP200 and exit0 alone are insufficient freshness checks. Back up existing raw files before the authorized workspace ingestion.

Do not install cron here. Before `cli/schedule_batch.sh install`, review one-time batch paths/locks/logs, confirm all latest observed dates against publisher availability, review retained gaps and API limits, retain raw receipts, and require tests plus operator acceptance. Scheduling collection does not deploy shadow inference or publish production forecasts. Production feature-age semantics require separate validation before any change.

Input/source-axis metadata and successful feature/MSI artifacts are additionally archived under content-addressed `artifacts/<input_sha256>/` directories; conflicting writes fail. Forecast history references these hashes. Later working CSVs may change, but issued input snapshots are not replaced. Exact historical reproduction requires these archived vintages, not only an end-date parameter.
