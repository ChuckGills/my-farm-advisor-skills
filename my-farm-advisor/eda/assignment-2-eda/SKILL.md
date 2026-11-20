---
name: assignment-2-eda
description: >
  Field-level EDA for the Assignment 2 dataset (IL/IA/NE growers, ten fields
  each). Produces static figures and tidy statistics for field boundaries,
  CDL/cropland rotation, and weather comparisons within and across growers,
  plus a field-location atlas.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "0.2.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "0.2.0"
---

# Assignment 2 Field-Level EDA

Read-only EDA over the Assignment 2 runtime dataset. A small Python package
writes ten static figures plus tidy statistics tables; there is no dashboard,
no new ingestion, and no soil analysis.

## Start Here

- [README.md](README.md) - what each figure shows and how to read it.
- [GUIDE.md](GUIDE.md) - install, run, verify, and troubleshoot.
- [PROVENANCE.md](PROVENANCE.md) - upstream data sources and generation record.

Generator package lives beside the pipeline scripts:
`data-pipeline/src/scripts/eda/assignment2/` (`common`, `boundaries`, `cdl`,
`weather`, `field_map`, `run`).

Outputs land in `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment-2/`:

```text
figures/   10 PNGs, one visualization per file
tables/    per-grower and per-field-year CSVs plus tests.csv
data_manifest.json
```

Nothing is committed.

## Categories

| Category | Command flag | Figures |
|---|---|---|
| Boundaries | `--category boundaries` | acreage, compactness ECDF, size-vs-shape |
| CDL / cropland | `--category cdl` | rotation heat map, crop acreage, size-vs-diversity |
| Weather | `--category weather` | annual GDD/rainfall, monthly profile, grower comparison |
| Map | `--category map` | field atlas (county overview + per-field insets) |

Each statistical category emits two visualizations plus one comparison or
correlation view. The map is the single geospatial output.

## Routing Notes

- Use when the request asks for cross-grower or cross-field comparison of
  boundaries, CDL/cropland, or weather for the Assignment 2 growers.
- Every category reads existing pipeline outputs only; missing layers degrade to
  a note in the manifest and skip just that figure instead of crashing the run.
- For single-dataset exploration, prefer the generic EDA guides in
  [`../INDEX.md`](../INDEX.md).
- Soil, terrain, and report generation are out of scope here.
