# Staging data artifact initialization repair — 2026-10-14

## Findings and API/file map

The deployed current U.S. card can work while historical/driver panels fail because they have separate storage dependencies. The current initializer delivered **only** Korea's target CSV. The approved export already contains historical, validation and SHAP files, but those files were not installed by that initializer. Git/Docker ignore `data`; rebuilding an ordinary source image does not place them into EBS. A bind mount at `/app/data` also hides anything placed at that path inside an image. `/health` is liveness, not proof that all research artifacts are available.

The actual U.S. latest route is **`/api/latest`**, not `/api/us/latest` (which is unregistered and returns 404). There are no route/financial changes in this repair.

| Endpoint/use | Persistent dependency relative to `MARKET_DATA_ROOT` |
| --- | --- |
| `/api/latest`, `/api/korea/latest` | `operations/refresh.sqlite3`: integrity-checked committed snapshot and current pointer; the initializer must not invent/copy in a new current snapshot |
| `/api/historical` and U.S. chart | `processed/oos_predictions.csv` |
| `/api/validation` | `processed/oos_predictions_10d.csv` |
| `/api/multi-horizon-validation` | `processed/multi_horizon_metrics.csv` |
| `/api/shap` | `features/shap/latest_shap.json` |
| `/api/korea/historical` | `processed/korea/korea_oos_predictions_10d.csv` |
| `/api/korea/validation` | `processed/korea/korea_model_evaluation_10d.csv` |
| `/api/korea/shap` | `processed/korea/shap/latest_shap.json` |
| U.S. bootstrap/source history | `raw/raw_market_data.csv`, or committed per-job source history resolved through the operations ledger |
| Korea bootstrap/source history | `raw/korea/krx_indices.csv`, `vkospi.csv`, `ecos_credit.csv`, or committed per-job source history |
| Korea default research builder | `processed/korea/korea_targets.csv`; operational worker already uses observable inference features only and does not need research labels |

U.S. inference reads **17 frozen-model inputs** built in its isolated job stage, not historical OOS predictions. Korea's worker builds staged features/MSI using real source histories and the unchanged frozen model; no additional external processed file is required by the corrected worker. `latest_features.csv`/`market_stress_index.csv` and Korea cached feature/MSI loaders are redirected to the job stage for operational inference. Model files remain `/app/models/saved/xgboost_latest.joblib` and `/app/models/korea/xgboost_10d_latest.joblib` on a read-only mount. SQL state and stage histories are never static image seeds.

AWS file presence beyond the supplied symptoms has **not** been directly inspected from this workspace. The required files do exist in the local repo data and both inspected approved exports. The definitive structural fault is that the previous image/initializer delivered one file instead of the approved API dependencies. Server-only differences/permissions should be assessed using the inventory command below, not assumed away.

## SHAP is a separate, confirmed date limitation

Inspected `data/` including Git-ignored files and the two existing approved exports (`market-stress-release-artifacts`, `market-stress-staging-artifacts`). The only endpoint-ready SHAP JSON dates are **U.S. 2026-10-05** and **Korea 2026-10-02**, each with eight top drivers. Latest validated snapshot dates are **2026-10-09** and **2026-10-13**. Associated latest/global SHAP CSVs have 17 rows and no observation-date column; they are not an alternative matching-date JSON explanation. No matching-date approved JSON was found in these inspected sources.

`useMarket` and Overview intentionally require `shap.date === latest.last_updated`. `/us` Equity/Volatility/Credit detail states summarize SHAP contributions, not the availability of SPY/VIX/credit quote values. Therefore:

- Installing existing approved files repairs the SHAP API's missing-file case and makes the historical/validation APIs available.
- It **does not** make the 10/05 explanation a valid driver of a 10/09 output. Current driver/channel panels may still show unavailable until a separately approved matching-date artifact exists.
- No SHAP/model output was generated, recomputed or relabeled. Existing date alignment and DELAYED/model availability guards were not changed. Missing Korea current snapshot still requires a successful controlled refresh; static initialization does not fake availability.

## Deployment changes

- New `deploy/artifact_spec.json` is the shared list of twelve required data artifacts and the two external model filenames. Exporter and initializer read the same list, preventing delivery-list drift.
- `scripts/staging_state.py` uses that specification; existing approved bundle format, backup behavior and byte-preserving export remain.
- `Dockerfile.api` copies only the manifest and approved `raw`/`processed`/`features` bundle directories outside the mount, under `/opt/market-stress/artifacts/data`. No model weights, account DBs, operations DBs or credentials are baked into the image.
- Staging build verification explicitly runs as **root**. All `/opt/market-stress` directories become **0555** (read/traverse) and files **0444** (read). The image explicitly switches to **`USER 10001:10001` before ENTRYPOINT**.
- The initializer verifies **all twelve sources and existing destinations before any installation**. Matching files retain contents/mtime. A differing file, corrupt bundle, missing requirement or unsafe destination stops startup with its path named; nothing is silently overwritten. Missing files are copied atomically and fsynced under the existing volume lock.
- Compose explicitly starts one Uvicorn worker, retains quoted `/tmp` tmpfs and read-only model mounts, and sets **`MARKET_REFRESH_ENABLED: 'false'`**, even if a host environment says true. Scheduler activation is outside this repair.

No `src` financial/model file or frontend rendering file changed in this task. The previous DELAYED ≠ UNAVAILABLE fix remains. Accounts/sessions/portfolio/admin/history/LKG are not seeded or replaced.

## Exact verification

