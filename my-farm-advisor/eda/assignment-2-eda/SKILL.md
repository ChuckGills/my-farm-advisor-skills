---
name: assignment-2-eda
description: >
  Field-level EDA for the Assignment 2 dataset (IL/IA/NE growers, ten fields
  each). Produces static figures and tidy statistics for field boundaries,
  CDL/cropland rotation, and weather comparisons within and across growers.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "0.1.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "0.1.0"
---

# Assignment 2 Field-Level EDA

Read-only EDA over the Assignment 2 runtime dataset. One Python script writes
three static figures plus statistics tables; there is no dashboard, no new
ingestion, and no soil analysis.

## Start Here

- [README.md](README.md) - what each panel shows and how to read it.
- [GUIDE.md](GUIDE.md) - install, run, verify, and troubleshoot.
- [PROVENANCE.md](PROVENANCE.md) - upstream data sources and generation record.

Generator lives beside the pipeline scripts:
`data-pipeline/src/scripts/eda/assignment2_eda.py`.

Outputs land in `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment-2/`:
`assignment2_boundaries.png`, `assignment2_cdl.png`,
`assignment2_weather.png`, matching `*_stats.csv` files, and
`data_manifest.json`. Nothing is committed.

## Routing Notes

- Use when the request asks for cross-grower or cross-field comparison of
  boundaries, CDL/cropland, or weather for the Assignment 2 growers.
- The generator reads existing pipeline outputs only; missing layers degrade to
  a note in the manifest instead of a crash.
- For single-dataset exploration, prefer the generic EDA guides in
  [`../INDEX.md`](../INDEX.md).
- Soil, terrain, and report generation are out of scope here.
