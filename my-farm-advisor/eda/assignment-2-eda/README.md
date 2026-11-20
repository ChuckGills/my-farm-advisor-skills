# Assignment 2 Field-Level EDA

Three static figures and three statistics tables that compare the Assignment 2
dataset from three angles:

| Grower | Farm | County | Fields |
|---|---|---|---:|
| `il-corn-grower` | `il-corn-grower-illinois` | Iroquois, IL | 10 |
| `ia-corn-grower` | `ia-corn-grower-iowa` | Kossuth, IA | 10 |
| `ne-corn-grower` | `ne-corn-grower-nebraska` | York, NE | 10 |

Each category answers the same three questions: what happens **inside a field
over time**, how do **fields within a grower** differ, and how do **growers**
differ from each other.

## Figures

All figures are written to
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment-2/`.

### 1. `assignment2_boundaries.png`

| Panel | Question | View |
|---|---|---|
| A | How big are the fields in each grower? | Box plot with jittered points, log acres |
| B | Does field size explain shape? | Compactness vs. area scatter, Spearman rho |
| C | Do growers differ in field shape? | Compactness ECDFs, Kruskal-Wallis |

Compactness is the Polsby-Popper score `4 * pi * area / perimeter^2`, computed
in EPSG:5070 metres, so `1.0` is a circle and lower values are more elongated
or irregular. Panel B is deliberately phrased as a test: with ten fields per
grower a visual trend is not a relationship, so the title carries the rho and
p-value.

### 2. `assignment2_cdl.png`

| Panel | Question | View |
|---|---|---|
| A | How does crop rotation vary within a field? | Corn share heat map, field x year |
| B | How diverse is each field's crop history? | Shannon diversity across CDL classes |
| C | Do growers differ in corn intensity? | Field-level corn share, Kruskal-Wallis |

Shares are pixel-weighted by CDL class inside each field, so partial-field
classes are represented honestly. `No Data` and `Unknown` classes are dropped
before shares are computed. Panel A is the only true within-field time view in
this figure; panels B and C pool years to compare fields and growers.

### 3. `assignment2_weather.png`

| Panel | Question | View |
|---|---|---|
| A | How does growing-season heat vary by year and field? | Annual GDD, thin lines per field, bold grower mean |
| B | How variable is seasonal rainfall? | Growing-season precipitation by grower |
| C | Are heat and rainfall related? | GDD vs. precipitation, Spearman overall and per grower |

GDD uses `(Tmax + Tmin) / 2`, base `10 °C`, cap `30 °C`, summed over April 1 to
October 31 (day-of-year window, not a crop-specific phenology). A field-year is
kept only when the season has at least 180 days of daily records.

## Statistics tables

Each figure has a companion `*_stats.csv` with one row per grower:

- `assignment2_boundaries_stats.csv` - field count, total/median/min/max acres,
  median/min/max compactness.
- `assignment2_cdl_stats.csv` - CDL source and years, field count, median corn
  share, median crop diversity.
- `assignment2_weather_stats.csv` - field and field-year counts, GDD mean/sd,
  precipitation mean/sd, per-grower Spearman rho and p-value.

`data_manifest.json` records the run timestamp, figure names, per-farm field
counts, CDL source, weather field counts, archived-field fallbacks, and all
degradation notes.

## Data requirements and degradation

- **Boundaries are required.** No boundary file means the run stops; the other
  two figures cannot be built without field ids.
- **CDL and weather are optional.** A missing table, an unreadable CSV, or a
  weather series shorter than 300 rows is skipped and logged.
- **Reseed detection.** A CDL table is treated as current only when it covers at
  least half the current fields (minimum two). Otherwise the table is labelled
  `previous-sample`, or skipped when fallback is disabled.
- **Archive fallback.** `--allow-archive-fallback` lets the script borrow
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
