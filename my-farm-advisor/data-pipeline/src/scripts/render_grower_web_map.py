#!/usr/bin/env python3
"""Render a lightweight interactive grower web map from pipeline field boundaries.

The map is a single self-contained HTML file per grower. It embeds only the
already-downloaded field polygons (rounded coordinates, no rasters or imagery)
and loads Leaflet plus ESRI World Imagery tiles from the internet at view time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_LOCAL_LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts
sys.path.insert(0, str(_SCRIPTS))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from paths import (  # noqa: E402
    DATA_ROOT,
    GROWERS_ROOT,
    farm_boundary_path,
    farm_manifest_dir,
    grower_dir,
    grower_manifest_dir,
)

LEAFLET_VERSION = "1.9.4"
LEAFLET_CSS = f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.css"
LEAFLET_JS = f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.js"
ESRI_IMAGERY = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
ESRI_LABELS = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
)
ESRI_ATTRIBUTION = (
    "Imagery &copy; Esri, Maxar, Earthstar Geographics | "
    "Labels &copy; Esri"
)
FARM_COLORS = (
    "#e6194b",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#008080",
    "#9a6324",
    "#800000",
)
OUTPUT_NAME = "grower_web_map.html"
MANIFEST_NAME = "grower_web_map.json"
COORD_DECIMALS = 5


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _runtime_relative(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(DATA_ROOT).as_posix()
    except ValueError:
        return str(path)


def _round_coordinates(value: Any, decimals: int = COORD_DECIMALS) -> Any:
    if isinstance(value, float):
        return round(value, decimals)
    if isinstance(value, (list, tuple)):
        return [_round_coordinates(item, decimals) for item in value]
    if isinstance(value, dict):
        return {key: _round_coordinates(item, decimals) for key, item in value.items()}
    return value


def _display_name(raw_slug: str) -> str:
    parts = raw_slug.replace("_", "-").split("-")
    return " ".join(
        part.upper() if len(part) == 2 and part.isalpha() else part.capitalize()
        for part in parts
        if part
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _grower_display_name(grower_path: Path, grower_slug: str) -> str:
    metadata = _read_json(grower_path / "grower.json")
    recorded = str(metadata.get("display_name") or "").strip()
    if recorded and recorded != grower_slug:
        return recorded
    return _display_name(grower_slug)


def _field_slug_lookup(grower_slug: str, farm_slug: str) -> dict[str, str]:
    inventory = farm_manifest_dir(grower_slug, farm_slug) / "field-inventory.csv"
    if not inventory.exists():
        return {}
    try:
        frame = pd.read_csv(inventory)
    except (OSError, ValueError):
        return {}
    if not {"field_id", "field_slug"}.issubset(frame.columns):
        return {}
    return {
        str(row["field_id"]): str(row["field_slug"])
        for _, row in frame[["field_id", "field_slug"]].dropna().iterrows()
    }


def _farm_display_name(farm_path: Path, farm_slug: str) -> str:
    metadata = _read_json(farm_path / "farm.json")
    recorded = str(metadata.get("display_name") or "").strip()
    return recorded or _display_name(farm_slug)


def _collect_grower(grower_slug: str) -> dict[str, Any]:
    grower_path = grower_dir(grower_slug)
    farms_root = grower_path / "farms"
    if not grower_path.is_dir():
        raise SystemExit(f"Grower not found: {grower_slug} ({grower_path})")
    if not farms_root.is_dir():
        raise SystemExit(f"Grower has no farms directory: {farms_root}")

    grower_name = _grower_display_name(grower_path, grower_slug)
    features: list[dict[str, Any]] = []
    farms: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []

    for index, farm_path in enumerate(sorted(p for p in farms_root.iterdir() if p.is_dir())):
        farm_slug = farm_path.name
        boundary = farm_boundary_path(grower_slug, farm_slug)
        if not boundary.exists():
            print(f"  skip {farm_slug}: no boundary at {boundary}")
            continue

        frame = gpd.read_file(boundary)
        if frame.empty or "geometry" not in frame.columns:
            print(f"  skip {farm_slug}: boundary has no geometries")
            continue
        if frame.crs is not None and frame.crs.to_epsg() != 4326:
            frame = frame.to_crs(4326)

        farm_name = _farm_display_name(farm_path, farm_slug)
        color = FARM_COLORS[index % len(FARM_COLORS)]
        slug_lookup = _field_slug_lookup(grower_slug, farm_slug)
        farm_acres = 0.0

        for _, row in frame.iterrows():
            field_id = str(row.get("field_id") or "")
            field_slug = slug_lookup.get(field_id) or field_id
            area_acres = row.get("area_acres")
            try:
                area_value = float(area_acres) if pd.notna(area_acres) else 0.0
            except (TypeError, ValueError):
                area_value = 0.0
            farm_acres += area_value
            geometry = row.get("geometry")
            if geometry is None or geometry.is_empty:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": _round_coordinates(geometry.__geo_interface__),
                    "properties": {
                        "grower": grower_slug,
                        "grower_name": grower_name,
                        "farm_slug": farm_slug,
                        "farm_name": farm_name,
                        "field_id": field_id,
                        "field_slug": field_slug,
                        "field_name": field_slug,
                        "county_name": str(row.get("county_name") or ""),
                        "state_fips": str(row.get("state_fips") or ""),
                        "crop_name": str(row.get("crop_name") or ""),
                        "area_acres": round(area_value, 2),
                        "color": color,
                    },
                }
            )

        farms.append(
            {
                "farm_slug": farm_slug,
                "farm_name": farm_name,
                "color": color,
                "field_count": int(len(frame)),
                "area_acres": round(farm_acres, 2),
            }
        )
        inputs.append(
            {
                "path": _runtime_relative(boundary),
                "sha256": _sha256(boundary),
                "bytes": boundary.stat().st_size,
            }
        )

    total_acres = round(sum(farm["area_acres"] for farm in farms), 2)
    payload = {
        "grower": grower_slug,
        "grower_name": grower_name,
        "farms": farms,
        "summary": {
            "farm_count": len(farms),
            "field_count": len(features),
            "total_acres": total_acres,
        },
        "basemap": {
            "imagery": ESRI_IMAGERY,
            "labels": ESRI_LABELS,
            "attribution": ESRI_ATTRIBUTION,
        },
        "geojson": {"type": "FeatureCollection", "features": features},
    }
    return {"payload": payload, "inputs": inputs}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="__LEAFLET_CSS__">
<style>
  :root { --panel:#111820; --muted:#9fb0c0; --accent:#5bc0eb; }
  html, body { height:100%; margin:0; font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  #layout { display:flex; height:100%; }
  #sidebar { width:290px; flex:0 0 290px; background:var(--panel); color:#eaf1f7;
             display:flex; flex-direction:column; overflow:hidden; }
  #sidebar header { padding:14px 16px 10px; border-bottom:1px solid #22303d; }
  #sidebar h1 { font-size:1.05rem; margin:0 0 4px; }
  #sidebar .sub { color:var(--muted); font-size:.78rem; line-height:1.35; }
  #sidebar .stats { display:flex; gap:14px; margin-top:10px; font-size:.78rem; color:var(--muted); }
  #sidebar .stats b { display:block; color:#fff; font-size:.95rem; }
  #list-wrap { flex:1; overflow:auto; padding:8px 0 16px; }
  #list-wrap h2 { font-size:.7rem; letter-spacing:.08em; text-transform:uppercase;
                  color:var(--muted); margin:10px 16px 6px; }
  #legend { padding:0 16px 10px; font-size:.76rem; color:var(--muted); }
  #legend div { display:flex; align-items:center; gap:8px; margin:3px 0; }
  #field-list { list-style:none; margin:0; padding:0; }
  .field-item { display:grid; grid-template-columns:10px 1fr auto; gap:2px 8px;
                padding:8px 16px; cursor:pointer; border-left:3px solid transparent; }
  .field-item:hover { background:#17222c; }
  .field-item.active { background:#1d2d3a; border-left-color:var(--accent); }
  .swatch { width:10px; height:10px; border-radius:2px; margin-top:3px; grid-row:span 2; }
  .fname { font-size:.84rem; color:#fff; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .facres { font-size:.74rem; color:var(--muted); }
  .ffarm { grid-column:2 / span 2; font-size:.72rem; color:var(--muted); }
  #map { flex:1; min-width:0; }
  .leaflet-popup-content { margin:12px 14px; font-size:.82rem; }
  .leaflet-popup-content table.popup { border-collapse:collapse; margin-top:6px; }
  .leaflet-popup-content table.popup th { text-align:left; color:#5a6b7b; font-weight:600;
                                          padding:2px 10px 2px 0; white-space:nowrap; }
  .leaflet-popup-content table.popup td { padding:2px 0; }
  @media (max-width:720px) {
    #layout { flex-direction:column; }
    #sidebar { width:auto; flex:0 0 auto; max-height:42vh; }
    #map { flex:1; }
  }
</style>
</head>
<body>
<div id="layout">
  <aside id="sidebar">
    <header>
      <h1 id="grower-name">Grower</h1>
      <div class="sub" id="grower-sub">Grower web map</div>
      <div class="stats">
        <span><b id="stat-fields">0</b>fields</span>
        <span><b id="stat-acres">0</b>acres</span>
        <span><b id="stat-farms">0</b>farms</span>
      </div>
    </header>
    <div id="list-wrap">
      <h2>Farms</h2>
      <div id="legend"></div>
      <h2>Fields</h2>
      <ul id="field-list"></ul>
    </div>
  </aside>
  <main id="map"></main>
</div>
<script src="__LEAFLET_JS__"></script>
<script>
const MAP_DATA = __MAP_DATA__;

const map = L.map('map', {zoomControl: true, preferCanvas: true});
const imagery = L.tileLayer(MAP_DATA.basemap.imagery, {
  maxZoom: 19,
  attribution: MAP_DATA.basemap.attribution
}).addTo(map);
const labels = L.tileLayer(MAP_DATA.basemap.labels, {maxZoom: 19, opacity: 0.8}).addTo(map);
L.control.layers(null, {'Place labels': labels}, {collapsed: true}).addTo(map);
L.control.scale({imperial: true, metric: false}).addTo(map);

const layersByKey = {};

function esc(value) {
  return String(value).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
  ));
}

function popupHtml(p) {
  const county = p.county_name ? p.county_name + (p.state_fips ? ', ' + p.state_fips : '') : 'n/a';
  const rows = [
    ['Grower', p.grower_name + ' (' + p.grower + ')'],
    ['Farm', p.farm_name],
    ['Field', p.field_name],
    ['County', county],
    ['Area', Number(p.area_acres).toFixed(1) + ' acres'],
    ['Crop layer', p.crop_name || 'n/a'],
  ];
  return '<strong>' + esc(p.field_name) + '</strong><table class="popup">'
    + rows.map(r => '<tr><th>' + esc(r[0]) + '</th><td>' + esc(r[1]) + '</td></tr>').join('')
    + '</table>';
}

const fieldLayer = L.geoJSON(MAP_DATA.geojson, {
  style: f => ({
    color: f.properties.color, weight: 2,
    fillColor: f.properties.color, fillOpacity: 0.18
  }),
  onEachFeature: (feature, layer) => {
    const p = feature.properties;
    layer.bindPopup(popupHtml(p));
    layer.on('mouseover', () => layer.setStyle({weight: 3, fillOpacity: 0.32}));
    layer.on('mouseout', () => layer.setStyle({weight: 2, fillOpacity: 0.18}));
    layersByKey[p.farm_slug + '/' + p.field_slug] = layer;
  }
}).addTo(map);

if (fieldLayer.getLayers().length) {
  map.fitBounds(fieldLayer.getBounds(), {padding: [30, 30]});
} else {
  map.setView([39.8, -98.5], 3);
}

const growerName = MAP_DATA.grower_name || MAP_DATA.grower;
document.title = growerName + ' field map';
document.getElementById('grower-name').textContent = growerName;
document.getElementById('grower-sub').textContent =
  'Grower ' + MAP_DATA.grower + ' - click a field for details';
document.getElementById('stat-fields').textContent = MAP_DATA.summary.field_count;
document.getElementById('stat-acres').textContent =
  Math.round(MAP_DATA.summary.total_acres).toLocaleString();
document.getElementById('stat-farms').textContent = MAP_DATA.summary.farm_count;

const legend = document.getElementById('legend');
MAP_DATA.farms.forEach(farm => {
  const row = document.createElement('div');
  row.innerHTML = '<span class="swatch" style="background:' + farm.color + '"></span>'
    + '<span>' + esc(farm.farm_name) + ' (' + farm.field_count + ')</span>';
  legend.appendChild(row);
});

const list = document.getElementById('field-list');
MAP_DATA.geojson.features.forEach(feature => {
  const p = feature.properties;
  const key = p.farm_slug + '/' + p.field_slug;
  const item = document.createElement('li');
  item.className = 'field-item';
  item.innerHTML = '<span class="swatch" style="background:' + p.color + '"></span>'
    + '<span class="fname">' + esc(p.field_name) + '</span>'
    + '<span class="facres">' + Number(p.area_acres).toFixed(0) + ' ac</span>'
    + '<span class="ffarm">' + esc(p.farm_name) + '</span>';
  item.addEventListener('click', () => {
    document.querySelectorAll('.field-item.active').forEach(el => el.classList.remove('active'));
    item.classList.add('active');
    const target = layersByKey[key];
    if (!target) return;
    map.fitBounds(target.getBounds(), {padding: [40, 40], maxZoom: 17});
    target.openPopup();
  });
  list.appendChild(item);
});
</script>
</body>
</html>
"""


