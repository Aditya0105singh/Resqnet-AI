# Flood model vs. observed water: Kerala 2018

Reproduce with `python scripts/validate_flood.py <map>` (needs network; results cache in `tmp/s1_cache/`).

## Data used

| What | Source | Access |
|---|---|---|
| Roads, bridges, rivers, shelters | OpenStreetMap | Overpass API |
| Terrain | Copernicus DEM GLO-30 (30 m surface model, 3×3 median) | Microsoft Planetary Computer, no account |
| River discharge, 14–18 Aug 2018 | GloFAS v4 reanalysis | Open-Meteo Flood API |
| Rainfall, 14–18 Aug 2018 | IMD 0.25° gauge-based daily grid (daily totals) + ERA5 (hourly shape only) | imdpune.gov.in, Open-Meteo |
| Observed water | Sentinel-1 RTC VV, 9 Aug (pre) and 21 Aug (post), descending orbit 165 | Planetary Computer |

IMD and ERA5 disagree a lot on the peak days. At the Aluva grid point IMD has 137 / 180 mm on 15 / 16 Aug where ERA5 has 117 / 76 mm, and ERA5 has three times IMD's rain on 14 Aug. IMD is gauge-based, so the simulator uses IMD totals. GloFAS is driven by ERA5-based meteorology, so its discharge peak is probably understated.

## Method

- **Observed flooding.** Change detection between two passes with identical geometry: a pixel counts as flooded when VV darkened by more than 3 dB since 9 Aug and is below −10 dB on 21 Aug.
  - A plain "below −17 dB" open-water test found almost nothing.
  - Shallow water among crops, trees and buildings does not get that dark.
- **Model.** Water depth at each road junction, computed with the GloFAS discharge for the satellite pass time (21 Aug 06:10 IST).
- **Comparison unit.** The share of flooded pixels within 400 m or 800 m of each junction. Junctions themselves sit on raised, bright roads, so radar sees almost no water exactly at them.

## Results (21 Aug, five days after the peak)

AUC 0.5 means no skill (chance), 1.0 means a perfect ranking.

| Map | Radius | Observed-wet junctions | Model elevation AUC | Model precision / recall / F1 |
|---|---|---|---|---|
| Chengannur | 400 m | 21 / 72 | **0.76** | 0.86 / 0.29 / 0.43 |
| Chengannur | 800 m | 33 / 72 | **0.77** | 1.00 / 0.24 / 0.39 |
| Aluva | 400 m | 10 / 78 | 0.61 | 0.18 / 0.30 / 0.22 |
| Aluva | 800 m | 11 / 78 | 0.51 | 0.22 / 0.36 / 0.28 |

The first version of the terrain model is shown for comparison. It used a 90 m DEM blended with height above the nearest channel, plus per-neighbourhood multipliers, and scored AUC 0.42–0.62 and F1 0.10–0.18. Those results are why the builder now uses plain relief from the 30 m DEM and a single water level.

## What this does and does not show

- **Chengannur:** the model puts water where the satellite saw it with useful skill. When it says a junction is flooded it is usually right, but it misses about 70% of the wet areas.
- **Aluva:** skill is weak.
  - Aluva is built-up, and SAR is known to under-detect urban flooding because walls and water reflect strongly back to the sensor.
  - So both the observation and the model are less reliable there.
- **The peak is untested.** No Sentinel-1 pass covered 14–19 Aug, so the satellite only shows the water left after recession, largely in paddy fields and hollows. Distance to the river is anti-correlated with this leftover water.
- **Small samples.** The sample is 10–33 wet junctions per map, so each AUC is uncertain by roughly ±0.1.
- **Choices made after seeing results.** Three terrain predictors were compared, and the one that was better on both maps was kept. Treat these numbers as indicative, not as an independent test.

Not usable here: NRSC/Bhuvan published 2018 inundation maps only as PDFs. The Dartmouth Flood Observatory event page (4663) is marked "in preparation" and its link now returns 404.
