# Assignment 2 EDA - Run Guide

## 1. Point at the runtime

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
RUNTIME="$DATA_PIPELINE_DATA_ROOT/data-pipeline"
PY="$RUNTIME/.venv/bin/python"
```

The EDA is read-only against the runtime and resolves paths through
`lib/paths.py`, which reads `DATA_PIPELINE_DATA_ROOT`. Run it from the runtime
source copy or the repo source; both import the same package.

## 2. Run it

```bash
cd "$RUNTIME/src"
$PY scripts/eda/assignment2/run.py
```

Expected stdout on a complete dataset:

```text
Output: /home/coder/my-farm-advisor-runtime/data-pipeline/eda/assignment-2
  figure: figures/boundaries_01_acreage_by_grower.png
  ...
  figure: figures/map_01_field_map.png
  table:  tables/map_fields.csv

  Illinois   fields=10 cdl=current (2021-2025) weather=10
  Iowa       fields=10 cdl=current (2021-2025) weather=10
  Nebraska   fields=10 cdl=current (2021-2025) weather=10
  tests: 14 -> .../tables/tests.csv
```

Run one category while iterating:

```bash
$PY scripts/eda/assignment2/run.py --category weather
$PY scripts/eda/assignment2/run.py --category boundaries --category map
```

Categories are `boundaries`, `cdl`, `weather`, and `map`; repeat the flag to
combine them.

While a reseeded pipeline is still running, add the archive fallback flag:

```bash
$PY scripts/eda/assignment2/run.py --allow-archive-fallback
```

The flag only borrows archived **previous-sample** weather and CDL. It never
fabricates or interpolates data, and every borrowed layer is named in the
figure footnote and in `data_manifest.json`.

## 3. Verify

```bash
ls -lh "$RUNTIME/eda/assignment-2/figures"
column -s, -t "$RUNTIME/eda/assignment-2/tables/tests.csv"
python -m json.tool "$RUNTIME/eda/assignment-2/data_manifest.json" | head -40
```

Checks worth making every run:

- `cdl_source` is `current (2021-2025)` once the pipeline has finished.
- `weather_fields` equals the field count for each grower.
- Each figure is populated; no empty panels, clipped titles, or illegible
  labels at README size.
- Legend and footnote name any fallback that was used.
- `map.fields_with_2025_cdl` equals the field count when CDL is complete.

## 4. Re-run after the pipelines finish

The script overwrites its own outputs, so re-running is the refresh path:

```bash
cd "$RUNTIME/src"
$PY scripts/eda/assignment2/run.py
```

If CDL reports `previous-sample`, the farm table is stale. Check the filename
under `$RUNTIME/growers/<grower>/farms/<farm>/derived/tables/` - a current
window must contain `_cdl_2021_2025_full_composition.csv`. Re-run the farm
pipeline with `--cdl-latest-year 2025 --cdl-window-years 5` to produce it.

If weather is missing for a grower, check
`$RUNTIME/growers/<grower>/farms/<farm>/fields/*/weather/daily_weather.csv`
row counts; the pipeline must finish its weather step first.

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RuntimeError: No boundary data available for any farm` | No `boundary/field_boundaries.geojson` | Run `bootstrap_farm_from_county.py`, then the farm pipeline |
| A whole figure is absent | That category failed for every grower | Check the `warning:` lines in stdout and `errors` in the manifest |
| Weather shows only one grower | Other growers' weather CSVs are still header-only | Check each `fields/*/weather/daily_weather.csv` row count |
| CDL heat map is empty or single-year | Composition table missing or unreadable | Re-run the CDL step |
| GDD values look too low | Season or base differs from expectation | Season is Apr-Oct, base 10 °C, cap 30 °C |
| Corn share is all 0% | CDL years outside the table window, or `No Data` classes | Check `cdl_years` in the manifest |
| Diversity plot shows Shannon instead of class counts | Every field-year had the same class count | Expected; the manifest records `cdl.diversity_field` |
| Map fields are all grey | No 2025 CDL class for those fields | Let the CDL step finish, then re-run `--category map` |

## 6. Keep outputs out of Git

Everything under `eda/assignment-2/` is runtime output. Do not copy the PNGs,
CSVs, or manifest into the repository. The docs in this folder describe the
recipe; the data stays under `DATA_PIPELINE_DATA_ROOT`.
