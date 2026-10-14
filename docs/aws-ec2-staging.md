# EC2 private staging procedure

Prepared 2026-10-14 against the blockers in [the readiness audit](aws-staging-readiness.md). **Do not deploy until the Docker build/start/recreation gate below passes.** The staging preparation did not provision AWS resources or configure a domain. Reviewed source is delivered on `wip/data-automation`; use [the release procedure](aws-staging-release.md) for an existing AWS host. The implementation uses one host and SQLite; it does not change financial calculations or research artifacts.

## Resources and directories

Use one **x86_64** EC2 instance, a supported Linux distribution with systemd, Docker Engine and the Compose plugin. A private pilot may use 2 vCPU/2 GiB with images built elsewhere; use at least 4 GiB if building both images on EC2, and measure refresh memory before reducing capacity. Use an encrypted 30 GiB root volume and an encrypted, independently persistent 20 GiB data EBS volume, with expansion/backup monitoring. Use an instance role for Systems Manager; restrict inbound access to intended testers. Only proxy ports 80/443 are public; 3000/8000 have no staging host bindings. Outbound HTTPS/DNS/time sync must work for providers, registries and certificate renewal. Keep one host/one Compose project; do not scale the API service.

Paths:

| Path | Purpose/owner |
| --- | --- |
| `/opt/market-stress-early-warning` | Reviewed application source; no secret env files |
| `/etc/market-stress/staging.env` | Root-owned mode 0600 configuration; outside Git and images |
| `/srv/market-stress` | Encrypted EBS mount, not an ordinary root-volume directory |
| `/srv/market-stress/data` | UID/GID 10001:10001; account DB, operations DB, immutable job artifacts, seeds/research |
| `/srv/market-stress/models` | Root-owned frozen artifacts; readable by API UID, mounted read-only |
| `/srv/market-stress/caddy/data`, `caddy/config` | Caddy certificate/config state, persistent and private |
| `/srv/market-stress/backups` | Mode 0700 private application backups; also copy off-instance to encrypted storage |

Identify the data device using `lsblk -f`. Format **only a confirmed new empty EBS device**; do not format a restored volume. Mount it at `/srv/market-stress`, add its UUID to `/etc/fstab`, and verify `mountpoint /srv/market-stress`. A `nofail` mount may allow host diagnostics if the disk is unavailable; Docker's mount guard must still prevent application startup on the root volume. The supplied systemd files assume this mount and source path; change both files together if choosing different paths.

## Deliver the reviewed source and existing artifacts

Use the reviewed `wip/data-automation` source release from the existing Git repository. Git contains application source, deployment scripts and tests, not private environment files or the generated artifact archive. Source delivery does not replace the separately controlled persistent/deployment artifacts.

On the source machine, export the existing approved artifacts to a new destination:

```bash
python3 scripts/staging_state.py artifacts --data-root data --models-root models \
  --bundle /tmp/market-stress-artifacts
```

Transfer the artifact directory through an authenticated private channel. The artifact export is an allowlist of existing CSV/JSON files under `raw`, `processed`, `features`, plus the two frozen model files and SHA256 manifest. It excludes environment files, accounts, sessions, operations DBs and logs. It does **not** retrain or regenerate research. Keep the reviewed manifest with the release; hash checks detect transfer corruption, not a maliciously replaced manifest.

Required Korea refresh inputs are `raw/korea/krx_indices.csv`, `vkospi.csv`, and `ecos_credit.csv`. `processed/korea/korea_targets.csv` is the approved static research artifact for the default labeled feature builder. Operational inference no longer needs its future labels; staging now independently guarantees this release artifact exists through the image-backed initialization below. U.S. bootstrap requires `raw/raw_market_data.csv`. Public research routes additionally need existing U.S. OOS/multi-horizon/SHAP and Korea OOS/evaluation/SHAP outputs. `scripts/staging_state.py:REQUIRED` checks these exact files, including `oos_predictions_10d.csv`. The bundle carries remaining existing CSV/JSON research/cache artifacts unchanged. No research-generation command is part of deployment.

On the staging host, with `REPOSITORY_URL` identifying the existing repository:

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /opt/market-stress-early-warning
git clone --branch wip/data-automation "$REPOSITORY_URL" /opt/market-stress-early-warning
cd /opt/market-stress-early-warning
git pull --ff-only origin wip/data-automation
sudo mountpoint -q /srv/market-stress
# Keep the approved export as a separate release build context, outside live data.
sudo test ! -e /srv/market-stress/release-artifacts
sudo cp -a /tmp/market-stress-artifacts /srv/market-stress/release-artifacts
sudo python3 scripts/staging_state.py restore --offline \
  --data-root /srv/market-stress/data --models-root /srv/market-stress/models \
  --bundle /tmp/market-stress-artifacts
