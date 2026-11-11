# Grower Web Map

A lightweight grower-level interactive map for My Farm Advisor. For each
grower it renders one self-contained HTML file that shows every field the
data pipeline has already downloaded, over an online satellite basemap.

## What it renders

- **All fields for the grower**, aggregated across the grower's farms, using
  the real `boundary/field_boundaries.geojson` polygons written by
  `ingest/download_fields.py`.
- **ESRI World Imagery** tiles as the satellite basemap, plus an optional
  ESRI place-label overlay. Both load from the internet at view time and need
  no API key.
- **Zoom and pan** with Leaflet's standard controls, starting fitted to the
  grower's full field extent.
- **Click a field** for a popup with grower, farm, field name, county, area,
  and the boundary's crop layer.
- **Field list sidebar** that flies to a field and opens its popup when clicked.
- **Farm color legend** so multi-farm growers stay readable.

## Output contract

| Purpose | Template |
| --- | --- |
| Map HTML | `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/reports/grower_web_map.html` |
| Run manifest | `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/manifests/grower_web_map.json` |

The manifest records the input boundary paths and sha256 hashes, field and
farm counts, total acres, the output path and byte size, the Leaflet version,
and the basemap URLs.

## Size policy

The HTML embeds only field polygons with coordinates rounded to five decimal
places (about one metre), so a three-field farm adds only a few kilobytes.
Rasters, NDVI tiles and downloaded imagery are never embedded. The files for
the seeded Illinois and Iowa growers are tens of kilobytes, not megabytes.

## Requirements

- `DATA_PIPELINE_DATA_ROOT` pointing at the runtime root.
- The runtime Python environment (the installer creates it) with geopandas.
- Internet access at view time for Leaflet and the ESRI basemap. The map is
  still a valid HTML file without connectivity; the polygons render on a blank
  background and tiles fill in when the network returns.

No new Python dependencies are required, and no JavaScript assets are vendored
into this repository.

## How it works

`src/scripts/render_grower_web_map.py` discovers each farm under the grower,
reads its boundary and `farm.json` display name, joins field slugs from
`manifests/field-inventory.csv`, builds a GeoJSON FeatureCollection with the
map metadata, and writes the HTML plus manifest. See [GUIDE.md](GUIDE.md) for
the exact commands.
