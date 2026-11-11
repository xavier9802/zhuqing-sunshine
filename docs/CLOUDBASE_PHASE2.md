# CloudBase Phase 2: forecast compute migration

## Target design

- Static frontend remains a prebuilt Next.js export and is hosted by CloudBase Static Hosting.
- The Python forecast pipeline runs as a CloudBase Python 3.11 scheduled function.
- Forecast JSON is published to CloudBase Storage as immutable snapshots.
- A small manifest is updated last, so the previous snapshot remains authoritative if a run fails midway.
- No database is introduced: the current product is read-only and snapshot-oriented.

## Why Python 3.11

CloudBase's current ordinary and HTTP function runtime matrix lists Python 3.11 and 3.10, not 3.12. The current pipeline dependencies (Shapely, PyProj, PyShp, httpx) must be installed and smoke-tested in the selected Python 3.11 runtime before production activation.

## Scheduled execution

CloudBase timer trigger uses a seven-field cron expression. The function is configured for every four hours at minute 17: `0 17 */4 * * * *`. GitHub Actions also has a manual dispatch workflow for controlled deployment and one-shot execution.

## Data publishing

Each run writes generated data files under `zhuqing/snapshots/<snapshot-id>/data/...`. Only after all snapshot objects upload successfully does the function replace `zhuqing/data/manifest.json`. Consumers should fetch the manifest first, then resolve all data paths beneath `data_prefix`. This avoids partial data becoming current.

## Rollback

- Keep GitHub Pages and its scheduled workflow active until CloudBase function and frontend reads have passed multiple full refresh cycles.
- If the CloudBase function fails, the last manifest remains unchanged.
- Roll back the website DNS/hosting origin to GitHub Pages; do not delete old snapshots.

## Required console setup

1. Create or select the dedicated CloudBase environment.
2. Enable Cloud Storage and configure public read for the `zhuqing/**` forecast paths; keep writes server-only.
3. Add GitHub repository secrets: `TCB_ENV_ID`, `TCB_SECRET_ID`, `TCB_SECRET_KEY`.
4. Deploy the function using the workflow, inspect function logs, and invoke a live run.
5. Confirm the manifest timestamp, 3 model status records, and 372 locations where models provide complete coverage.
6. Only then switch the frontend to CloudBase Storage and bind the custom domain.

## Known activation gate

This repository does not have a CloudBase environment ID or credentials in source control. Therefore code can be prepared and validated in GitHub, but the actual CloudBase deployment cannot occur until the environment and repository secrets are configured. Never commit CloudBase secrets.
