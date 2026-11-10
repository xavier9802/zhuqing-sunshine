# Deploy Zhuqing Sunshine to Render

This Blueprint provisions the complete MVP stack in Singapore:
- Next.js public website
- FastAPI public read API
- Persistent Python ingestion worker
- Managed PostgreSQL with PostGIS enabled during first worker startup

## Cost and plan

The Blueprint uses always-on starter compute for the web, API, and worker, plus a 1 GB managed Postgres plan. Based on Render published compute pricing, the baseline is approximately **US$40/month**: three app services at about $7/month each, plus the 1 GB Postgres at about $19/month. Additional storage and bandwidth can add cost. Confirm the current estimate in the Blueprint review screen before deploying.

Free Render Postgres is deliberately not used because it expires after 30 days and has no backups. Free web services can spin down while idle and are not suitable for a continuously refreshed public service.

## Deploy

1. Sign in to Render and connect the GitHub account that can access `xavier9802/zhuqing-sunshine`.
2. In the Render Dashboard choose **New → Blueprint**.
3. Select this repository and branch `feature/m1-geography-weather-ingestion`.
4. Render reads the root `render.yaml`. Review the four resources and estimated charges.
5. Only select **Deploy Blueprint** if the displayed price is acceptable.

No secret is committed to the repository. The MVP uses Open-Meteo non-commercial endpoints. If the site is later used commercially, switch to an applicable paid Open-Meteo plan and add its API key in the Render Dashboard.

## Startup sequence

The worker waits for its database reference, enables PostGIS, creates/updates the schema, imports the USGS basin proxy and GeoNames city catalogue, then starts hourly Open-Meteo ingestion.

## Verify after deployment

- Website: https://zhuqing-sunshine-web.onrender.com
- API health: https://zhuqing-sunshine-api.onrender.com/health
- API readiness: https://zhuqing-sunshine-api.onrender.com/health/ready
- Model data status: https://zhuqing-sunshine-api.onrender.com/api/v1/data-status
- OpenAPI docs: https://zhuqing-sunshine-api.onrender.com/docs

Wait for worker logs to show `ingestion_cycle_complete`. The data-status endpoint should report available model runs and non-zero location counts. A successful container build alone is not a successful weather-data deployment.

## Operational notes

- Render service names generate the default `onrender.com` hostnames above. If Render changes a name to avoid a collision, update `NEXT_PUBLIC_API_BASE_URL` and `WEB_ORIGIN`, then redeploy web and API.
- All services and the database are in Singapore to avoid cross-region database latency.
- The basin boundary is a generalized USGS structural-sedimentary basin proxy, not an official administrative boundary.
- Forecasts are model outputs, not observed sunshine. Do not publish accuracy claims before station-based backtesting.
