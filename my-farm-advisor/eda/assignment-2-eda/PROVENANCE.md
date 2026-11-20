# Provenance

## What this skill contains

Docs and a pointer to one generator script. No data, no figures, and no copied
third-party code are stored in this repository.

| Item | Location | Origin |
|---|---|---|
| Generator | `data-pipeline/src/scripts/eda/assignment2_eda.py` | Written for this repository |
| Runtime outputs | `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment-2/` | Generated locally, untracked |
| Docs | `eda/assignment-2-eda/` | Written for this repository |

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

All metrics are computed in the generator, from the layers above:

- **Area, perimeter, compactness** - EPSG:5070 equal-area projection;
  compactness is Polsby-Popper `4*pi*A/P^2`.
- **Corn and soybean share** - field pixels by CDL class, pixel-weighted,
  excluding `No Data` and `Unknown`.
- **Crop diversity** - Shannon entropy of pooled CDL class shares per field.
- **GDD** - daily `(Tmax+Tmin)/2`, base 10 °C, cap 30 °C, summed Apr 1-Oct 31.
- **Statistical tests** - SciPy `kruskal` for three-group comparisons,
  `spearmanr` for monotonic association.

## Reproduction

See [GUIDE.md](GUIDE.md). Runs are reproducible from the runtime data alone; the
manifest records the timestamp, per-farm coverage, CDL source window, and any
archived previous-sample fallback used.

## License

Apache-2.0. Upstream data remains subject to its own terms: OSM data under
ODbL, CDL as a U.S. Government work, NASA POWER data under NASA's open data
policy.
