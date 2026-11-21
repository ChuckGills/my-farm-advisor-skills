---
name: grower-web-map
description: >
  Grower-level interactive web map for My Farm Advisor. Use when a request
  needs a lightweight, browsable HTML map of every field a grower has, built
  from the data pipeline's downloaded field boundaries over an online
  satellite basemap.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "0.1.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "0.1.0"
---

# Grower Web Map

Use this nested skill to render one small interactive HTML map per grower from
the field polygons the data pipeline already downloaded. The map shows every
field for the grower over ESRI World Imagery, supports zoom/pan, and opens a
popup with grower, farm, and field metadata.

## Start Here

- Read [README.md](README.md) for the output contract, runtime paths, and size policy.
- Read [GUIDE.md](GUIDE.md) for install, run, and verification commands.
- Read [PROVENANCE.md](PROVENANCE.md) before changing the generator or its external assets.
- Use `data-pipeline/src/scripts/render_grower_web_map.py` from the installed runtime source copy.

## Routing Notes

- Invoke this skill when the request mentions a grower map, farm map, field
  overview map, interactive field map, web map, or Leaflet view of pipeline fields.
- The generator reads existing runtime outputs only. It does not download
  imagery, create fields, or modify farm data.
- The HTML embeds only rounded field polygons (no rasters, orthomosaics, or
  NDVI tiles) and loads Leaflet plus ESRI tiles from the internet at view time.
- Generated maps belong under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/reports/`
  and stay out of Git.
