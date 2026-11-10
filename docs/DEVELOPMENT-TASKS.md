# Development tasks

## M0 — Project foundation
- [x] Create repository and feature branch.
- [x] Add monorepo skeleton.
- [x] Add Next.js dashboard scaffold.
- [x] Add FastAPI health and data-status endpoints.
- [x] Add PostGIS Docker Compose service.
- [x] Add API tests and CI workflow.
- [ ] Run CI and fix build issues.

## M1 — Geography and ingestion
- [ ] Obtain a traceable Sichuan Basin boundary polygon.
- [ ] Generate a configurable 0.25-degree grid clipped to the basin.
- [ ] Add 14 initial city reference points with source metadata.
- [ ] Validate current Open-Meteo model identifiers and variables.
- [ ] Implement provider adapter and request batching.
- [ ] Persist model runs and raw forecast payloads.
- [ ] Add stale-data and missing-variable handling.

## M2 — Sunshine calculation
- [ ] Normalize sunshine duration to minutes.
- [ ] Calculate daily sunshine duration.
- [ ] Detect continuous sunshine windows.
- [ ] Aggregate grid results using area weights.
- [ ] Compare IFS and AIFS without presenting uncalibrated probabilities.
- [ ] Add deterministic unit tests.

## M3 — Product experience
- [ ] Replace map placeholder with MapLibre grid rendering.
- [ ] Add 72-hour timeline and forecast layer switching.
- [ ] Add 7-day daily sunshine trend.
- [ ] Add city detail routes.
- [ ] Add source/model freshness indicators.

## M4 — Verification
- [ ] Archive forecast snapshots by run and lead time.
- [ ] Connect suitable ground observations.
- [ ] Calculate sunshine-duration error and window hit rate.
- [ ] Evaluate probability reliability before displaying probabilities.
- [ ] Document verification methodology.

## M5 — Release readiness
- [ ] Review data licensing and attribution.
- [ ] Confirm meteorological information service requirements.
- [ ] Add monitoring, backups and operational alerts.
- [ ] Complete mobile and accessibility checks.
