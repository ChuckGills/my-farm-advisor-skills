# Assignment 2 Field-Level EDA

Nine static figures, one PDF report, and tidy statistics tables that compare the
Assignment 2 dataset from four angles:

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
figures/            nine PNGs, one visualization per file
tables/             per-field, per-field-year, and summary CSVs
assignment2_report.pdf   single-file report built from the tables and figures
data_manifest.json
```

One figure per visualization is deliberate: each PNG stands on its own. The PDF
is the presentation layer and is built by a separate command, so the reusable
EDA contract stays "figures plus tables".

## Read this first

`assignment2_report.pdf` is nine pages: a ranked summary, a county map, one page
per finding, and a methods page. Page order and the cover table follow evidence
strength, strongest first. Every number in the text is recomputed from the CSVs,
so the prose cannot drift from the data.

## Boundaries (`--category boundaries`)

| Figure | Question | View |
|---|---|---|
| `boundaries_01_acreage_by_grower.png` | How big are fields in each grower? | Log-scale box plot with jittered field points |
| `boundaries_02_compactness_ecdf.png` | Do growers differ in field shape? | Compactness ECDFs, Kruskal-Wallis p-value |
| `boundaries_03_size_vs_shape.png` | Does field size explain shape? | Compactness vs. area scatter with Spearman rho |

Compactness is the Polsby-Popper score `4 * pi * area / perimeter^2`, computed
in EPSG:5070 metres, so `1.0` is a circle and lower values are more elongated
or irregular. With ten fields per grower a visual trend is not a relationship,
so the annotation carries rho, p, and the cross-grower Kruskal-Wallis results.

Tables: `boundaries_fields.csv` (one row per field) and
`boundaries_summary.csv` (one row per grower).

## CDL / cropland (`--category cdl`)

| Figure | Question | View |
|---|---|---|
| `cdl_01_rotation_grid.png` | Which crop dominates each field each year? | Three 10-field grids (one per grower), cells coloured by dominant CDL class |
| `cdl_02_crop_share_by_grower_year.png` | How is each grower's cropland split? | 100 % stacked shares per grower-year, absolute acres above bars |
| `cdl_03_rotation_vs_size.png` | Does field size explain rotation? | Years in corn vs. area, plus median by size quartile |

The rotation grid is categorical on purpose: corn, soybean, other and no-CDL
each get one fixed colour, and a hollow dot marks a field-year where no single
class reaches 80 %. Shares are pixel-weighted by CDL class inside each field, so
partial-field classes are represented honestly; `No Data` and `Unknown` classes
are dropped before shares are computed.

Rotation intensity is "years in corn out of five", because the distinct-class
count saturates at one or two and carries no signal.

Tables: `cdl_field_year.csv` (one row per field-year with acre splits),
`cdl_field_stats.csv` (one row per field: acres, years in each crop, switches),
and `cdl_summary.csv` (one row per grower).

## Weather (`--category weather`)

| Figure | Question | View |
|---|---|---|
| `weather_01_gdd_precip_by_year.png` | How do heat and rainfall vary by year? | Grower mean lines with a band spanning distinct grid cells, GDD and rainfall side by side |
| `weather_02_monthly_profile.png` | What does the season look like month by month? | Monthly temperature and rainfall, grower mean with field range band |
| `weather_03_grower_comparison.png` | Do growers differ in season totals? | Box plots of distinct cell-years, year-blocked Friedman test in the title |

GDD uses `(Tmax + Tmin) / 2`, base `10 °C`, cap `30 °C`, summed over April 1 to
October 31. A field-year is kept only when the season has at least 180 days of
daily records, and a field needs at least 300 daily rows to enter the analysis.

**Grid-cell sharing matters.** NASA POWER serves one series per grid cell, so
most fields in a grower share an identical daily series. Testing on 150
field-years would treat copies as independent replicates. The run therefore
collapses fields to distinct cell-years (nine cells across the three growers)
and tests growers with years as blocks. The figures label the real `n`.

Tables: `weather_field_year.csv` (all field-years, including duplicates),
`weather_grower_year.csv` (grower-year means and cell counts),
`weather_monthly.csv`, and `weather_summary.csv`.

## Field atlas (`--category map`)

`map_01_field_map.png` is a three-row atlas. Each row has a county-scale
overview of the grower's fields plus ten field-footprint insets colored by the
dominant 2025 CDL crop. Insets follow the repository field-frame contract:
local metre frame, auto-rotation to the long edge, true-north arrow, and an
adaptive scale bar. Unmapped fields fall back to a neutral `No CDL` color.

The PDF report draws its own compact county overview (one panel per grower,
counties from the shared geoadmin parquet) because the full atlas is not legible
at page size.

Table: `map_fields.csv` (field centroid, acres, dominant 2025 crop).

## Statistics

`tables/tests.csv` and the manifest `tests` block record:

- Boundary acreage and compactness Kruskal-Wallis p-values across growers.
- Size-vs-compactness Spearman rho and p.
- Corn-share and years-in-corn Kruskal-Wallis p across growers.
- Size-vs-years-in-corn Spearman rho and p.
- GDD and precipitation year-blocked Friedman p, grower eta-squared on
  cell-years, and the supporting cell-level Kruskal-Wallis p.
- Effective sample sizes: weather cells, cell-years, field-years.
- Map field count and how many fields have a 2025 CDL class.

The PDF applies Holm correction within each question family (boundaries,
weather, rotation) and prints both raw and adjusted p-values. Under one global
family of all eight tests nothing reaches 0.05; the methods page says so.

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
- **Partial reruns.** `--category X` refreshes only that category's figures and
  tests; `tests.csv` keeps the other categories' last results.

## Non-goals

- No soil, terrain, or SSURGO analysis.
- No dashboards, HTML, or interactive output.
