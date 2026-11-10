# Data sources

## Forecast provider: Open-Meteo ECMWF Single Runs API

M1 uses the Single Runs API to retrieve an exact, individually identified model run rather than a seamless forecast stitched from changing runs:

- Single-run forecast: \`https://single-runs-api.open-meteo.com/v1/forecast\`
- Model metadata: \`https://api.open-meteo.com/data/{model_id}/static/meta.json\`
- Commercial single-run endpoint: \`https://customer-single-runs-api.open-meteo.com\`
- Commercial metadata host: \`https://customer-api.open-meteo.com\`

The worker reads the latest model initialization time from metadata, waits for the provider's 10-minute consistency window after availability, then requests that exact run with the \`run=YYYY-MM-DDTHH:MM\` parameter. Each model is requested separately and stored as a separate forecast run.

### Model identifiers and native cadence

| Model ID | Model | Spatial resolution | Native time steps |
|---|---|---:|---|
| \`ecmwf_ifs\` | IFS HRES | 9 km | 1-hourly to 90 h, 3-hourly to 144 h, then 6-hourly |
| \`ecmwf_ifs025\` | IFS Open Data | 0.25° | 3-hourly to 144 h, then 6-hourly |
| \`ecmwf_aifs025_single\` | AIFS Single | 0.25° | 6-hourly |

Open-Meteo can interpolate hourly output from coarser native time steps. The worker stores the model's native step schedule and flags interpolated hourly values; the one-hour spacing of the returned time array is not treated as native one-hour model output.

### Initial hourly variables

- \`sunshine_duration\` — seconds per hour above the WMO direct-normal-irradiance threshold used by Open-Meteo.
- \`shortwave_radiation\`, \`direct_normal_irradiance\`, \`cloud_cover\`
- \`precipitation\`, \`temperature_2m\`, \`relative_humidity_2m\`, \`dew_point_2m\`
- \`wind_speed_10m\`, \`wind_direction_10m\`
- \`visibility\` — requested for IFS HRES only.

IFS 0.25° and AIFS do not natively publish direct and diffuse radiation in the same way as IFS HRES; Open-Meteo derives those components from global radiation. The worker records the DNI derivation method in each forecast run's metadata. Sunshine duration is also a derived indicator, not a directly observed ground measurement.

### Model-run metadata

The worker reads and stores:

- \`last_run_initialisation_time\`
- \`last_run_modification_time\`
- \`last_run_availability_time\`
- \`data_end_time\`
- \`temporal_resolution_seconds\`
- \`update_interval_seconds\`

This separates model initialization, provider publication, local retrieval and forecast valid time.

## Basin boundary: USGS Open-File Report 00-047

Initial operational boundary source:

- U.S. Geological Survey, Open-File Report 00-047 (2000)
- Structural sedimentary basin polygon dataset
- Download: \`https://pubs.usgs.gov/of/2000/of00-047/SHP_files/sed_basins.ZIP\`
- The source metadata says the basin polygons were digitized from a 1992 Chinese energy/mineral-resource map at 1:5,000,000 scale.

Important limitation: this is a generalized structural-sedimentary-basin boundary, not a definitive geomorphological or administrative boundary. It is treated as a versioned operational proxy for the first grid build. The importer requires the source shapefile's own .prj file and refuses to guess the datum. A future verified geomorphological boundary can replace it without changing the grid or forecast schema.

## City reference points: GeoNames

The 14 initial city points are imported from the official GeoNames \`cities15000\` dump and \`admin1CodesASCII.txt\`:

- Download: \`https://download.geonames.org/export/dump/cities15000.zip\`
- Admin-area codes: \`https://download.geonames.org/export/dump/admin1CodesASCII.txt\`
- License: CC BY 4.0; attribution to GeoNames is required.

The city points are gazetteer populated-place reference points, not administrative boundary centroids. Sichuan cities are matched to the Sichuan admin-1 code; Chongqing is matched separately. The imported snapshot date, GeoNames ID, population and feature code are retained.

## Licensing and operations

Open-Meteo's free API is restricted to non-commercial use. A product, advertising, subscription or commercial promotional use requires an appropriate paid API plan or separate authorization. For commercial deployments set \`OPEN_METEO_USAGE=commercial\` and provide \`OPEN_METEO_API_KEY\`; the worker then uses the customer API hosts. Do not use the free endpoint for a commercial deployment.

Open-Meteo weather data is provided under CC BY 4.0. Displayed data must be attributed and changes indicated. Review current provider terms, API limits and product-specific licensing before public release.

## Verification data

Historical reanalysis is useful for climatological context but must not be treated as a substitute for ground observations when claiming forecast accuracy. Forecast snapshots are retained by exact model run and lead time so later verification can compare issued forecasts with suitable station observations.
