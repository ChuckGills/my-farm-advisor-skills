# Provenance

## grower-web-map

- source_repo: local to this fork (`ChuckGills/my-farm-advisor-skills`)
- source_local_path: `my-farm-advisor/data-pipeline/grower-web-map/`
- source_ref: `assignment-1`
- source_commit: authored on branch `assignment-1`
- source_status: new local subskill, no upstream import
- source_path: N/A (authored, not imported)
- destination_path: `my-farm-advisor/data-pipeline/grower-web-map/`
- import_date: 2026-11-11
- exclusions: no vendored JavaScript, no basemap tiles, no generated HTML,
  no runtime manifests, no field polygons
- external_runtime_dependencies:
  - Leaflet `1.9.4` loaded from `https://unpkg.com/leaflet@1.9.4/` (CDN, not vendored)
  - ESRI World Imagery and World Boundaries and Places tiles loaded from
    `https://server.arcgisonline.com/ArcGIS/rest/services/` (online, keyless, not vendored)
- local_modifications: New subskill authored for Assignment 1. It reuses the
  data-pipeline runtime contract (`lib/runtime_paths.py`, `lib/paths.py`) and
  the existing boundary, inventory, and farm metadata outputs. The generator is
  code-only; every map is a runtime artifact under
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/` and is never committed.

## Update procedure

1. Change `data-pipeline/src/scripts/render_grower_web_map.py` or the docs in
   this folder.
2. Refresh the runtime source copy from the checkout:
   `./scripts/install.sh --non-interactive --force-refresh --no-install-deps`.
3. Re-run the generator for the affected growers and check the HTML size,
   field counts, popup metadata, and the written manifest.
4. Run `./scripts/validate.sh` from the repository root.
5. Update this provenance record if the external asset versions or basemap
   providers change.
