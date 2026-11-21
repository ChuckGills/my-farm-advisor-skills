# Provenance

## What this skill contains

Docs and a pointer to one generator package. No data, no figures, and no copied
third-party code are stored in this repository.

| Item | Location | Origin |
|---|---|---|
| Generator package | `data-pipeline/src/scripts/eda/assignment2/` | Written for this repository |
| Shared plotting/statistics | `.../assignment2/common.py` | Written for this repository |
| Field-frame helpers | `data-pipeline/src/scripts/lib/field_frame.py` | Existing repository helper, reused by the map |
| Runtime outputs | `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment-2/` | Generated locally, untracked |
| Docs | `eda/assignment-2-eda/` | Written for this repository |

Package modules (nine figures plus the PDF):

| Module | Responsibility |
|---|---|
| `common.py` | Runtime loaders, degradation rules, styling, statistics, figure saving |
| `boundaries.py` | Acreage, compactness, size-vs-shape |
| `cdl.py` | Rotation grid, crop share, rotation vs. size |
| `weather.py` | Annual series, monthly profile, grower comparison |
| `field_map.py` | Field atlas and map table |
| `run.py` | CLI, category dispatch, manifest and `tests.csv` |
| `report.py` | Single-file PDF report built from the tables and figures |

## Upstream data sources

The EDA does not download anything. It reads what the My Farm Advisor data
pipeline already produced.

| Layer | Source | Produced by |
|---|---|---|
| Field boundaries | OpenStreetMap / Overpass, `landuse=farmland`, clipped to county | `bootstrap_farm_from_county.py`, `download_boundaries.py` |
| CDL/cropland classes | USDA NASS Cropland Data Layer, `nassgeodata.gmu.edu` by-FIPS GeoTIFFs | `download_cdl.py` |
| Daily weather | NASA POWER (T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, ALLSKY_SFC_SW_DWN, RH2M, WS10M) | `download_weather.py` |

Dataset selection, county choices, sampling seed, and the 2021-2025 CDL window
are recorded in
[`../../data-pipeline/docs/assignment-2-dataset.md`](../../data-pipeline/docs/assignment-2-dataset.md).

## Derived metrics

All metrics are computed in the package, from the layers above:

- **Area, perimeter, compactness** - EPSG:5070 equal-area projection;
  compactness is Polsby-Popper `4*pi*A/P^2`.
- **Corn and soybean acres and shares** - field pixels by CDL class, pixel
  weighted at 30 m resolution, excluding `No Data` and `Unknown`.
- **Dominant crop** - CDL class with the largest pixel share in a field-year;
  a field-year is flagged as mixed when no class reaches 80 %.
- **Rotation intensity** - years in corn out of the CDL window, and the number
  of dominant-crop switches. Distinct-class counts saturate at one or two and
  are kept only as a CSV column.
- **GDD** - daily `(Tmax+Tmin)/2`, base 10 °C, cap 30 °C, summed Apr 1-Oct 31
  for field-years with at least 180 season days.
- **Statistical tests** - SciPy `kruskal` for three-group field-level
  comparisons, `friedmanchisquare` with years as blocks for weather (fields in
  one NASA POWER cell are not independent), `spearmanr` for monotonic
  association, and a one-way eta-squared computed from group means.
- **Multiple comparisons** - Holm step-down adjustment within each question
  family (boundaries, weather, rotation); `report.py` prints raw and adjusted
  p-values and also states the stricter all-eight-test result.

## Reproduction

See [GUIDE.md](GUIDE.md). Runs are reproducible from the runtime data alone; the
manifest records the timestamp, per-farm coverage, CDL source window, weather
field counts, and any archived previous-sample fallback used.

## License

Apache-2.0. Upstream data remains subject to its own terms: OSM data under
ODbL, CDL as a U.S. Government work, NASA POWER data under NASA's open data
policy.