sudo chown -R 10001:10001 /srv/market-stress/data
sudo chmod -R u+rwX,go-rwx /srv/market-stress/data
sudo chown -R root:root /srv/market-stress/models
sudo find /srv/market-stress/models -type d -exec chmod 0755 {} +
sudo find /srv/market-stress/models -type f -exec chmod 0444 {} +
sudo install -d -m 0700 /srv/market-stress/caddy/data /srv/market-stress/caddy/config /srv/market-stress/backups
sudo install -d -m 0700 /etc/market-stress
sudo install -m 0600 deploy/staging.env.example /etc/market-stress/staging.env
sudoedit /etc/market-stress/staging.env
```

Restore requires empty destinations and verifies every manifest file before copying. To migrate existing private accounts/history, use the separate **backup** procedure, not the public-artifact export. Existing signed snapshot payloads and job records are not rewritten. Legacy `.../staging/<job-id>` absolute references resolve to the matching directory beneath the new operations root; new snapshots store `staging/<job-id>`. Source-history hashes are checked before using relocated seeds. The backup preserves all committed snapshot directories, not only the latest pointer.

## Automatic static artifact initialization

Set `STAGING_ARTIFACT_BUNDLE` in the private staging env file to the approved export directory (`/srv/market-stress/release-artifacts`). It is a **build-time** source, separate from mutable EBS application state. Compose selects the `staging` Dockerfile target and passes this named BuildKit context. Only its manifest and existing Korea target CSV are copied into the image at `/opt/market-stress/artifacts`; no models, accounts or secrets are baked into the image. The build verifies the target checksum and fails if the approved source is missing/corrupt. [Docker's named build-context specification](https://docs.docker.com/reference/compose-file/build/#additional_contexts) requires Compose 2.17+ and a compatible BuildKit/Buildx builder.

The staging entrypoint executes `deploy/init_artifacts.py` before Uvicorn or a one-off refresh CLI. It verifies the immutable image seed, locks the mounted data root, copies only a **missing** target atomically to `MARKET_DATA_ROOT/processed/korea/korea_targets.csv`, fsyncs it and its directory, then executes the requested command. The bind mount cannot hide the seed because `/opt` is outside `/app/data`. An existing matching file is left byte-for-byte intact; an existing different/corrupt file is never overwritten and stops startup for operator review. No target/label generation or financial calculation occurs.

EBS keeps the file through container recreation and reboot. Every new process checks it again; if it was deleted, the retained image seed restores it before the API/scheduler begins. Existing EBS mount guards still prevent startup on a missing disk. The bundle need only be available for a new image build, not every reboot. Retain the approved release bundle for reproducible rebuilds. Local development Compose explicitly selects the unchanged `runtime` stage and needs no artifact build context. Raw `docker build` for development must use `--target runtime`.

## Configuration names and secrets

External host configuration names are `STAGING_ARTIFACT_BUNDLE`, `STAGING_ROOT`, `SITE_ADDRESS`, `PAPER_ALLOWED_ORIGINS`, `PAPER_SESSION_SECRET`, `FRED_API_KEY`, `KRX_API_KEY`, `ECOS_API_KEY`, `MARKET_REFRESH_ENABLED`. Populate provider keys through the private root-owned file or an instance-role secret delivery mechanism. Never put keys/passwords in shell arguments, source patches, images, browser variables, tickets or copied command output. Do not print `docker compose config`; use `config --quiet`.

Generate and retain a stable `PAPER_SESSION_SECRET` of at least 32 characters through a secure secret-management/editor workflow. Preserve it when restoring accounts: existing session HMACs depend on it. Rotation intentionally invalidates old sessions. Avoid automatic admin/password environment bootstrap; use the interactive CLI below.

Compose sets `APP_ENV`, `MARKET_DATA_ROOT`, `MARKET_MODELS_ROOT`, `MARKET_OPERATIONS_DIR`, `PAPER_DB_PATH`, `PAPER_COOKIE_SECURE`, `API_INTERNAL_URL`. Staging defaults to secure cookies and fails startup if the session secret, explicit HTTPS origins or persistent roots are missing. Development retains localhost origins and non-secure cookies. `NEXT_PUBLIC_API_URL` is no longer used; browser market requests are relative `/api/...` paths.

`PAPER_STARTING_USD`, `PAPER_STARTING_KRW`, `PAPER_MAX_PRICE_AGE_DAYS`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_BOOTSTRAP_PROMOTE_EXISTING` remain existing optional application controls, unchanged; the staging Compose deliberately does not enable admin-password bootstrap or alter portfolio defaults. Do not introduce those variables to change financial behavior during deployment.

