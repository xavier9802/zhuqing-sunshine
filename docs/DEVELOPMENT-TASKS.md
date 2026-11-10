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
- [x] Implement boundary download and reprojection when a .prj exists; for this source's missing .prj, use the USGS-documented decimal-degree coordinates with an explicitly provisional WGS84 display assumption and provenance caveat.
- [x] Implement a configurable 0.25° grid clipped to the basin with equal-area cell weights.
- [x] Implement the 14-city GeoNames import with province matching and source attribution.
- [x] Validate ECMWF model IDs against the current Open-Meteo API specification.
- [x] Add model metadata polling and retain run initialization / availability timestamps.
- [x] Add model-specific native temporal schedules and interpolation flags.
- [x] Add multi-location request batching, retries, timeout and 429 handling.
- [x] Persist raw payloads, checksums, normalized hourly data and provider-resolved grid coordinates.
- [x] Add worker tests and CI.
- [x] Execute a live USGS + GeoNames geography import in PostGIS CI; verified 14 cities, 358 grid cells and valid geometries.
- [ ] Execute the first forecast ingestion in the deployment environment after selecting the correct Open-Meteo usage plan.
- [ ] Verify model freshness and all requested model variables against a live forecast response.

## M2 — Sunshine calculation
- [x] Normalize sunshine duration to minutes for product calculations.
- [x] Detect continuous sunshine windows with missing-data handling.
- [x] Calculate daily sunshine duration and daylight-normalized indicators.
- [x] Aggregate grid results using clipped cell area weights.
- [x] Expose IFS and AIFS as separately selectable model runs; do not present uncalibrated probabilities.
- [x] Add deterministic unit tests for edge cases.

## M3 — Product experience
- [x] Replace map placeholder with MapLibre grid rendering.
- [x] Add 72-hour timeline and forecast model switching.
- [x] Add 7-day daily sunshine trend.
- [x] Add city detail routes.
- [x] Add source/model freshness indicators.

## M4 — Verification
- [ ] Archive forecast snapshots by run and lead time.
- [ ] Connect suitable ground observations.
- [ ] Calculate sunshine-duration error and window hit rate.
- [ ] Evaluate probability reliability before displaying probabilities.
- [ ] Document verification methodology.

## M5 — Release readiness
- [x] Add Open-Meteo, GeoNames, USGS and OpenStreetMap source attribution to the product UI.
- [x] Document Open-Meteo non-commercial vs commercial API usage requirements.
- [ ] Review final deployment data licensing and attribution.
- [ ] Confirm meteorological information service requirements.
- [ ] Add monitoring, backups and operational alerts.
- [ ] Complete mobile and accessibility checks.
