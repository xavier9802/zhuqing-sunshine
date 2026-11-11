# CloudBase functions

## forecastIngest

- Runtime: Python 3.11
- Handler: `forecastIngest/index.main`
- Trigger: every four hours at minute 17 (CloudBase seven-field cron).
- Memory/timeout target: 3072 MB / 900 seconds.
- Runs the existing `sitegen.build.generate()` pipeline without changing the forecast rules.
- Writes immutable versioned snapshots to CloudBase Storage and updates `zhuqing/data/manifest.json` only after all files have uploaded.
- If all models fail, it raises an error and preserves the last published manifest.

Required environment configuration:
- `TCB_ENV` / `TCB_ENV_ID`: CloudBase environment ID.
- CloudBase function runtime credentials: use the platform's injected credentials for the Python CloudBase client. If the selected function runtime does not inject these credentials, configure a least-privilege server API key in the function's environment; do not commit it.
- `OPEN_METEO_USAGE=non_commercial` for the current Open-Meteo non-commercial endpoint.
- Optional `OPEN_METEO_API_KEY` only when a separately licensed commercial endpoint is used.

The public website must read the current manifest and snapshot files from CloudBase Storage (or a public CDN URL). Keep the GitHub Pages workflow enabled during the migration as a rollback path.
