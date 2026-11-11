# Grower Web Map Guide

## Prerequisites

- A runtime initialized by `data-pipeline/scripts/install.sh`.
- At least one grower with downloaded boundaries under
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`.
- `DATA_PIPELINE_DATA_ROOT` exported in the current shell.

The seeded Assignment 1 growers are `il-corn-grower` (Illinois Corn Farm,
Iroquois County, 3 fields) and `ia-corn-grower` (Iowa Corn Farm, Kossuth
County, 3 fields).

## Install the generator into the runtime

The installer copies the committed `src/` tree into the runtime. From the
checkout's data-pipeline folder:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive --force-refresh --no-install-deps
```

`--no-install-deps` skips the venv rebuild because the runtime environment
already exists. Drop it on a fresh machine.

## Run the map

From the runtime source copy, with the runtime Python:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
PY="$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python"
cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline/src"

# One grower
"$PY" scripts/render_grower_web_map.py --grower il-corn-grower

# Both Assignment 1 growers
"$PY" scripts/render_grower_web_map.py --grower il-corn-grower --grower ia-corn-grower

# Every grower in the runtime
"$PY" scripts/render_grower_web_map.py --all-growers
```

The script prints one line per grower and a JSON summary. It exits nonzero if
a named grower does not exist.

## Outputs

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/reports/grower_web_map.html
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/manifests/grower_web_map.json
```

Open the HTML in a browser. The map fits all of the grower's fields on load;
use the sidebar to fly to a field, and click any polygon for its metadata.

## Verify

Check that each output is small and complete:

```bash
for g in il-corn-grower ia-corn-grower; do
  f="$DATA_PIPELINE_DATA_ROOT/data-pipeline/growers/$g/derived/reports/grower_web_map.html"
  printf '%s: %s bytes, %s field features\n' "$g" "$(stat -c%s "$f")" \
    "$(grep -o '"type":"Feature"' "$f" | wc -l)"
done
```

Expected for the seeded growers: three field features per map and a file well
under 100 KB. The manifest's `inputs` array should list the boundary path and
sha256 for each farm.

## Notes and failure modes

- **No basemap tiles**: Leaflet and ESRI tiles load over HTTPS at view time.
  A firewall or offline session shows the polygons on a blank canvas; the
  popups and field list still work.
- **Grower not found**: confirm the slug under
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/`.
- **Farm skipped**: the farm has no `boundary/field_boundaries.geojson`; run
  the data pipeline or `download_fields.py` for that farm first.
- **Field names**: the sidebar and popup use the inventory `field_slug`; when
  it is an OSM id that id is the field name.
- **Determinism**: polygons, colors, ordering, and counts are deterministic
  for a given runtime snapshot. The manifest records `generated_at` and input
  hashes; the HTML itself is regenerated on every run.
- **Figure policy**: this skill writes an interactive HTML artifact only. It
  does not add or change gallery figures, so the static figure quality gate
  does not apply.