- Backend suite: **113 passed, 1 dummy training test deselected, 1 existing Starlette/httpx warning in 30.11s**.
- Seven artifact tests cover shared dependency lists, all-file delivery, fresh-process reuse, partial deletion recovery, preflight conflicts, corrupt/missing SHAP/history sources, mount/symlink guards and preservation of the existing approved SHAP date.
- TypeScript: exit 0. Bilingual/availability UI tests: exit 0, 816 messages and Overview/U.S./Korea/Compare cases passed. Production frontend: Next 16.4.0, all 13 routes built. Existing React missing-key warnings remain.
- Actual native API integration under the pinned production dependency stack: twelve approved files seeded into isolated data root; repeated initialization changed no mtimes; both latest APIs, both historical APIs, both SHAP APIs, both validation APIs and multi-horizon validation all returned **200**. Full-history probes requested the same `days=10000` as the frontend and returned **5,057 U.S. rows / 2,454 Korea rows**, with successful JSON serialization; each SHAP returned eight drivers with its **original** date.
- Latest responses in that integration used a SQLite online copy of **pre-existing validated operations state**, not a newly generated model output. U.S. 11.9/MSI -1.159 retained; Korea 37.8/MSI 0.744 retained. This does not certify a fresh Korea snapshot on AWS, where controlled refresh remains pending.
- Compose normalization: explicit one-worker command, scheduler false even with host true, one quoted tmpfs entry, model mount read-only. Local development `runtime` target still validates.
- Actual image build attempted but unavailable: local Docker CLI lacks Buildx and a reachable daemon. Root-build/non-root-runtime/container recreation/reboot behavior must still be checked on AWS; no Docker success is claimed.

Model SHA256 values unchanged:

```text
U.S.   90c51c245ebe62b58f804098a7a7045b60fb64ef83da72d4c9a049cf8d5eeb0d
Korea  42c3026386a58b25df337a431fbd5a793e93665a3d9a3f2cf22be4cfcc9186e3
```

## Minimal AWS rollout

These reviewed changes are delivered on **wip/data-automation**. No merge into main or AWS deployment is part of this repair. Pull that branch after backing up any server-only deployment edits. No model/data/secret files are included in the source commit. Keep prior reviewed application fixes.

An existing full approved artifact export can be reused: the inspected exports already contain all twelve required paths. `STAGING_ARTIFACT_BUNDLE` must point to that **export root** with `manifest.json` and `data/`; it must not point to live application `data` or an individual target file. If a new export is needed, run the existing byte-copy export on the approved source, never training/SHAP-generation scripts:

```bash
python3 scripts/staging_state.py artifacts --data-root data --models-root models \
  --bundle /tmp/market-stress-full-release-artifacts
```

On AWS, update the source from the reviewed branch:

```bash
set -e
cd /opt/market-stress-early-warning
test "$(git branch --show-current)" = wip/data-automation
git status --short
# Back up existing source and EBS state before replacing reviewed deployment files.
STAGING_DATA_FIX_BACKUP="$(date -u +%Y%m%dT%H%M%SZ)-before-full-artifacts"
sudo tar -czf "/srv/market-stress/backups/$STAGING_DATA_FIX_BACKUP-source.tar.gz" \
  Dockerfile.api deploy/docker-compose.staging.yml deploy/init_artifacts.py scripts/staging_state.py
sudo python3 scripts/staging_state.py backup --data-root /srv/market-stress/data \
  --bundle "/srv/market-stress/backups/$STAGING_DATA_FIX_BACKUP"
git pull --ff-only origin wip/data-automation
sudoedit /etc/market-stress/staging.env
# Preserve MARKET_REFRESH_ENABLED=false; confirm STAGING_ARTIFACT_BUNDLE is the approved export root.
sudo mountpoint -q /srv/market-stress
sudo docker buildx version
stage_compose() {
  sudo docker compose --env-file /etc/market-stress/staging.env \
    -f /opt/market-stress-early-warning/deploy/docker-compose.staging.yml "$@"
}
stage_compose config --quiet
stage_compose build api
stage_compose stop api
# Required if prior temporary root-runtime changes created root-owned state.
# Ownership changes preserve bytes; keep database writers stopped during this step.
sudo chown -R 10001:10001 /srv/market-stress/data
stage_compose up -d --force-recreate --wait --wait-timeout 360 api
stage_compose exec -T api id
stage_compose exec -T api python -c \
  "from src.api.main import load_xgboost_model,load_korea_xgboost_model; print(load_xgboost_model().n_features_in_,load_korea_xgboost_model().n_features_in_)"
stage_compose exec -T api python -c \
  "import os; assert os.getenv('MARKET_REFRESH_ENABLED') == 'false'; from pathlib import Path; import json; r=Path('/app/data'); s=json.loads(Path('/app/deploy/artifact_spec.json').read_text()); print({p:(r/p).is_file() for p in s['required_data']})"
curl --fail "$PUBLIC_ORIGIN/api/historical?days=5"
curl --fail "$PUBLIC_ORIGIN/api/shap"
curl --fail "$PUBLIC_ORIGIN/api/korea/historical?days=5"
curl --fail "$PUBLIC_ORIGIN/api/korea/shap"
```

`PUBLIC_ORIGIN` is the existing HTTPS origin. Frontend source did not change, so the minimum AWS rollout rebuilds/recreates **API only**; its local production build was verified for regression. No Caddy/routing/auth/trading/model mount changes are required. If startup reports a checksum conflict, retain the existing data/backup and reconcile approved versions; do not force an overwrite or disable verification.

After artifact and permission checks, a controlled Korea refresh can run while keeping automatic scheduling disabled:

```bash
stage_compose exec -T api python -m src.operations refresh --market korea
curl --fail "$PUBLIC_ORIGIN/api/korea/latest"
```

Do not call `/api/us/latest`; use `/api/latest`. Do not publish/copy the local operations DB to fabricate a current Korea response. Successful controlled provider validation and publication are required. Matching-date SHAP must come from separately approved existing artifacts; this repair cannot manufacture it.
