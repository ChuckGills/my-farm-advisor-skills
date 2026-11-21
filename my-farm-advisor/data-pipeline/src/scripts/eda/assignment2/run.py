#!/usr/bin/env python3
"""Run the Assignment 2 field-level EDA.

Examples
--------
    export DATA_PIPELINE_DATA_ROOT=/path/to/runtime
    cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline/src"
    python scripts/eda/assignment2/run.py
    python scripts/eda/assignment2/run.py --category weather --category map

Outputs land in ``$DATA_PIPELINE_DATA_ROOT/data-pipeline/eda/assignment-2``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from eda.assignment2 import boundaries, cdl, field_map, weather  # noqa: E402
from eda.assignment2.common import (  # noqa: E402
    FARMS,
    OUT_ROOT,
    TABLE_DIR,
    load_farm,
    read_csv,
)

CATEGORIES: dict[str, Callable[[list[Any]], dict[str, Any]]] = {
    "boundaries": boundaries.run,
    "cdl": cdl.run,
    "weather": weather.run,
    "map": field_map.run,
}


def _relative(path: str) -> str:
    return str(Path(path).relative_to(OUT_ROOT))


def _manifest(
    data: list[Any],
    selected: list[str],
    results: dict[str, dict[str, Any]],
    *,
    allow_archive: bool,
) -> dict[str, Any]:
    figures = [path for result in results.values() for path in result.get("figures", [])]
    tables = [path for result in results.values() for path in result.get("tables", [])]
    tests: dict[str, Any] = {}
    for result in results.values():
        tests.update(result.get("tests", {}))
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": "assignment-2",
        "output_dir": str(OUT_ROOT.relative_to(OUT_ROOT.parents[2])),
        "allow_archive_fallback": allow_archive,
        "categories": selected,
        "figures": [_relative(path) for path in sorted(figures)],
        "tables": [_relative(path) for path in sorted(tables)],
        "tests": tests,
        "errors": {
            name: result["error"]
            for name, result in results.items()
            if result.get("error")
        },
        "farms": [
            {
                "grower": farm.meta.grower,
                "farm": farm.meta.farm,
                "label": farm.meta.label,
                "fields": int(len(farm.boundaries)) if farm.boundaries is not None else 0,
                "cdl_source": farm.cdl.source if farm.cdl is not None else "missing",
                "cdl_years": farm.cdl.years if farm.cdl is not None else [],
                "weather_fields": len(farm.weather.sources) if farm.weather is not None else 0,
                "weather_archive_fields": (
                    sum(1 for value in farm.weather.sources.values() if value == "archive")
                    if farm.weather is not None
                    else 0
                ),
                "notes": farm.notes,
            }
            for farm in data
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--category",
        action="append",
        choices=["all", *CATEGORIES],
        help="Category to run (repeatable). Defaults to all.",
    )
    parser.add_argument(
        "--allow-archive-fallback",
        action="store_true",
        help=(
            "Use archived previous-sample weather and CDL when the current "
            "reseeded pipeline has not produced data yet"
        ),
    )
    args = parser.parse_args()

    selected = args.category or ["all"]
    if "all" in selected:
        selected = list(CATEGORIES)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    data = [load_farm(meta, allow_archive=args.allow_archive_fallback) for meta in FARMS]

    results: dict[str, dict[str, Any]] = {}
    for name in selected:
        try:
            results[name] = CATEGORIES[name](data)
        except Exception as exc:  # noqa: BLE001 - one category must not kill the run
            results[name] = {
                "error": f"{type(exc).__name__}: {exc}",
                "figures": [],
                "tables": [],
                "tests": {},
            }

    manifest = _manifest(data, selected, results, allow_archive=args.allow_archive_fallback)
    (OUT_ROOT / "data_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    tests = manifest["tests"]
    tests_path = TABLE_DIR / "tests.csv"
    merged = tests
    if len(selected) < len(CATEGORIES) and tests_path.exists():
        # A partial rerun only refreshes its own categories; keep the rest so
        # tests.csv stays a complete record of the last full run.
        previous = read_csv(tests_path) if tests_path.exists() else None
        if previous is not None and {"metric", "value"} <= set(previous.columns):
            merged = {
                **dict(zip(previous["metric"], previous["value"])),
                **tests,
            }
    if merged:
        with tests_path.open("w", encoding="utf-8") as handle:
            handle.write("metric,value\n")
            for key, value in merged.items():
                handle.write(f"{key},{value}\n")

    print(f"Output: {OUT_ROOT}")
    for name in selected:
        result = results[name]
        if result.get("error"):
            print(f"  {name}: SKIPPED - {result['error']}")
            continue
        for figure in result["figures"]:
            print(f"  figure: {_relative(figure)}")
        for table in result["tables"]:
            print(f"  table:  {_relative(table)}")
    print()
    for farm in manifest["farms"]:
        note = " (archive fallback)" if farm["weather_archive_fields"] else ""
        print(
            f"  {farm['label']:10s} fields={farm['fields']:2d} "
            f"cdl={farm['cdl_source']:26s} weather={farm['weather_fields']:2d}{note}"
        )
    for name, error in manifest["errors"].items():
        print(f"  warning: {name}: {error}")
    print(f"  tests: {len(tests)} -> {TABLE_DIR / 'tests.csv'}")


if __name__ == "__main__":
    main()
