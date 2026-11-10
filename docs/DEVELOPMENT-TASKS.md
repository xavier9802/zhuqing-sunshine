# Development tasks

## M0 — Project foundation
- [x] Create repository and feature branch.
- [x] Add monorepo skeleton.
- [x] Add Next.js dashboard scaffold.
- [x] Add FastAPI health and data-status endpoints.
- [x] Add PostGIS Docker Compose service.
- [x] Add API tests and CI workflow.
- [x] Pass frontend and API CI.

## M1 — Geography and weather ingestion
- [x] Identify a traceable initial Sichuan Basin structural-sedimentary boundary source.
- [x] Implement boundary download, CRS validation and reprojection; refuse missing CRS metadata.
- [x] Implement a configurable 0.25° grid clipped to the basin with equal-area cell weights.
- [x] Implement the 14-city GeoNames import with province matching and source attribution.
- [x] Validate ECMWF model IDs against the current Open-Meteo API specification.
- [x] Add model metadata polling and retain run initialization / availability timestamps.
- [x] Add model-specific native temporal schedules and interpolation flags.
- [x] Add multi-location request batching, retries, timeout and 429 handling.
- [x] Persist raw payloads, checksums, normalized hourly data and provider-resolved grid coordinates.
- [x] Add worker tests and CI.
- [ ] Execute geography import against the live source datasets in the deployment environment.
- [ ] Execute a real model ingestion after the correct Open-Meteo usage plan and credentials are configured.
- [ ] Verify the returned city count, grid-cell count, data freshness and model-variable availability.

## M2 — Sunshine calculation
- [ ] Normalize sunshine duration to minutes for product calculations.
- [ ] Detect continuous sunshine windows with missing-data handling.
- [ ] Calculate daily sunshine duration and daylight-normalized indicators.
- [ ] Aggregate grid results using clipped cell area weights.
- [ ] Compare IFS and AIFS without presenting uncalibrated probabilities.
- [ ] Add deterministic unit tests for edge cases.

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
