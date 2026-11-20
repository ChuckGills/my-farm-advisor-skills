#!/usr/bin/env python3
"""Static geospatial field atlas for the three Assignment 2 farms.

One figure: three grower rows, each with a county-scale location panel and ten
field-footprint insets. Footprints are colored by dominant 2025 CDL crop and use
the repository field-frame contract (local metre frame, auto-rotation, true-north
arrow; scale bar only where axes are stripped).

Outputs
-------
figures/map_01_field_map.png
tables/map_fields.csv
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from lib.field_frame import decorate, frame_for

from .cdl import dominant_crop
from .common import CORN, CROP_COLORS, SOY, TABLE_DIR, FarmData, save_figure

GROUPS = ("Corn", "Soybeans", "Other", "No CDL")


def _crop_group(name: str) -> str:
    if name == CORN:
        return "Corn"
    if name == SOY:
        return "Soybeans"
    if name == "No CDL":
        return "No CDL"
    return "Other"


def map_table(data: list[FarmData], crops: dict[str, str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for farm in data:
        if farm.boundaries is None:
            continue
        projected = farm.boundaries.to_crs("EPSG:5070")
        centroids = projected.geometry.centroid.to_crs(4326)
        for (_, row), point in zip(farm.boundaries.iterrows(), centroids):
            field_id = str(row["field_id"])
            rows.append(
                {
                    "grower": farm.meta.label,
                    "field_id": field_id,
                    "acres": round(float(row["area_acres"]), 2),
                    "lon": round(float(point.x), 6),
                    "lat": round(float(point.y), 6),
                    "dominant_crop_2025": crops.get(field_id, "No CDL"),
                }
            )
    return pd.DataFrame(rows)


def _plot_overview(ax: plt.Axes, farm: FarmData, crops: dict[str, str]) -> None:
    frame = frame_for(
        farm.boundaries.to_crs(4326),
        panel_h_in=3.2,
        panel_w_in=2.6,
        scale_len=0.0,
        force_rot=0.0,
    )
    framed = frame.geometry.copy()
    framed["crop_group"] = [_crop_group(crops.get(str(fid), "No CDL")) for fid in framed["field_id"]]
    for group in GROUPS:
        subset = framed[framed["crop_group"] == group]
        if subset.empty:
            continue
        subset.plot(ax=ax, color=CROP_COLORS[group], edgecolor="#1f2937", linewidth=1.4, zorder=2)
    decorate(ax, frame, arrow_r=0.085, arrow_fs=9, callout=False)
    ax.set_aspect("equal")
    ax.margins(0.06)
    ax.set_xlabel("metres east", fontsize=8)
    ax.set_ylabel("metres north", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_facecolor("#fafaf8")
    ax.set_title(
        f"{farm.meta.label} - {farm.meta.county} County, {farm.meta.state}\n"
        f"{len(framed)} fields - {framed['area_acres'].sum():,.0f} ac",
        loc="left",
        fontweight="bold",
        fontsize=10.5,
    )


def _scale_bar(ax: plt.Axes) -> None:
    """Scale bar pinned to the lower-left margin, legible over any fill.

    A white outline under the bar and text keeps it readable when the polygon
    reaches the panel edge, which is common for narrow or L-shaped fields. The
    bar length adapts to the panel so small fields do not get a bar as long as
    the field itself.
    """
    from matplotlib import patheffects

    x_span = float(ax.get_xlim()[1] - ax.get_xlim()[0]) or 1.0
    length = min(
        (candidate for candidate in (1000.0, 500.0, 250.0, 200.0, 100.0, 50.0)
         if candidate / x_span <= 0.40),
        default=50.0,
        key=lambda candidate: -candidate,
    )
    frac = length / x_span
    left, y = 0.06, 0.055
    line = ax.plot(
        [left, left + frac],
        [y, y],
        transform=ax.transAxes,
        color="#111827",
        lw=2.4,
        solid_capstyle="butt",
        zorder=20,
        clip_on=False,
    )[0]
    line.set_path_effects([patheffects.withStroke(linewidth=4.5, foreground="white")])
    label = ax.text(
        left + frac / 2,
        y,
        f"{length:.0f} m",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=6.6,
        color="#111827",
        zorder=21,
        bbox={"boxstyle": "square,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.92},
    )
    label.set_path_effects([patheffects.withStroke(linewidth=1.2, foreground="white")])


def _plot_field(ax: plt.Axes, field: Any, label: str, crop: str, acres: float) -> None:
    frame = frame_for(
        field.to_crs(4326),
        panel_h_in=1.5,
        panel_w_in=1.9,
        scale_len=200.0,
    )
    color = CROP_COLORS[_crop_group(crop)]
    frame.geometry.plot(ax=ax, color=color, edgecolor="#1f2937", linewidth=1.1, zorder=2)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.margins(0.12)
    decorate(ax, frame, arrow_r=0.075, arrow_fs=7.5, callout=False, scalebar=False, arrow_xy=(0.89, 0.86))
    _scale_bar(ax)
    ax.set_title(f"{label} - {acres:.0f} ac\n{crop}", fontsize=8, pad=3.5)


def figure_map(data: list[FarmData]) -> plt.Figure:
    usable = [farm for farm in data if farm.boundaries is not None]
    if not usable:
        raise RuntimeError("No boundary data available for any farm")

    crops = dominant_crop(usable, 2025)
    fig = plt.figure(figsize=(15.5, 13.2))
    grid = fig.add_gridspec(
        len(usable) * 2,
        6,
        width_ratios=(1.5, 1, 1, 1, 1, 1),
        hspace=0.90,
        wspace=0.22,
    )

    for row_index, farm in enumerate(usable):
        _plot_overview(fig.add_subplot(grid[row_index * 2 : row_index * 2 + 2, 0]), farm, crops)
        fields = farm.boundaries.sort_values("field_id").reset_index(drop=True)
        for position in range(len(fields)):
            field = fields.iloc[[position]]
            field_id = str(field["field_id"].iloc[0])
            label = f"{farm.meta.short}-{position + 1:02d}"
            ax = fig.add_subplot(
                grid[row_index * 2 + position // 5, 1 + position % 5]
            )
            _plot_field(
                ax,
                field,
                label,
                crops.get(field_id, "No CDL"),
                float(field["area_acres"].iloc[0]),
            )

    handles = [plt.Rectangle((0, 0), 1, 1, color=CROP_COLORS[group]) for group in GROUPS]
    fig.suptitle(
        "Assignment 2 field atlas - 30 fields across three growers",
        x=0.01,
        y=0.995,
        ha="left",
        fontsize=14,
        fontweight="bold",
    )
    fig.text(
        0.01,
        0.972,
        "Left panel: true field positions at county scale. Right insets: each field boundary, "
        "auto-rotated to its long edge, with north arrow and an adaptive scale bar.",
        ha="left",
        va="top",
        fontsize=8.8,
        color="#555555",
    )
    fig.legend(
        handles,
        GROUPS,
        loc="lower center",
        ncol=4,
        frameon=False,
        fontsize=9.5,
        title="Dominant CDL crop, 2025",
        title_fontsize=9.5,
        bbox_to_anchor=(0.5, 0.012),
    )
    fig.tight_layout(rect=(0, 0.055, 1, 0.945))
    return fig


def run(data: list[FarmData]) -> dict[str, Any]:
    usable = [farm for farm in data if farm.boundaries is not None]
    if not usable:
        raise RuntimeError("No boundary data available for any farm")

    crops = dominant_crop(usable, 2025)
    figure = save_figure(figure_map(usable), "map_01_field_map.png")

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    table = map_table(usable, crops)
    table.to_csv(TABLE_DIR / "map_fields.csv", index=False)

    mapped = int((table["dominant_crop_2025"] != "No CDL").sum())
    return {
        "figures": [str(figure)],
        "tables": [str(TABLE_DIR / "map_fields.csv")],
        "tests": {
            "map.fields": int(len(table)),
            "map.fields_with_2025_cdl": mapped,
        },
    }
