# Architecture

\`\`\`text
USGS basin polygon ─┐
GeoNames city points ├─> Geography importer ─> PostGIS
                    │
Open-Meteo model metadata + Single Runs API
                    │
                    v
             Python ingestion worker
                    │
          ┌─────────┴──────────┐
          v                    v
   Raw JSONB payloads   Normalized hourly rows
          │                    │
          └─────────┬──────────┘
                    v
               PostgreSQL
                    │
                 FastAPI
                    │
              Next.js web app
\`\`\`

## Services

- **Web**: forecast presentation, map interaction, city exploration and explanations.
- **API**: stable read-only product endpoints; browser clients do not call weather providers directly.
- **Worker**: imports geographic source data, polls model metadata, retrieves exact model runs, batches requests, retries transient failures, archives raw payloads and normalizes hourly values.
- **PostGIS**: stores the basin boundary, clipped 0.25° cell polygons, city reference points and resolved provider grid-cell coordinates.

## Data model

- \`region_boundaries\`: source, scale, source CRS and versioned boundary geometry.
- \`forecast_locations\`: city and grid sample points; grid locations retain clipped cell geometry and area weights.
- \`forecast_runs\`: model ID, exact initialization time, retrieval time, provider publication time, native cadence and source provenance.
- \`raw_forecast_payloads\`: request parameters, raw response JSON and SHA-256 checksum for each batch.
- \`forecast_run_locations\`: mapping from requested location to the provider's resolved grid-cell coordinate.
- \`forecast_hourly\`: normalized forecast variables keyed by run, location and valid time.

## Engineering rules

1. Never overwrite a previous model run; every ingestion cycle creates a new run record.
2. Keep model initialization, provider availability, local retrieval and forecast valid time separate.
3. Preserve model-native temporal cadence and explicitly flag hourly interpolation.
4. Keep missing provider values as NULL; never silently replace them with zero.
5. Store provider-resolved grid-cell coordinates separately from requested sample coordinates.
6. Store the raw response and its checksum before relying on normalized values.
7. Do not call a model-consensus score a calibrated probability.
8. The initial basin polygon is a generalized structural-sedimentary proxy, not an official administrative boundary.

## Running M1 jobs

\`\`\`bash
# Start PostGIS, API and web
docker compose up --build -d db api web

# Import source geography and create the 0.25° grid
docker compose run --rm worker import-geography

# Fetch the latest available exact run for each configured ECMWF model
docker compose run --rm worker ingest-once --days 7
\`\`\`

The worker uses the free Open-Meteo endpoint only when explicitly configured for non-commercial use. For commercial operation, configure the paid customer endpoints and API key first.
