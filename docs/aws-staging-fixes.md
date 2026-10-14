# AWS staging freshness / Korea refresh fixes — 2026-10-14

> **Source release:** use the committed `wip/data-automation` branch and [current pull/build/recreate procedure](aws-staging-release.md). Earlier source-archive instructions and no-commit statements below record the preceding implementation steps. Artifact exports remain separate from Git.

> **Follow-up:** AWS has now directly confirmed the target CSV is absent. The permanent image-backed/EBS initialization repair and revised artifact-delivery commands are in [Korea artifact deployment](korea-artifact-deployment.md). The earlier report below records the evidence available before that confirmation. Use the follow-up deployment configuration and approved artifact context for new builds.

## 1. Korea failure: evidence and cause

The failing command is `python -m src.operations.worker korea <persistent-stage-directory>`, launched by `refresh.py` with `capture_output=True`, timeout 180 seconds. With the existing real histories, omitting the research cache reproduces exactly **4,128 merged rows**, **60 warm-up rows**, **4,068 feature-ready rows**, then exit code **1** and `FileNotFoundError` for `processed/korea/korea_targets.csv`.

The existing feature builder writes the complete inference features first, then reads cached research targets to build a labeled training/evaluation matrix. The operational worker called that entire research path, even though prediction needs no future labels and its current MSI/threshold/event comes from the separately calculated staged MSI file. That unnecessary research-target dependency caused the reproduced failure.

**AWS's actual missing file has not been inspected directly.** Its supplied progress log matches the reproduction, but an absent/unreadable/malformed target cache cannot be distinguished definitively from that truncated log alone. If another failure remains after this release, the new diagnostic logs reveal its actual exception/exit code. No AWS resources were accessed or modified by this task.

Docker deliberately excludes `data` from images. Existing seeds/research and runtime state come from the EBS bind mount. Consequently a target cache can be absent if omitted from delivery or placed outside the mounted data root; rebuilding an image never creates it. We did not fabricate it or introduce a hardcoded host path. The corrected operational inference does not require it. The default research invocation still requires its original targets and performs its original labeled-matrix QA.

## 2. DELAYED → UNAVAILABLE: exact cause and corrected semantics

Overview masked scores with `latest.data_health.is_current ? score : null`. The shared `signal()` made the same freshness check; MarketDetail's assessment also depended on `is_current`. Meanwhile CrossMarketSnapshot formatted the raw score directly, so one page could show a number and another hide the same validated output. DataHealthNotice called every non-current snapshot “Current market risk unavailable.”

Backend `model_available` now describes whether the committed, integrity-checked snapshot carries finite model score/MSI with an in-range score. Existing `status`, `is_current`, calendars, provider lag, source gates, snapshot publication and LKG policy are unchanged. A failed refresh can coexist with an available valid LKG; `ERROR` freshness does not erase that output. No snapshot yields unavailable/503.

The frontend uses one shared availability guard independently of freshness, preserving the existing U.S. bands and Korea's own warning state/reference. CURRENT/DELAYED/STALE/PARTIAL/ERROR all retain valid snapshot outputs with the appropriate warning and observation date. Missing/invalid output remains UNAVAILABLE. Stale data is not relabeled CURRENT.

## 3–4. Modified files and changes

| File | Change |
| --- | --- |
| `src/korea/build_korea_features.py` | Optional `inference_only` return after existing observable feature generation; default research target join/QA unchanged. No feature formula/order changed. |
| `src/operations/worker.py` | Korea calls the inference-only path; existing feature/date/MSI/model/probability/checksum gates stay intact. |
| `src/operations/refresh.py` | Capture redacted stderr/stdout, return code, calculation tail; persist diagnostic logs and send only a safe generic ledger/UI summary. |
| `src/operations/service.py` | Add independent `model_available`; describe retained validated output accurately; omit internal job error text from public health. |
| `frontend/src/app/components/market-data.ts` | Shared model availability guard; signal no longer depends on freshness; existing classifications preserved. |
| `frontend/src/app/page.tsx` | Overview uses shared availability/signal rules; DELAYED score retained and no false offline classification. |
| `frontend/src/app/components/MarketDetail.tsx` | U.S./Korea score, MSI and assessment use availability, not `is_current`. |
| `frontend/src/app/components/CrossMarketSnapshot.tsx` | Snapshot and assessment displays share the same availability guard. Compare inherits this component. |
| `frontend/src/app/components/DataHealthNotice.tsx` | Separate delayed/stale/partial/failed-refresh warnings from missing model output; preserve observation date. |
| `frontend/src/app/i18n/en.json`, `ko.json` | Four natural bilingual freshness notices; existing messages/financial numbers untouched. |
| `frontend/tests/i18n.test.cjs` | All freshness states, invalid outputs, Overview/U.S./Korea/Compare rendering in both languages; independent Korea warning behavior. |
| `tests/test_market_operations.py` | Real Korea cache-independent inference/failure regression; diagnostic redaction, retained validation, delayed availability, no-snapshot behavior and public traceback exclusion. |
| This document | Evidence, exact checks, source delivery and AWS application commands. |