## Build, controlled bootstrap and scheduler activation

Define this helper in the deployment operator's shell:

```bash
stage_compose() {
  sudo docker compose --env-file /etc/market-stress/staging.env \
    -f /opt/market-stress-early-warning/deploy/docker-compose.staging.yml "$@"
}
cd /opt/market-stress-early-warning
sudo docker buildx version
# BuildKit and Compose 2.17+ named contexts are required.
stage_compose config --quiet
stage_compose build --pull api frontend
stage_compose up -d --wait --wait-timeout 360 api frontend
stage_compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').status)"
stage_compose exec api python -m src.admin.create_admin
stage_compose exec -T api python -m src.operations refresh --market both
stage_compose exec -T api python -m src.operations health --market both
stage_compose exec -T api python -m src.operations history --market both
stage_compose exec -T api sha256sum /app/models/saved/xgboost_latest.joblib /app/models/korea/xgboost_10d_latest.joblib
```

Initial `MARKET_REFRESH_ENABLED` is disabled in the template. Review each refresh result, source dates and required-artifact availability. A provider failure must keep Last Known Good; do not certify stale data as current. If provider credentials/egress are not ready, leave the scheduler disabled and diagnose the failed attempt. Never run `run_pipeline.py`, model-training or research-generation scripts.

After successful controlled refresh, enable `MARKET_REFRESH_ENABLED` through `sudoedit /etc/market-stress/staging.env`, then:

```bash
stage_compose up -d --force-recreate --wait --wait-timeout 360 api
stage_compose exec -T api python -m src.operations health --market both
```

Exactly one Uvicorn worker starts the embedded scheduler. A lifetime Linux `flock` at the persistent `operations/scheduler.lock` rejects another API scheduler or standalone `schedule` process on the same volume. Existing per-market locks also reject overlapping manual/scheduled refreshes. Do not run a second scheduler via cron, systemd, another Compose project or another data volume. Do not delete lock files while services are running. Lock ownership releases on normal thread exit or process death; a leftover filename does not hold a lock.

## Single public origin and HTTPS

The pinned Caddy proxy serves one hostname from `SITE_ADDRESS`, redirects HTTP to HTTPS and persists certificate state on EBS. `PAPER_ALLOWED_ORIGINS` must contain the exact corresponding HTTPS origin. Configure an existing/approved DNS hostname and EC2 ingress **only during the later authorized deployment**; no domain was purchased or configured by this task.

Routing order preserves `/api/workspace/*` on Next.js, including POST origin/content-type/body-size checks and FastAPI session/CSRF/admin authorization. Only the explicit GET market/health allowlist goes directly to FastAPI. Other direct `/api/*` requests return 404, including raw auth/admin/paper paths. All page/static routes go to Next.js. Browser requests remain on the public origin; Docker service names are server-only. Next's matching market rewrites preserve ordinary local development without Caddy.

When DNS, ingress and the HTTPS origin are ready:

```bash
stage_compose up -d --wait --wait-timeout 360
stage_compose ps
curl --fail "$PUBLIC_ORIGIN/health"
curl --fail "$PUBLIC_ORIGIN/api/health"
curl --fail "$PUBLIC_ORIGIN/api/data-health"
```

Set `PUBLIC_ORIGIN` locally to the chosen HTTPS site origin; never use an academy-computer IP. Check browser login/register, HttpOnly/Secure/SameSite session cookies, both languages, both market pages, validation and admin access. Verify ports 3000/8000 are absent from published bindings. Do not use `curl -k` for the deployed site's certificate check.

## Backup and restore

The application-state script uses SQLite's **online backup API**, closes connections and converts the backup to standalone rollback-journal databases. It never copies an active SQLite DB/WAL/SHM set. Account and operations databases are independently transaction-consistent; their domains have no cross-database transaction. Immutable directories referenced by every committed operations snapshot are copied with the research/seed CSV/JSON data and a SHA256 manifest. Private backups contain password hashes, sessions and portfolio history: mode 0700 directories/0600 files, encrypted EBS and encrypted off-instance retention are required. Bundle paths must be unique; incomplete exports must not be treated as successful backups.

```bash
# BACKUP_NAME is a unique timestamp/name, not a reused directory.
stage_compose exec -T api python scripts/staging_state.py backup \
  --data-root /app/data --bundle "/app/data/backups/$BACKUP_NAME"
```

