# Assignment 2 Field-Level EDA

Ten static figures and tidy statistics tables that compare the Assignment 2
dataset from four angles:

| Grower | Farm | County | Fields |
|---|---|---|---:|
| `il-corn-grower` | `il-corn-grower-illinois` | Iroquois, IL | 10 |
| `ia-corn-grower` | `ia-corn-grower-iowa` | Kossuth, IA | 10 |
| `ne-corn-grower` | `ne-corn-grower-nebraska` | York, NE | 10 |

Each statistical category answers the same three questions: what happens
**inside a field over time**, how do **fields within a grower** differ, and how
do **growers** differ from each other. Categories are independent, so a missing
layer only removes that category's figures.

## Output layout

All outputs are written under
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment-2/`:

```text
figures/     ten PNGs, one visualization per file
tables/      per-field, per-field-year, monthly, and summary CSVs
data_manifest.json
```

One figure per visualization is deliberate: each PNG can be dropped into a
report or slide on its own, without reading a composite panel grid.

## Boundaries (`--category boundaries`)

| Figure | Question | View |
|---|---|---|
| `boundaries_01_acreage_by_grower.png` | How big are fields in each grower? | Log-scale box plot with jittered field points |
| `boundaries_02_compactness_ecdf.png` | Do growers differ in field shape? | Compactness ECDFs, Kruskal-Wallis p-value |
| `boundaries_03_size_vs_shape.png` | Does field size explain shape? | Compactness vs. area scatter with Spearman rho |

Compactness is the Polsby-Popper score `4 * pi * area / perimeter^2`, computed
in EPSG:5070 metres, so `1.0` is a circle and lower values are more elongated
or irregular. The size-vs-shape figure is deliberately phrased as a test: with
ten fields per grower a visual trend is not a relationship, so the annotation
carries rho, p, and the cross-grower Kruskal-Wallis results.

Tables: `boundaries_fields.csv` (one row per field) and
`boundaries_summary.csv` (one row per grower).

## CDL / cropland (`--category cdl`)

| Figure | Question | View |
|---|---|---|
| `cdl_01_rotation_heatmap.png` | How does corn share vary by field and year? | Field x year heat map, rows grouped by grower |
| `cdl_02_crop_acres_by_grower_year.png` | What is each grower planting over time? | Stacked corn/soybean/other acres per year, one panel per grower |
| `cdl_03_size_vs_diversity.png` | Does field size explain crop diversity? | Distinct crop classes (or Shannon fallback) vs. area, Spearman rho |

Shares are pixel-weighted by CDL class inside each field, so partial-field
classes are represented honestly. `No Data` and `Unknown` classes are dropped
before shares are computed. A crop class counts toward diversity only when it
covers at least 5 % of the field-year; if the distinct-class count has no
variation the figure falls back to Shannon entropy.

Tables: `cdl_field_year.csv` (one row per field-year with acre splits) and
`cdl_summary.csv` (one row per grower).

## Weather (`--category weather`)

| Figure | Question | View |
|---|---|---|
| `weather_01_gdd_precip_by_year.png` | How do heat and rainfall vary by year and field? | Field lines plus grower means, GDD and rainfall side by side |
| `weather_02_monthly_profile.png` | What does the season look like month by month? | Monthly temperature and rainfall, grower mean with field range band |
| `weather_03_grower_comparison.png` | Do growers differ in season totals? | Box plots with Kruskal-Wallis p and eta-squared |

GDD uses `(Tmax + Tmin) / 2`, base `10 °C`, cap `30 °C`, summed over April 1 to
October 31. A field-year is kept only when the season has at least 180 days of
daily records, and a field needs at least 300 daily rows to enter the analysis.
The comparison figure reports eta-squared because a significant p-value alone
does not say how much of the spread grower membership explains.

Tables: `weather_field_year.csv`, `weather_monthly.csv`, `weather_summary.csv`.

## Field atlas (`--category map`)

`map_01_field_map.png` is a three-row atlas. Each row has a county-scale
overview of the grower's fields plus ten field-footprint insets colored by the
dominant 2025 CDL crop. Insets follow the repository field-frame contract:
local metre frame, auto-rotation to the long edge, true-north arrow, and an
adaptive scale bar where axes are stripped. Unmapped fields fall back to a
neutral `No CDL` color rather than disappearing.

Table: `map_fields.csv` (field centroid, acres, dominant 2025 crop).

## Statistics

`tables/tests.csv` and the manifest `tests` block record:

- Boundary acreage and compactness Kruskal-Wallis p-values across growers.
- Size-vs-compactness Spearman rho and p.
- Corn-share Kruskal-Wallis p across growers.
- Size-vs-diversity Spearman rho and p (plus which diversity metric was used).
- GDD and precipitation Kruskal-Wallis p and eta-squared across growers.
- Map field count and how many fields have a 2025 CDL class.

## Data requirements and degradation

- **Boundaries gate the run.** No boundary file for any grower means no figures;
  boundaries are needed for field ids, areas, and the map.
- **CDL and weather are optional per grower.** A missing table, an unreadable
  CSV, or a short weather series is skipped and logged; the remaining growers
  still plot.
- **Reseed detection.** A CDL table is treated as current only when it covers at
  least half the current fields (minimum two). Otherwise it is labelled
  `previous-sample`, or skipped when fallback is disabled.
- **Archive fallback.** `--allow-archive-fallback` lets the run borrow
  previous-sample weather and CDL from `farms/<farm>/archive/` while a reseeded
  pipeline is still running. Figures and manifest say so explicitly.

## Non-goals

- No soil, terrain, or SSURGO analysis.
- No dashboards, HTML, or interactive output.
- No downloads, re-projections, or writes into farm data.
- No report generation; the Assignment 2 report is a separate artifact.

## See also

- [GUIDE.md](GUIDE.md) - commands and verification.
- [PROVENANCE.md](PROVENANCE.md) - sources and generation record.
- [`../INDEX.md`](../INDEX.md) - the other EDA guides.
