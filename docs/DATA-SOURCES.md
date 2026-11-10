# Data sources

## MVP provider: Open-Meteo

Open-Meteo is the initial access layer. The worker must record the selected model, requested variables, coordinates, retrieval time and available provider metadata.

### Initial model candidates
- ECMWF IFS variants available through the selected endpoint.
- ECMWF AIFS variants available through the selected endpoint.

Validate current model identifiers and supported variables against live documentation before enabling ingestion. Do not assume every model-variable combination is available.

### Initial variables
- sunshine_duration
- direct_normal_irradiance
- shortwave_radiation
- cloud_cover
- cloud_cover_low (when supported)
- precipitation
- relative_humidity_2m
- dew_point_2m
- visibility
- wind_speed_10m
- wind_direction_10m

### Data handling
- Display in Asia/Shanghai; preserve UTC timestamps internally.
- Archive raw provider payloads.
- Store retrieval time separately from forecast valid time.
- Record native model cadence; mark interpolated values explicitly.
- Handle missing or unsupported variables explicitly.

## Licensing and operations
Review current Open-Meteo terms, attribution, rate limits and commercial-use options before public or commercial launch. API availability does not automatically grant permission for every use case.

## Future sources
- Direct ECMWF open data.
- China Meteorological Data Service Centre observations.
- Fengyun satellite products, subject to access and licensing.
- Local ground observations for forecast verification.

Historical reanalysis is useful for context but is not a substitute for station observations when claiming forecast accuracy.
