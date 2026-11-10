# Forecast verification protocol

## Objective

Measure the ECMWF IFS HRES forecast's ability to predict daytime clear/bright sky conditions at actual surface stations in and near the Sichuan Basin. This is a first independent verification layer; it is not a claim of basin-wide sunshine-duration accuracy.

## Data sources

- Forecast: archived individual ECMWF IFS HRES runs through the Open-Meteo Single Runs API. Exact run initialisation timestamps are requested to avoid comparing a stitched forecast series with a different lead time.
- Observations: NOAA NCEI Global Historical Climatology Network hourly (GHCNh), which aggregates hourly/synoptic reports from fixed land stations. Station metadata and annual PSV files are downloaded from the official NOAA bulk interface.
- Geography: the repository's USGS Sichuan Basin structural-sedimentary proxy. Stations outside the polygon are only included when fewer than three in-basin stations are available.

## Matching protocol

- Sample archived 00 UTC HRES runs on monthly mid-month dates across 2024-04 to 2026-09, evenly downsampled to the configured maximum run count.
- Evaluate local target dates at lead days 1, 2 and 3.
- Use daytime local observations from 07:00 through 18:59 Asia/Shanghai.
- Match each forecast valid time to the nearest NOAA report within 35 minutes.
- Require at least four matched daylight hours for a station-day. Missing observations are excluded, never treated as clear or dry.
- Use NOAA raw report remarks containing a parseable METAR/SYNOP cloud layer group. Cloud categories are converted to approximate oktas midpoints: FEW 18.75%, SCT 43.75%, BKN 75%, OVC/VV 100%; CLR/SKC 0%. CAVOK/NSC/NCD are conservatively set to 26% because they do not prove a completely cloud-free sky.

## Metrics

For each lead day, report station-day binary classification metrics for the positive class “sunny or mostly_sunny”: confusion matrix, accuracy, precision, recall and F1. Also report hourly total-cloud-cover MAE and signed bias. The sunny_score is not treated as a probability, so no Brier score or probability calibration is claimed.

## Limitations and guardrails

- GHCNh stations in the basin are sparse and are often airports. Station conditions cannot be assumed to represent the entire basin's area-weighted weather.
- METAR sky cover is a categorical cloud observation, not a sunshine-duration instrument. This backtest does not validate sunshine_duration in minutes.
- The three ECMWF products are related forecasts, not independent probabilistic members.
- Do not adjust production thresholds from a small or seasonally unbalanced sample. Require at least 200 station-days overall, at least 50 station-days per lead, and representation across all four seasons before proposing a threshold change.
- A stronger sunshine-duration verification requires China Meteorological Administration surface station sunshine-duration observations or a separately validated satellite-derived surface solar-radiation product.
