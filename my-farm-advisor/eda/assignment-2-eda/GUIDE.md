# Assignment 2 EDA - Run Guide

## 1. Point at the runtime

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
RUNTIME="$DATA_PIPELINE_DATA_ROOT/data-pipeline"
PY="$RUNTIME/.venv/bin/python"
```

The generator is read-only against the runtime, so it can be run either from
the repo source or from the synced runtime source. Both resolve paths through
`lib/paths.py`, which reads `DATA_PIPELINE_DATA_ROOT`.

## 2. Run it

```bash
cd "$RUNTIME/src"
$PY scripts/eda/assignment2_eda.py
```

Expected stdout on a complete dataset:

```text
Output: /home/coder/my-farm-advisor-runtime/data-pipeline/eda/assignment-2
  assignment2_boundaries.png
  assignment2_cdl.png
  assignment2_weather.png
  Illinois   fields=10 cdl=current (2021-2025) weather_fields=10
  Iowa       fields=10 cdl=current (2021-2025) weather_fields=10
  Nebraska   fields=10 cdl=current (2021-2025) weather_fields=10
```

While a reseeded pipeline is still running, add the archive fallback flag:

```bash
$PY scripts/eda/assignment2_eda.py --allow-archive-fallback
```

The flag only borrows archived **previous-sample** weather and CDL. It never
fabricates or interpolates data, and every borrowed layer is named in the
figure footnote and in `data_manifest.json`.

## 3. Verify

```bash
ls -lh "$RUNTIME/eda/assignment-2"
cat "$RUNTIME/eda/assignment-2/data_manifest.json"
column -s, -t "$RUNTIME/eda/assignment-2/assignment2_weather_stats.csv"
```

Checks worth making every run:

- `cdl_source` is `current (2021-2025)` once the pipeline has finished.
- `weather_fields` equals the field count for each grower.
- Statistics CSVs have one row per grower with no `nan` in means.
- Each PNG has three populated panels, no clipped titles, and legible labels at
  README size.
- The figure footnote names any fallback that was used.

## 4. Re-run after the pipelines finish

The script overwrites its own outputs, so re-running is the refresh path:

```bash
cd "$RUNTIME/src"
$PY scripts/eda/assignment2_eda.py
```

If CDL still reports `previous-sample`, the farm table is stale. Check the
filename under
`$RUNTIME/growers/<grower>/farms/<farm>/derived/tables/` - a current window
must contain `_cdl_2021_2025_full_composition.csv`. Re-run the farm pipeline
with `--cdl-latest-year 2025 --cdl-window-years 5` to produce it.

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RuntimeError: No boundary data available for any farm` | No `boundary/field_boundaries.geojson` | Run `bootstrap_farm_from_county.py`, then the farm pipeline |
| Weather panel is missing entirely | No series with at least 300 daily rows | Let the pipeline finish; or use `--allow-archive-fallback` |
| Weather panel shows only one grower | Other growers' weather CSVs are still header-only | Check each `fields/*/weather/daily_weather.csv` row count |
| CDL heat map is empty or single-year | Composition table missing or unreadable | Re-run the CDL step |
| GDD values look too low | Season or base differs from expectation | Season is Apr-Oct, base 10 °C, cap 30 °C |
| Corn share is all 0% | CDL years outside the table window, or `No Data` classes | Check `cdl_years` in the manifest |

## 6. Keep outputs out of Git

Everything under `eda/assignment-2/` is runtime output. Do not copy the PNGs,
CSVs, or manifest into the repository. The docs in this folder describe the
recipe; the data stays under `DATA_PIPELINE_DATA_ROOT`.
