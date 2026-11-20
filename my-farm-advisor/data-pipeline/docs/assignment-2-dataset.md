# Assignment 2 dataset expansion

This runbook records how the Assignment 2 runtime dataset was built: three
growers with one farm and ten fields each, focused on field boundaries, weather,
and CDL/cropland layers. Runtime data stays under
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline` and is never committed.

## Dataset

| Grower | Farm | State / county | Fields | Acres |
|---|---|---|---:|---:|
| `il-corn-grower` | `il-corn-grower-illinois` | Illinois / Iroquois (17075) | 10 | 1,084.6 |
| `ia-corn-grower` | `ia-corn-grower-iowa` | Iowa / Kossuth (19109) | 10 | 1,505.3 |
| `ne-corn-grower` | `ne-corn-grower-nebraska` | Nebraska / York (31185) | 10 | 1,060.0 |

All three farms are single-farm growers. Field boundaries come from
OpenStreetMap `landuse=farmland` polygons clipped to the county, sampled
deterministically with seed `42`.

## Decisions

- **Nebraska county: York (31185).** York is in the Central Platte Valley, where
  center-pivot irrigated corn/soy is the dominant cropping system. The county
  has enough mapped farmland polygons to sample ten fields at pivot scale.
- **Minimum field size.** Illinois and Iowa used a 10-acre floor; Nebraska used a
  40-acre floor so the sample reflects center-pivot field geometry rather than
  small mapped fragments.
- **Reseed from scratch.** Illinois and Iowa were reseeded to ten fields rather
  than appended, so the ten-field sample is the deterministic seed-42 sample for
  the county. Previous field artifacts were archived under
  `farms/<farm>/archive/reseed-<timestamp>/fields/`.
- **Full pipeline.** Soil, terrain, weather, CDL, satellite, NDVI, and farm
  reports all run. Soil is not used in the Assignment 2 EDA, but keeping it
  preserves the complete report chain.
- **CDL window 2021–2025.** Farm CDL composition now covers the same years as
  weather and NDVI, so 2024–2025 crop labels are resolved instead of `Unknown`.

## Pipeline changes

- `bootstrap_farm_from_county.py`: new `--min-acres` filter (default `0.5`,
  backward compatible).
- `download_cdl.py`: farm mode now honours `--cdl-latest-year` and
  `--cdl-window-years` (and explicit `--cdl-years`), and the cache gate compares
  the requested window instead of always accepting any five cached years.
- `run_farm_pipeline.py`: new `--cdl-latest-year` / `--cdl-window-years` flags
  forwarded to the CDL step. Defaults remain unchanged (`2023`, `5`).
- `farm_dashboard.py`: `create` forwards the same CDL window flags to the farm
  pipeline.

## Reproduce

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline/src"
PY="$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python"

# Illinois: reseed ten fields in Iroquois County
$PY scripts/ingest/bootstrap_farm_from_county.py \
  --state-fips 17 --county-name Iroquois \
  --grower-slug il-corn-grower \
  --farm-slug il-corn-grower-illinois \
  --farm-name "Illinois Corn Farm" \
  --count 10 --seed 42 --min-acres 10

$PY scripts/run_farm_pipeline.py \
  --grower-slug il-corn-grower \
  --farm-slug il-corn-grower-illinois \
  --farm-name "Illinois Corn Farm" \
  --cdl-latest-year 2025 --cdl-window-years 5

# Iowa: reseed ten fields in Kossuth County
$PY scripts/ingest/bootstrap_farm_from_county.py \
  --state-fips 19 --county-name Kossuth \
  --grower-slug ia-corn-grower \
  --farm-slug ia-corn-grower-iowa \
  --farm-name "Iowa Corn Farm" \
  --count 10 --seed 42 --min-acres 10

$PY scripts/run_farm_pipeline.py \
  --grower-slug ia-corn-grower \
  --farm-slug ia-corn-grower-iowa \
  --farm-name "Iowa Corn Farm" \
  --cdl-latest-year 2025 --cdl-window-years 5

# Nebraska: new grower/farm, ten pivot-scale fields in York County
$PY scripts/ingest/bootstrap_farm_from_county.py \
  --state-fips 31 --county-name York \
  --grower-slug ne-corn-grower \
  --farm-slug ne-corn-grower-nebraska \
  --farm-name "Nebraska Corn Farm" \
  --count 10 --seed 42 --min-acres 40

$PY scripts/run_farm_pipeline.py \
  --grower-slug ne-corn-grower \
  --farm-slug ne-corn-grower-nebraska \
  --farm-name "Nebraska Corn Farm" \
  --cdl-latest-year 2025 --cdl-window-years 5
```

Regenerate the grower maps after the pipelines:

```bash
$PY scripts/render_grower_web_map.py \
  --grower il-corn-grower --grower ia-corn-grower --grower ne-corn-grower
```

## Expected coverage

| Layer | Coverage |
|---|---|
| Field boundaries | 10 per farm, 30 total |
| Weather | Daily 2021-01-01 through 2025-12-31 per field |
| CDL/cropland | Crop composition 2021–2025 plus rotation summary |
| NDVI | Yearly composites 2021–2025 and crop joins |
| Soil | SSURGO tables and maps from the full pipeline |
| Web map | `growers/<grower>/derived/reports/grower_web_map.html` |

## Verification

Verification results are recorded in the Assignment 2 build report. The runtime
dataset is intentionally excluded from Git; only this runbook and the small
pipeline changes are versioned.
