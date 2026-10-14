# Staging implementation and verification — 2026-10-14

**Verdict: NOT READY for AWS EC2 staging deployment yet.** Source/configuration blockers are implemented and non-container integration checks pass. Actual Docker image builds and Compose startup could not run because this WSL environment has no Docker daemon/socket. Container recreation, EC2 mount/reboot recovery and next-day unattended provider access therefore remain release gates. No AWS deployment, domain purchase/configuration, commit or push occurred.

## 1. Blockers fixed

- Browser market requests use same-origin paths; no client-side localhost API fallback remains. Local development has server-side market rewrites. Workspace origin/JSON/CSRF/session/admin checks remain in the Next/FastAPI path.
- Existing required Korean seeds, targets and public research caches have a controlled checksum-manifest export/restore strategy; no research was fabricated or regenerated. An actual existing-data export completed, approximately 21 MiB.
- Configurable persistent data/model roots. New snapshot artifact paths are relative; old absolute paths rebase safely without rewriting signed payloads or job history. Source-history checksum verification prevents silently consuming modified relocated files.
- Secret environment variants and private data backups are Git-ignored; safe example files remain trackable. Docker contexts exclude environment variants/private data.
- Staging startup fails closed for missing session secret/explicit HTTPS origins/persistent roots or disabled secure cookies. Development localhost behavior remains.
- Frozen models have read-only staging mounts and unchanged SHA256 values.
- Supported frontend framework/Node LTS, locked production dependency installs, non-development startup, non-root API/frontend, multi-stage frontend image, healthchecks.
- Separate staging Compose with health-aware startup, private application networking, no published application ports, restart policies and persistent EBS bind mounts that must already exist.
- Pinned Caddy single-origin HTTPS-ready proxy, with public market GET allowlist and protected workspace routing.
- One-worker API scheduler plus a process-lifetime volume lock, used by API and standalone scheduler CLI. Existing per-market locks remain.
- SQLite online backup and checksum-verified offline restore, with immutable snapshot artifacts and account/history state preserved.
- systemd application startup and a Docker-level EBS mount guard, documented startup catch-up/LKG/reboot/next-day checks.
- Existing `/health` plus frontend `/api/health` and existing `/api/data-health`/protected admin health distinguish liveness, scheduler heartbeat/execution, latest refresh attempts and source freshness.

## 2. Files changed by this implementation

Earlier automation/localization changes already present in the working tree were preserved. This task's source/configuration files:

| Group | Paths |
| --- | --- |
| Ignore/build/local Compose | `.gitignore`, `.dockerignore`, `Dockerfile.api`, `docker-compose.yml`, `frontend/.dockerignore`, `frontend/Dockerfile` |
| Dependency/runtime/config | `requirements-staging.in`, `requirements-staging.lock`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig.json`, `frontend/next.config.mjs`, `src/config.py`, `src/runtime.py` |
| Frontend compatibility/routing | `frontend/src/app/layout.tsx`, `frontend/src/app/api/workspace/[...path]/route.ts`, `frontend/src/app/api/health/route.ts`, `frontend/src/app/page.tsx`, `frontend/src/app/paper-trading/page.tsx`, `frontend/src/app/components/USValidationResearch.tsx`, `ValidationOverview.tsx`, `market-data.ts` |
| Persistent/secure operations | `src/api/main.py`, `src/paper/auth.py`, `src/paper/router.py`, `src/paper/store.py`, `src/operations/store.py`, `refresh.py`, `worker.py`, `scheduler.py`, `__main__.py` |
| Staging deployment | `deploy/docker-compose.staging.yml`, `deploy/Caddyfile`, `deploy/staging.env.example`, `deploy/market-stress.service`, `deploy/docker-ebs.conf` |
| Backup/tests/docs | `scripts/staging_state.py`, `tests/test_staging_readiness.py`, `docs/aws-staging-readiness.md`, `docs/aws-ec2-staging.md`, this report |

`frontend/tsconfig.tsbuildinfo` was restored to its exact pre-task bytes. Unrelated experiments and `README.md.backup` were not edited. No Git staging command was used.

## 3–4. Versions before/after

| Component | Before | After |
| --- | --- | --- |
| Next.js | Locked 14.2.35, unsupported | Locked stable **16.4.0** |
| React / React DOM | 18.3.1 | 19.3.0 (framework compatibility) |
| Docker Node runtime | Node 20 Alpine, EOL | **22.23.3-bookworm-slim**, supported Node 22 LTS patch |
| Actual build/test Node | Host 22.22.1 originally | Verified isolated official Node **22.23.3** |
| Backend image Python | 3.11 untested resolver | **3.14.4-slim-bookworm**, matching verified local interpreter |
| XGBoost model runtime | Local XGBoost 3.4.1 | Locked CPU-only **3.4.1**, verified same frozen inference |
| Reverse proxy | None | Official **Caddy 2.11.7 Alpine** tag |

Official [Next.js support policy](https://nextjs.org/support-policy) lists 16 as Active LTS and 14 unsupported. [Next's version-16 guide](https://nextjs.org/docs/app/guides/upgrading/version-16) requires asynchronous request APIs and updated React/types: only those compatibility changes were applied. [Node's release index](https://nodejs.org/dist/index.json) identified 22.23.3 as the current Node 22 LTS patch; its official download checksum and image tag were verified. Caddy's [2.11.7 release](https://github.com/caddyserver/caddy/releases/tag/v2.11.7) and official image tag were verified. Base-image tags are pinned to versions, not immutable OCI digests; package installs use exact locks/hashes.

The production Python lock contains **49** exact transitive packages with artifact hashes for CPython 3.14/Linux x86_64. It excludes GPU/NCCL and training/plotting tools. A clean isolated install and `pip check` succeeded. Financial runtime versions remain pandas 3.0.6, NumPy 2.5.3, scikit-learn 1.9.1, XGBoost 3.4.1 and joblib 1.6.0.

## 5–8. Persistence, proxy, scheduler, backups

Data is EBS-backed under configurable `MARKET_DATA_ROOT`; staging maps the host data directory to `/app/data`. Both SQLite databases, all account/session/admin/paper records, operations pointers/ledger/LKG and source histories survive process recreation. Model root is configurable and mounted read-only. UID 10001 owns data; root owns the readable frozen models. TLS certificate state also resides on EBS. Preserve the stable external session secret for restored sessions.

Caddy publishes 80/443 only. Explicit public market GET routes go to FastAPI; `/api/workspace/*` goes through Next; other direct `/api/*` account/admin requests return 404. Pages/assets go to Next. A local test used an isolated Caddy CA without installing trust or changing a domain.

One API worker starts the existing scheduler when enabled; the persistent `scheduler.lock` rejects another API/standalone scheduler owner. Per-market refresh locks provide additional exclusion. Startup catch-up and existing calendars/retry/LKG behavior remain unchanged. Exactly one host/data volume is assumed; this is not a distributed scheduler.

Backups use SQLite's online API, close connections, convert backup DBs to standalone rollback-journal files, and copy immutable signed-snapshot directories plus seed/research artifacts. Restore verifies the manifest and refuses nonempty destinations; services must be stopped. A real approximately 99 MiB private state backup restored to a different root. No database history/payload migration was performed. Secret recovery and frozen model release artifacts remain separately protected.

## 9. Tests and exact results

| Check | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests -k 'not test_xgboost_smoke' -q` | **100 passed, 1 deselected, 1 warning in 23.69s**. The deselected test calls `fit` on a dummy XGBoost model; it was excluded to honor no training. Existing Starlette/httpx deprecation warning only. |
| Added staging invariants, also included above | **8 passed**: secure/fail-closed defaults, cookie configuration, relative/legacy path integrity, cross-process scheduler exclusion/release, configurable roots, committed WAL online backup/session restore, legacy snapshot-history restore, artifact allowlist/Korea target presence. |
| `npm run typecheck` on Node 22.23.3 | Exit **0**, no TypeScript errors. |
| `npm test` on Node 22.23.3 | Exit **0**; **812 bilingual messages**, catalog/static JSX/formula/parameter checks, all page rendering paths in both languages, populated comparison/validation values passed. Existing React missing-key warnings remain. |
| Production `npm run build` on Node 22.23.3 | Exit **0**, Next **16.4.0**, all **13 routes** compiled/generated; all existing pages/workspace route preserved and frontend health route added. |
| Clean lockfile install | `npm ci --ignore-scripts`: exit **0**, 104 installed packages, 0 reported vulnerabilities; production build also succeeded afterward. Actual Docker `npm ci` still awaits image verification. |
| Hashed Python production lock | Clean isolated install: exit **0**, 49 packages; `pip check`: **No broken requirements found**. |
| Frozen model loading | Both Pipelines load under the isolated CPU-only production stack; **17 input features each**. |
| Full staged U.S./Korea inference on relocated state | Exit **0** for both. MSI, stress threshold, Risk Score, warning/event booleans exactly match the existing committed snapshots; new relative artifact locations resolve under the relocated operations volume. |
| Fresh-clone delivery check | A separate clone of `21b1852` accepted the documented tracked-source patch and explicit new-file archive; imports came from that clone, all required deployment files existed under the restored persistent root, and both frozen models loaded with 17 features. |
| Real artifact export and restore | Exit **0**. Required Korea seeds/targets/research outputs and two models present; checksum-manifest restore to a fresh root succeeded. |
| Real state backup/restore | Exit **0** after fixing the discovered backup sidecar issue; old signed snapshots/history remain intact and relocated source seeds load. |
| Local production HTTPS integration | Exit **0** using Node 22.23.3 standalone `server.js` with the exact image-style file layout, pinned backend runtime and Caddy 2.11.7. All **12** tested health/market routes return 200; both language HTML values correct. Secure/HttpOnly/SameSite cookies, workspace origin rejection and direct account API 404 pass. Same account/session/CSRF data and both snapshot IDs persist after API process recreation. |
| Browser URL/secret scan | **1,397** JS/JSON/HTML/CSV files inspected across client assets, standalone output and artifact export; **0 configured-secret matches**, **0 browser localhost:8000/127.0.0.1:8000 matches**. Server-only local fallback remains for development. Image secret scan awaits actual builds. |
| Compose validation | Official checksum-verified Compose **5.6.0**, `config --quiet`: exit **0**, no interpolated configuration printed. |
| Caddy validation | Official checksum-verified Caddy **2.11.7**, `adapt --validate`: exit **0**. |
| Git/env safety | Required env variants/private backups ignored; safe templates trackable; `git diff --check` exit **0**; tsbuildinfo unchanged from task entry. |

No production models were trained, replaced or modified. No evaluation/validation research output was regenerated. Inference probes used copied state and isolated staged calculations.

## 10. Actual Docker build/start attempts

Both normal Docker Desktop-wrapper attempts and real isolated Docker CLI attempts were made. Outside the sandbox, the real **Docker CLI 28.5.1** attempted both Dockerfiles; both returned:

```text
Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?
```

The real Compose startup returned:

```text
failed to connect to the docker API at unix:///var/run/docker.sock;
dial unix /var/run/docker.sock: connect: no such file or directory
```

The default Docker Desktop wrapper also reported WSL integration unavailable. No image build completed and no container was started. This is an environment capability blocker, not an automatic approval rejection; no daemon was installed/started and no AWS resources were accessed. Compose/Caddy parsing and equivalent native runtime HTTPS/persistence tests passed, but they do not establish container image correctness.

## 11. Model checksums before/after

| Frozen artifact | Before SHA256 | After SHA256 |
| --- | --- | --- |
| `models/saved/xgboost_latest.joblib` | `90c51c245ebe62b58f804098a7a7045b60fb64ef83da72d4c9a049cf8d5eeb0d` | `90c51c245ebe62b58f804098a7a7045b60fb64ef83da72d4c9a049cf8d5eeb0d` |
| `models/korea/xgboost_10d_latest.joblib` | `42c3026386a58b25df337a431fbd5a793e93665a3d9a3f2cf22be4cfcc9186e3` | `42c3026386a58b25df337a431fbd5a793e93665a3d9a3f2cf22be4cfcc9186e3` |

## 12–13. Remaining blockers and readiness

1. Run both actual image builds and Compose startup on a working x86_64 Docker host. Verify non-root file ownership, read-only root/model mounts, container DNS/proxy behavior, image secret scan and DB/account/snapshot persistence across **container** recreation.
2. During a separately authorized EC2 deployment, provide the encrypted EBS mount/configuration, reviewed source and existing artifact bundle, stable session secret, approved hostname/TLS origin and working provider access. These were intentionally not provisioned/configured here.
3. Verify the Docker/systemd mount guard, EC2 reboot recovery and next-day unattended U.S./Korea provider refresh from the deployed egress address.

**NOT READY** until the Docker release gate passes. The [EC2 staging runbook](aws-ec2-staging.md) supplies exact resource/directory/configuration/build/admin/refresh/scheduler/HTTPS/backup/restore/reboot/next-day steps. Existing SQLite, research methodology, financial formulas/features/thresholds and bilingual UI design remain intact.