def _render_html(payload: dict[str, Any]) -> str:
    title = f"{payload['grower_name']} field map"
    map_data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    return (
        HTML_TEMPLATE.replace("__TITLE__", title)
        .replace("__LEAFLET_CSS__", LEAFLET_CSS)
        .replace("__LEAFLET_JS__", LEAFLET_JS)
        .replace("__MAP_DATA__", map_data)
    )


def _write_manifest(
    *,
    grower_slug: str,
    payload: dict[str, Any],
    inputs: list[dict[str, Any]],
    output: Path,
) -> Path:
    manifest_path = grower_manifest_dir(grower_slug) / MANIFEST_NAME
    manifest = {
        "dataset_name": "grower_web_map",
        "status": "complete",
        "generator": "data-pipeline/src/scripts/render_grower_web_map.py",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "grower_slug": grower_slug,
        "grower_name": payload["grower_name"],
        "farm_count": payload["summary"]["farm_count"],
        "field_count": payload["summary"]["field_count"],
        "total_acres": payload["summary"]["total_acres"],
        "output": _runtime_relative(output),
        "output_bytes": output.stat().st_size,
        "leaflet_version": LEAFLET_VERSION,
        "basemap": payload["basemap"],
        "inputs": inputs,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _available_growers() -> list[str]:
    if not GROWERS_ROOT.is_dir():
        return []
    return sorted(p.name for p in GROWERS_ROOT.iterdir() if p.is_dir())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render one lightweight interactive web map per grower."
    )
    parser.add_argument(
        "--grower",
        action="append",
        default=None,
        metavar="SLUG",
        help="Grower slug to render (repeatable). Defaults to every grower.",
    )
    parser.add_argument(
        "--all-growers",
        action="store_true",
        help="Render every grower under the runtime growers root.",
    )
    args = parser.parse_args()

    growers = args.grower or _available_growers()
    if not growers:
        raise SystemExit(f"No growers found under {GROWERS_ROOT}")

    results = []
    for grower_slug in growers:
        collected = _collect_grower(grower_slug)
        payload = collected["payload"]
        output = grower_dir(grower_slug) / "derived" / "reports" / OUTPUT_NAME
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_render_html(payload), encoding="utf-8")
        manifest_path = _write_manifest(
            grower_slug=grower_slug,
            payload=payload,
            inputs=collected["inputs"],
            output=output,
        )
        result = {
            "grower_slug": grower_slug,
            "grower_name": payload["grower_name"],
            "farms": payload["summary"]["farm_count"],
            "fields": payload["summary"]["field_count"],
            "acres": payload["summary"]["total_acres"],
            "html": str(output),
            "html_bytes": output.stat().st_size,
            "manifest": str(manifest_path),
        }
        results.append(result)
        print(
            f"wrote {output} ({result['fields']} fields, "
            f"{result['html_bytes']:,} bytes)"
        )

    print(json.dumps({"status": "complete", "maps": results}, indent=2))


if __name__ == "__main__":
    main()
