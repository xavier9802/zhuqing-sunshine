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
- Prefer native GHCNh sky-cover columns (`sky_condition`, `sky_cover`, `sky_cover_1..3`, `sky_cover_summation_1..4`, and `sky_cover_layer_1..4`) before falling back to NOAA raw METAR/SYNOP remarks. Numeric sky-cover codes are interpreted as oktas where documented; cloud categories are converted to approximate oktas midpoints: FEW 18.75%, SCT 43.75%, BKN 75%, OVC/VV 100%; CLR/SKC 0%. CAVOK/NSC/NCD are conservatively set to 26% because they do not prove a completely cloud-free sky.
- Decode native FM-12 reports in both AAXX and NOAA GHCNh compact `SYN...` forms. Total cloud amount `N` in the `Nddff` group is converted from oktas to percent; a slash (`/`) means cloud amount was not reported and is excluded, never treated as clear. The `7wwW1W2` group is used to flag present precipitation (`ww` 50–99). Station diagnostics distinguish FM-12 reports with a cloud amount from reports where `N` is missing.
- Add an independent daily solar-radiation comparison using NASA POWER `ALLSKY_SFC_SW_DWN` (`AG` community, MJ/m²/day, local solar time) against the daily sum of Open-Meteo hourly shortwave radiation. NASA POWER uses a 0.5° × 0.625° meteorological grid and is a satellite/reanalysis product, not a direct sunshine-duration sensor; its results are reported separately and cannot by themselves calibrate sunshine probability.
- Add a time-ordered holdout: the latest available forecast-initialisation year is held out, and earlier years are used only to estimate a lead-specific mean radiation bias. Raw and bias-adjusted holdout MAE/RMSE/bias are reported separately. This evaluates temporal bias stability against NASA POWER only; no correction is automatically applied to production or to sunshine-duration classification.
- Add a holdout-only low-cloud guardrail sensitivity comparison. The counterfactual removes the low-cloud restriction while retaining total-cloud, sunshine-duration and precipitation checks. It is diagnostic only; each lead requires at least 50 holdout station-days before a threshold change can even be considered.

## Metrics

For each lead day, report station-day binary classification metrics for the positive class “sunny or mostly_sunny”: confusion matrix, accuracy, precision, recall and F1. Also report hourly total-cloud-cover MAE and signed bias. The sunny_score is not treated as a probability, so no Brier score or probability calibration is claimed.

## Limitations and guardrails

- GHCNh stations in the basin are sparse and are often airports. Station conditions cannot be assumed to represent the entire basin's area-weighted weather.
- METAR sky cover is a categorical cloud observation, not a sunshine-duration instrument. This backtest does not validate sunshine_duration in minutes.
- The three ECMWF products are related forecasts, not independent probabilistic members.
- Do not adjust production thresholds from a small or seasonally unbalanced sample. Require at least 200 station-days overall, at least 50 station-days per lead, and representation across all four seasons before proposing a threshold change.
- A stronger sunshine-duration verification requires China Meteorological Administration surface station sunshine-duration observations or a separately validated satellite-derived surface solar-radiation product.


## Latest exploratory run and quality gates (2026-11-10)

The current 24-run audit sampled monthly 00 UTC ECMWF IFS HRES initialisations from 2024-04-15 through 2026-10-15. Twelve NOAA stations were selected; only three airport stations supplied enough parseable cloud observations:

- Verified stations: CHI0000ZUCK (Chongqing Jiangbei), CHI0000ZUTF (Chengdu Tianfu), CHI0000ZUUU (Chengdu Shuangliu).
- Candidate stations: 12; verified stations: 3.
- HRES samples: 216 station-days, 72 per lead, across all four seasons.
- The sample-size, per-lead and seasonal checks pass, but the four-station requirement fails. The report remains exploratory and cannot support a basin-wide accuracy claim.

Most non-airport SYNOP reports in the sample encode the total-cloud N group as /. This means cloud amount was not reported. The parser correctly excludes those records rather than treating missing cloud as clear. Adding more such stations does not increase the usable cloud-observation sample.

HRES station-proxy classification metrics:

| Lead | Accuracy | Precision | Recall | F1 | Cloud MAE | Cloud bias |
|---|---:|---:|---:|---:|---:|---:|
| 1 day | 61.1% | 90.0% | 51.9% | 65.9% | 42.8 pp | +31.1 pp |
| 2 days | 59.7% | 92.3% | 47.1% | 62.3% | 42.4 pp | +31.9 pp |
| 3 days | 63.9% | 80.0% | 54.5% | 64.9% | 37.2 pp | +23.5 pp |

These are three-airport cloud-condition proxy metrics, not observed sunshine-duration accuracy.

NASA POWER radiation research comparison uses 12 spatial points and 288 spatial-day pairs per lead for HRES. A time-ordered holdout uses 2024–2025 for training and 2026 for holdout:

| Lead | Training bias | 2026 raw holdout MAE | Raw holdout bias | Bias-corrected MAE | MAE improvement |
|---|---:|---:|---:|---:|---:|
| 1 day | +0.11 MJ/m² | 3.24 MJ/m² | +2.27 MJ/m² | 3.19 MJ/m² | 1.5% |
| 2 days | +0.37 MJ/m² | 3.69 MJ/m² | +2.78 MJ/m² | 3.55 MJ/m² | 3.8% |
| 3 days | +0.79 MJ/m² | 4.04 MJ/m² | +2.33 MJ/m² | 3.74 MJ/m² | 7.4% |

The training-period bias does not transfer cleanly to 2026. Even after the research-only correction, residual holdout bias remains. No correction is applied to production.

IFS 0.25° and AIFS 0.25° archived runs were available for only 5 of the 24 dates. Their station and radiation comparisons are too small for model-selection or calibration decisions. The three ECMWF products remain directional cross-checks, not independent ensemble members.

## Repeated verification

The default end date advances automatically to 14 days before execution (to leave time for station-year reports); the default branch's monthly schedule evaluates up to 24 historical run dates. Branch CI uses 12 run dates to limit provider requests. The observations are not sufficient for a true sunshine-duration calibration without independent station sunshine-duration instruments.