Korea's three source-file changes from the preceding repair were already in the working tree and are included in this release. Unrelated authentication, trading, admin, routing, Compose/Caddy settings, experiments, README backup and preexisting tsbuildinfo bytes were preserved. No commit or push occurred.

## 5–8. Verification

Both **real-provider** refreshes ran under the pinned production Python dependency stack, on a new isolated data root with the existing seeds/models and **without** `korea_targets.csv`.

| Market | Refresh | Published | Latest API | Date | Score | MSI | Threshold | Freshness | Model available |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| U.S. | SUCCESS | true | 200 | 2026-10-09 | 11.9 | -1.159 | 1.292 | DELAYED | true |
| Korea | SUCCESS | true | 200 | 2026-10-13 | 37.8 | 0.744 | 1.116 | CURRENT | true |

The U.S. validated output remains visible despite provider publication lag. Existing Korea output is reproduced without a research target cache. Neither production data root nor production snapshot history was overwritten by these probes.

- Backend: `.venv/bin/python -m pytest tests -k 'not test_xgboost_smoke' -q` → **106 passed, 1 deselected, 1 warning in 29.49s**. The deselected dummy test calls model `fit`; no training was run. Existing Starlette/httpx deprecation warning only.
- Frontend: `npm run typecheck` on Node 22.23.3 → exit 0.
- Frontend: `npm test` → exit 0, **816** bilingual messages plus all previous checks; new Overview/U.S./Korea/Compare tests pass for both languages. Existing React missing-key warnings remain.
- Production: `npm run build` → exit 0, Next 16.4.0, all **13 routes** retained.
- Additional diagnostic tests verify credential redaction in persisted stderr and logger output; traceback is absent from public health and generic worker failure summary.
- `git diff --check` passes; pre-task tsbuildinfo bytes restored.

The target-cache reproduction, full live refresh and HTTP API checks ran locally. This is not evidence that a new release has been applied to AWS. Actual Docker/AWS deployment was not performed here.

## 9–10. Frozen model / financial integrity

Both before/after SHA256 values are identical:

```text
U.S.   90c51c245ebe62b58f804098a7a7045b60fb64ef83da72d4c9a049cf8d5eeb0d
Korea  42c3026386a58b25df337a431fbd5a793e93665a3d9a3f2cf22be4cfcc9186e3
```

No model file, model definition, feature definition/order/formula, MSI calculation, threshold, SHAP semantics, historical performance or validation methodology changed. Korea does not receive U.S. risk bands. No research labels were fabricated, and inference validations were not weakened or disabled.

## 11. Additional artifacts

**No new financial/model artifact is required for this fix.** Keep the existing frozen models, actual raw source histories and public research outputs on EBS. `korea_targets.csv` remains useful for the default research builder and existing comprehensive artifact bundle, but it is no longer an operational inference prerequisite. Do not run training or research-generation scripts to repair refresh.

## 12. Exact source delivery and AWS application commands

These are commands for the later authorized AWS rollout; they were not executed against AWS. Use the existing `/opt/market-stress-early-warning`, `/etc/market-stress/staging.env` and `/srv/market-stress` layout. No credentials belong in this archive or shell arguments.

On the source machine, package only reviewed files:

