# Korea static artifact delivery repair

> **Source release:** use the committed `wip/data-automation` branch and [current pull/build/recreate procedure](aws-staging-release.md). Earlier source-archive instructions and no-commit statements below record the preceding implementation steps. Artifact exports remain separate from Git.

## Confirmed cause

AWS reported `/app/data/processed/korea/korea_targets.csv` absent inside the API container. The old worker calls the full research feature builder: after 4,128 merged rows and 4,068 inference-ready rows it reads that target CSV and exits 1 with FileNotFoundError. The same input histories and missing-file condition reproduce the supplied AWS progress pattern.

The precise deployment omission mechanism is visible in source: the CSV is Git-ignored, root `.dockerignore` excludes `data`, the Dockerfile copies only runtime source and libraries, and Compose mounts the host EBS `data` directory over `/app/data`. Image rebuilds cannot supply a file absent from that directory. The former export/restore procedure checked targets only if used, but startup did not enforce delivery. **The host's exact transfer command/history was not provided, so which delivery step was skipped cannot be asserted.** Missing static artifact plus the old unnecessary research-target read explains the refresh failure; it is not a provider, model, MSI or threshold failure.

The previous inference-only repair remains: ordinary operational inference does not depend on future research labels, and all its actual validation gates remain. This follow-up independently guarantees the requested static artifact is delivered and retained rather than relying on an ad hoc copy.

## Corrected structure

1. Existing `scripts/staging_state.py artifacts` produces an approved public-data/model export with a SHA256 manifest, including the original target CSV. No file is regenerated.
2. `STAGING_ARTIFACT_BUNDLE` provides this export as a named build context. Staging builds fail if it is absent or the target checksum is wrong.
3. The staging image contains only the target CSV and manifest at `/opt/market-stress/artifacts`, outside the data mount. Frozen models continue to be external read-only mounts.
4. Before every API or one-off CLI startup, the non-root entrypoint checks/installs the approved target to persistent EBS. Installation is locked, atomic and fsynced. Existing matching contents are preserved; different contents are not overwritten.
5. Container recreation and server reboot reuse EBS and the image seed. A missing target is restored automatically; a missing EBS mount remains blocked by the existing host guards. No raw DBs or other live state are replaced.

Changed deployment files: `Dockerfile.api`, `docker-compose.yml` (development target selection only), `deploy/docker-compose.staging.yml`, `deploy/staging.env.example`, new `deploy/init_artifacts.py`, new `tests/test_deployment_artifacts.py`, and deployment documentation. **No Korea/U.S. model, feature, MSI, threshold or financial validation file was modified by this follow-up.** Earlier uncommitted fixes remain in the working tree.

## Verification

- Five deployment tests cover first boot, fresh-process reuse, deleted-file recovery, immutable existing-file behavior, seed corruption, missing manifest entries, missing mount and destination symlink escape.
- Backend suite: **111 passed, 1 training test deselected, 1 existing Starlette/httpx warning in 27.41s**.
- Compose staging configuration validates with the artifact context; development still selects the ordinary runtime target.
- The real approved target was seeded into an isolated EBS-style directory, checked on another boot, deleted, then automatically restored; bytes equal the original file. Target SHA256: `3f08e42dd31363459d24eb9f8f861122ecb951c6a1f56a5485dd49f965213399`.
- Frozen model SHA256 values unchanged: U.S. `90c51c245ebe62b58f804098a7a7045b60fb64ef83da72d4c9a049cf8d5eeb0d`; Korea `42c3026386a58b25df337a431fbd5a793e93665a3d9a3f2cf22be4cfcc9186e3`.
- Local actual staging image build was attempted but the environment lacks Buildx and a Docker daemon. Image build/container recreation/EC2 reboot are **not** claimed verified. This follow-up did not deploy to AWS or commit/push.

## Applying the deployment repair

On the source machine, produce the controlled export (use a new destination):

```bash
python3 scripts/staging_state.py artifacts --data-root data --models-root models \
  --bundle /tmp/market-stress-release-artifacts
```

Transfer the verified export and reviewed deployment source changes through the existing authenticated delivery path. Deliver the **bundle**, not an individual manually copied target. The EBS release directory is a build input; API startup places/verifies the file automatically. Back up current state/source using the existing runbook before replacing files. Preserve all previous reviewed application fixes when building.

On AWS after source and bundle delivery, use a previously unused release directory. Set `STAGING_ARTIFACT_BUNDLE` through `sudoedit /etc/market-stress/staging.env` to `/srv/market-stress/release-artifacts-korea-static-fix` (or your unused versioned release directory). Do not print the populated env file or full Compose config.

```bash
cd /opt/market-stress-early-warning
sudo mountpoint -q /srv/market-stress
# This creates a new immutable release directory, not a patch to live application data.
sudo test ! -e /srv/market-stress/release-artifacts-korea-static-fix
sudo cp -a /tmp/market-stress-release-artifacts /srv/market-stress/release-artifacts-korea-static-fix
sudoedit /etc/market-stress/staging.env
sudo docker buildx version
stage_compose() {
  sudo docker compose --env-file /etc/market-stress/staging.env \
    -f /opt/market-stress-early-warning/deploy/docker-compose.staging.yml "$@"
}
stage_compose config --quiet
stage_compose build api
stage_compose up -d --force-recreate --wait --wait-timeout 360 api
stage_compose exec -T api ls -lh /app/data/processed/korea/korea_targets.csv
stage_compose exec -T api sha256sum /app/data/processed/korea/korea_targets.csv
# Stop the embedded scheduler for a controlled full refresh.
stage_compose stop api
stage_compose run --rm --no-deps -e MARKET_REFRESH_ENABLED=false api \
  python -m src.operations refresh --market korea
stage_compose up -d --wait --wait-timeout 360 api
curl --fail "$PUBLIC_ORIGIN/api/korea/latest"
```

Require a supported Compose/BuildKit/Buildx installation; named contexts need Compose 2.17+. See [Docker's build-context specification](https://docs.docker.com/reference/compose-file/build/#additional_contexts). If the named context is unsupported or the approved artifact is missing, repair build prerequisites; do not remove the checks or generate dummy labels.

Recreate the API a second time and compare target/model checksums; existing accounts/history must remain. During the later authorized reboot check, inspect EBS mount, container health and the same target checksum after reconnection. The current local fresh-process test exercises the initialization/persistence behavior, but actual EC2 reboot verification must occur on AWS. Do not delete the production file merely to test recovery: perform deletion/reseeding tests on an isolated volume.