That command runs as the application UID and produces a hot backup on the same EBS mount. Alternatively, the host command below stores backups outside `data`:

```bash
sudo python3 scripts/staging_state.py backup --data-root /srv/market-stress/data \
  --bundle "/srv/market-stress/backups/$BACKUP_NAME"
```

Schedule that host command daily with a unique timestamp through your existing operations tooling; check its exit status. Keep a short explicit retention policy and copy verified bundles off-instance. Check `df -h /srv/market-stress` daily; immutable operations history is retained and requires measured disk capacity, with no automatic history deletion. Periodically restore to an empty isolated directory and run `PRAGMA quick_check` on both DBs. Models are frozen and retained separately in the verified release artifact bundle; environment/session-secret and Caddy certificate recovery are separate private host/secret-store backups. Application backups never export provider/session secrets.

Restore only while **all** application services using the target volume are stopped:

```bash
stage_compose stop
sudo mv /srv/market-stress/data /srv/market-stress/data.before-restore
sudo python3 scripts/staging_state.py restore --offline \
  --data-root /srv/market-stress/data --bundle "$BACKUP_BUNDLE"
sudo chown -R 10001:10001 /srv/market-stress/data
sudo chmod -R u+rwX,go-rwx /srv/market-stress/data
stage_compose up -d --wait --wait-timeout 360
stage_compose exec -T api python -m src.operations health --market both
```

Keep the old directory until the restored account/session/portfolio/admin records and snapshot/job history are checked. Keep the same model artifacts and stable session secret. For a fresh recovery host, restore the artifact model bundle separately, then the private application-state backup; do not overwrite a nonempty live directory. Never restore only one raw DB file over an active WAL database.

## Reboot recovery and unattended next-day checks

Install the mount guard on the dedicated staging host. Without the Docker guard, `restart: unless-stopped` could restart old containers before the application systemd unit checks EBS:

```bash
sudo install -d /etc/systemd/system/docker.service.d
sudo install -m 0644 deploy/docker-ebs.conf /etc/systemd/system/docker.service.d/market-stress-ebs.conf
sudo install -m 0644 deploy/market-stress.service /etc/systemd/system/market-stress.service
sudo systemctl daemon-reload
sudo systemctl enable docker.service market-stress.service
# Activate/restart during the later authorized staging maintenance window.
sudo systemctl start market-stress.service
```

Docker waits for the EBS mount and refuses startup if `mountpoint` fails. Compose checks bind-source existence, uses health-aware dependencies and restart policies. Do not use `down -v` as a recovery shortcut. Containers can be recreated without losing accounts/sessions/positions/orders/admin activity, operations DB/LKG/job ledger or source histories. The runtime data is outside image layers; frozen models are a read-only bind mount.

A restarted scheduler immediately evaluates both exchanges, then polls each minute. Existing calendars, provider deadlines, retry cadence and Last Known Good behavior remain unchanged. A missed run catches up; interrupted RUNNING ledger jobs become recorded failures before the next attempt. No fabricated prices, observation dates or stale CURRENT labels are introduced.

After backing up and during a scheduled recovery test:

```bash
stage_compose up -d --force-recreate --wait --wait-timeout 360
# Check the same existing login/session, portfolios, orders, admin activity and snapshot IDs.
sudo reboot
```

Reconnect, verify `mountpoint`, `systemctl status docker market-stress`, `stage_compose ps`, both liveness endpoints and `/api/data-health`. Verify only one scheduler owns the volume, recent heartbeats and retained records. Simulate provider failure only in a separate test environment; production must retain LKG rather than clear valid state.

On the following unattended trading day inspect `/api/data-health` and protected `/api/workspace/admin/data-health`: `scheduler.heartbeat_fresh`, `heartbeat_at`, `last_run_at`, `last_run_expected_date`, expected dates/deadlines, `last_job.started_at/finished_at/status`, each input's latest observation/retrieval dates and freshness status, LKG/snapshot ID. `/health` means API alive; `/api/health` means frontend alive. A 200 from `/api/data-health` does not guarantee CURRENT or a healthy scheduler. Investigate MISSED, stale heartbeat, repeated ERROR/PARTIAL and unexpected source lag; legitimate provider delay must remain visible.

## Mandatory remaining release gate

On a working Docker host, perform both real image builds, Compose startup, read-only model checks, full HTTPS workspace routing and container recreation with retained SQLite state. Then perform the EC2 reboot and next-day checks above during authorized deployment. Current local non-container tests pass, but this environment has no Docker daemon: **do not describe Docker image contents, startup or container persistence as verified.** See [the exact verification report](aws-staging-verification.md).