```bash
tar -czf /tmp/aws-staging-fixes.tar.gz \
  src/korea/build_korea_features.py src/operations/worker.py \
  src/operations/refresh.py src/operations/service.py \
  frontend/src/app/components/market-data.ts \
  frontend/src/app/components/DataHealthNotice.tsx \
  frontend/src/app/components/MarketDetail.tsx \
  frontend/src/app/components/CrossMarketSnapshot.tsx \
  frontend/src/app/page.tsx frontend/src/app/i18n/en.json frontend/src/app/i18n/ko.json \
  frontend/tests/i18n.test.cjs tests/test_market_operations.py docs/aws-staging-fixes.md
sha256sum /tmp/aws-staging-fixes.tar.gz
```

Transfer the archive through the existing authenticated SSH/SSM delivery path to `/tmp/aws-staging-fixes.tar.gz`; verify the transfer SHA256. No models, datasets, environment files or unrelated files are packaged. The supplied paths assume AWS is running the reviewed staging source; inspect local edits before replacing these specific files.

On AWS, in a maintenance window:

```bash
set -e
cd /opt/market-stress-early-warning
stage_compose() {
  sudo docker compose --env-file /etc/market-stress/staging.env \
    -f /opt/market-stress-early-warning/deploy/docker-compose.staging.yml "$@"
}
STAGING_FIX_BACKUP_NAME="$(date -u +%Y%m%dT%H%M%SZ)-before-staging-fixes"
sudo python3 scripts/staging_state.py backup --data-root /srv/market-stress/data \
  --bundle "/srv/market-stress/backups/$STAGING_FIX_BACKUP_NAME"
# Save these source files separately for rollback before extraction.
sudo tar -czf "/srv/market-stress/backups/$STAGING_FIX_BACKUP_NAME-source.tar.gz" \
  src/korea/build_korea_features.py src/operations/worker.py \
  src/operations/refresh.py src/operations/service.py \
  frontend/src/app/components/market-data.ts frontend/src/app/components/DataHealthNotice.tsx \
  frontend/src/app/components/MarketDetail.tsx frontend/src/app/components/CrossMarketSnapshot.tsx \
  frontend/src/app/page.tsx frontend/src/app/i18n/en.json frontend/src/app/i18n/ko.json
# Verify archive contents/checksum and reviewed files before replacing source.
sudo tar -xzf /tmp/aws-staging-fixes.tar.gz
stage_compose config --quiet
stage_compose build api frontend
# Stop the embedded scheduler before the controlled one-off refresh.
stage_compose stop api
stage_compose run --rm --no-deps -e MARKET_REFRESH_ENABLED=false api \
  python -m src.operations refresh --market both
stage_compose up -d --wait --wait-timeout 360 api frontend
stage_compose exec -T api python -m src.operations health --market both
stage_compose exec -T api sha256sum \
  /app/models/saved/xgboost_latest.joblib /app/models/korea/xgboost_10d_latest.joblib
curl --fail "$PUBLIC_ORIGIN/api/latest"
curl --fail "$PUBLIC_ORIGIN/api/korea/latest"
```

`PUBLIC_ORIGIN` is the existing HTTPS site origin. Retain the existing scheduler environment setting; no provider keys, origin, session secret, auth/trading settings or Caddy/DNS configuration changes are required. Frontend **must be rebuilt**, because restarting an old image cannot replace compiled score masking. A standalone refresh CLI does not start an embedded scheduler; stopping the existing API prevents overlap during the controlled refresh.

If controlled refresh fails, the command exits nonzero: investigate before continuing, preserve LKG and either restore the old reviewed source/images or correct the diagnosed issue. Obtain a bounded diagnostic tail from the persistent job directory (the diagnostic files redact configured credentials):

```bash
stage_compose run --rm --no-deps -e MARKET_REFRESH_ENABLED=false api python -c \
  "from src.operations.store import root,history; j=history('korea',1)[0]; p=root()/'staging'/j['job_id']/'worker.diagnostic.log'; print(p.read_text()[-8000:] if p.exists() else 'No worker diagnostic log for this job.')"
```

Normal public APIs/UI receive freshness and availability with a safe failure summary, never the worker traceback. Confirm Overview cards, U.S., Korea and Compare in both languages show **11.9**/MSI **-1.159** for a valid delayed U.S. snapshot, with a separate delayed warning and 2026-10-09 observation date. Confirm missing snapshot remains UNAVAILABLE. Do not relabel delayed/stale data as CURRENT or modify any financial threshold to force success.
