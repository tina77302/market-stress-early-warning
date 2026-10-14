# Reviewed staging source release

Includes Korea's verified image-backed artifact installation, cache-independent operational inference, safe worker diagnostics, independent model availability/freshness, bilingual UI regressions, and the staging tmpfs YAML fix. Source branch: **wip/data-automation**; main is not merged.

Final local checks: **111 backend tests passed**, one dummy model-training test excluded; TypeScript, 816 bilingual messages/page fixtures, production Next build (13 routes), Compose parsing and model hashes pass. Existing Starlette/httpx and React missing-key warnings remain. Actual local Docker builds/container reboot checks remain unavailable because the environment lacks Buildx/daemon. Do not treat source verification as completed AWS runtime verification.

The old YAML `tmpfs: [/tmp:size=128m,mode=1777]` normalized to two mount strings. Both API/frontend now use `tmpfs: ["/tmp:size=128m,mode=1777"]`, validated as exactly one mount string per service.

## AWS prerequisites

Use the existing encrypted EBS mount and root-owned staging env file. Deliver the approved artifact export via the existing authenticated transfer path; do not commit it. `STAGING_ARTIFACT_BUNDLE` must identify that export directory, containing `manifest.json` and `data/processed/korea/korea_targets.csv`. Set the variable with `sudoedit /etc/market-stress/staging.env` if missing. The file inside live `/app/data` is installed automatically by the new API image, not through a manual container copy. See [artifact delivery](korea-artifact-deployment.md).

Use BuildKit/Buildx and Compose with named-context support. Run the following in a maintenance window. Check `git status` first. The reported AWS-only Compose quotation change can be safely preserved in a **path-specific stash** before pulling; do not restore that old file over the released Compose file, which contains the fix and the new artifact build context. If there are other server edits, review/preserve them before proceeding; never use `reset --hard`, force pull or stash unrelated state blindly.

```bash
set -e
cd /opt/market-stress-early-warning
test "$(git branch --show-current)" = wip/data-automation
git status --short
git diff -- deploy/docker-compose.staging.yml
# If this file contains only the reported temporary quotation fix:
git stash push -m 'aws-compose-before-reviewed-release' -- deploy/docker-compose.staging.yml
git pull --ff-only origin wip/data-automation
git log -1 --oneline

sudo mountpoint -q /srv/market-stress
sudo docker buildx version
sudo docker compose version
stage_compose() {
  sudo docker compose --env-file /etc/market-stress/staging.env \
    -f /opt/market-stress-early-warning/deploy/docker-compose.staging.yml "$@"
}
STAGING_RELEASE_BACKUP="$(date -u +%Y%m%dT%H%M%SZ)-before-reviewed-release"
sudo python3 scripts/staging_state.py backup --data-root /srv/market-stress/data \
  --bundle "/srv/market-stress/backups/$STAGING_RELEASE_BACKUP"
stage_compose config --quiet
stage_compose build api frontend
stage_compose up -d --force-recreate --wait --wait-timeout 360 api frontend
stage_compose exec -T api sha256sum \
  /app/data/processed/korea/korea_targets.csv \
  /app/models/saved/xgboost_latest.joblib /app/models/korea/xgboost_10d_latest.joblib
# Pause the existing embedded scheduler for controlled provider refresh.
stage_compose stop api
stage_compose run --rm --no-deps -e MARKET_REFRESH_ENABLED=false api \
  python -m src.operations refresh --market both
stage_compose up -d --wait --wait-timeout 360 api frontend
stage_compose exec -T api python -m src.operations health --market both
curl --fail "$PUBLIC_ORIGIN/api/latest"
curl --fail "$PUBLIC_ORIGIN/api/korea/latest"
```

`PUBLIC_ORIGIN` is the existing HTTPS origin. No domain/Caddy/auth/trading configuration changes are required. No secrets are printed by `config --quiet`. Do not continue after a failed build/refresh; diagnose or roll back through the existing maintenance procedure while retaining LKG and EBS records. Frontend must be rebuilt, not merely restarted.

Verify both actual latest APIs, delayed U.S. score visibility with a separate freshness warning, both UI languages, target presence after a second recreation, and the same target/models after the authorized EC2 reboot check. Preserve any path-specific stash for review; the old temporary tmpfs change is already incorporated and should not be popped over the release.

Frozen model SHA256 values:

```text
U.S.   90c51c245ebe62b58f804098a7a7045b60fb64ef83da72d4c9a049cf8d5eeb0d
Korea  42c3026386a58b25df337a431fbd5a793e93665a3d9a3f2cf22be4cfcc9186e3
```

The release includes no models, raw/generated data, databases, real environment files, archives, experiments, README backup, tsbuildinfo, node_modules or .next files. Safe `deploy/staging.env.example` is included; it contains empty credential placeholders and non-secret directory defaults only.
