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
- Decode native FM-12 reports in both AAXX and NOAA GHCNh compact `SYN...` forms. Total cloud amount `N` in the `Nddff` group is converted from oktas to percent; a slash (`/`) means cloud amount was not reported and is excluded, never treated as clear. The `7wwW1W2` group is used to flag present precipitation (`ww` 50–99). Station diagnostics distinguish FM-12 reports with a cloud amount from reports where `N` is missing.
- Add an independent daily solar-radiation comparison using NASA POWER `ALLSKY_SFC_SW_DWN` (MJ/m²/day, local solar time) against the daily sum of Open-Meteo hourly shortwave radiation. NASA POWER is a 0.5° satellite/reanalysis product, not a direct sunshine-duration sensor; its results are reported separately and cannot by themselves calibrate sunshine probability.

## Metrics

For each lead day, report station-day binary classification metrics for the positive class “sunny or mostly_sunny”: confusion matrix, accuracy, precision, recall and F1. Also report hourly total-cloud-cover MAE and signed bias. The sunny_score is not treated as a probability, so no Brier score or probability calibration is claimed.

## Limitations and guardrails

- GHCNh stations in the basin are sparse and are often airports. Station conditions cannot be assumed to represent the entire basin's area-weighted weather.
- METAR sky cover is a categorical cloud observation, not a sunshine-duration instrument. This backtest does not validate sunshine_duration in minutes.
- The three ECMWF products are related forecasts, not independent probabilistic members.
- Do not adjust production thresholds from a small or seasonally unbalanced sample. Require at least 200 station-days overall, at least 50 station-days per lead, and representation across all four seasons before proposing a threshold change.
- A stronger sunshine-duration verification requires China Meteorological Administration surface station sunshine-duration observations or a separately validated satellite-derived surface solar-radiation product.


## First live exploratory run and quality gates

The first successful pipeline execution used 12 archived HRES initialisations and selected 8 NOAA stations with year files. Only two sites (CHI0000ZUCK / Jiangbei and CHI0000ZUTF / Chengdu Tianfu) had sufficiently parseable hourly sky conditions. They produced 72 station-days (24 per lead), which is below research-review thresholds; results MUST be labeled exploratory and not presented as an operational accuracy figure.

New quality gates require at least 200 station-days, at least four independently located usable stations, 50 station-days for each of the 1–3 day leads, and coverage of winter/spring/summer/autumn. Passing these sampling checks still requires independent holdout observations and actual sunshine-duration/solar-radiation measurements before any operational calibration or probability claim.

The cloud-cover MAE averages per-station-day hourly errors equally, not all raw hourly pairs equally. Note that the 2024–2026 period includes an ECMWF IFS cycle change; formal calibration should stratify skill by model cycle.

## Repeated verification

The default end date advances automatically to 14 days before execution (to leave time for station-year reports); the default branch's monthly schedule evaluates up to 24 historical run dates. Branch CI uses 12 run dates to limit provider requests. The observations are not sufficient for a true sunshine-duration calibration without independent station sunshine-duration instruments.
