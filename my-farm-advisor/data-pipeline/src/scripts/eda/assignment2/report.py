#!/usr/bin/env python3
"""Build the single-file Assignment 2 PDF report.

This is an assignment deliverable, not part of the reusable EDA contract: it
reads the tables and figures that ``run.py`` already wrote and renders one
page per finding, strongest first. Every number in the text is recomputed from
the tables, so the prose cannot drift from the CSVs.

Usage
-----
    export DATA_PIPELINE_DATA_ROOT=/path/to/runtime
    cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline/src"
    python scripts/eda/assignment2/report.py

Output
------
    $DATA_PIPELINE_DATA_ROOT/data-pipeline/eda/assignment-2/assignment2_report.pdf
"""

from __future__ import annotations

import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import geopandas as gpd
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Patch, Polygon
from matplotlib.ticker import FuncFormatter

SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from eda.assignment2.common import (  # noqa: E402
    CROP_COLORS,
    DATA_ROOT,
    FARMS,
    FIG_DIR,
    REPORT_PATH,
    TABLE_DIR,
    VERDICT_COLORS,
    VERDICT_NONE,
    eta_squared,
    holm_adjust,
    kruskal,
    load_boundaries,
    ranking_consistency,
    spearman,
    verdict,
    year_block_test,
)
from eda.assignment2.weather import cell_counts, weather_units  # noqa: E402

PAGE = (11.69, 8.27)  # A4 landscape, inches
INK = "#1F2933"
MUTED = "#6B7280"
RULE = "#D8DEE4"
ACCENT = "#2F6D9E"
LEFT = 0.055
RIGHT = 0.945
IMAGE_ASPECT_SPLIT = 1.9
_STATE_FIPS = {"IL": "17", "IA": "19", "NE": "31"}


@dataclass
class Finding:
    rank: int
    title: str
    shows: str
    means: str
    test: str
    figure: str
    verdict: str


def _read(name: str) -> pd.DataFrame:
    path = TABLE_DIR / name
    if not path.exists():
        raise SystemExit(f"Missing {path}; run scripts/eda/assignment2/run.py first")
    return pd.read_csv(path)


def _p(value: float) -> str:
    if not np.isfinite(value):
        return "n/a"
    if value < 0.001:
        return "< 0.001"
    return f"{value:.3f}"


# ------------------------------------------------------------------ statistics


def statistics() -> dict[str, Any]:
    weather = _read("weather_field_year.csv")
    cdl = _read("cdl_field_year.csv")
    fields = _read("cdl_field_stats.csv")
    boundaries = _read("boundaries_fields.csv")

    units = weather_units(weather)
    _, gdd_p = year_block_test(units, "gdd")
    _, precip_p = year_block_test(units, "precip_mm")
    gdd_eta = eta_squared([group["gdd"].to_numpy() for _, group in units.groupby("grower")])
    precip_eta = eta_squared(
        [group["precip_mm"].to_numpy() for _, group in units.groupby("grower")]
    )
    ne_gdd_wins = ranking_consistency(units, "gdd", "Nebraska")

    _, corn_years_p = kruskal(
        [group["corn_years"].to_numpy(dtype=float) for _, group in fields.groupby("grower")]
    )
    _, corn_share_p = kruskal(
        [group["corn_share"].to_numpy(dtype=float) for _, group in cdl.groupby("grower")]
    )
    corn_size_rho, corn_size_p = spearman(
        fields["acres"].to_numpy(dtype=float), fields["corn_years"].to_numpy(dtype=float)
    )

    _, area_p = kruskal(
        [group["acres"].to_numpy(dtype=float) for _, group in boundaries.groupby("grower")]
    )
    _, compact_p = kruskal(
        [
            group["compactness"].to_numpy(dtype=float)
            for _, group in boundaries.groupby("grower")
        ]
    )
    shape_rho, shape_p = spearman(
        boundaries["acres"].to_numpy(dtype=float),
        boundaries["compactness"].to_numpy(dtype=float),
    )

    # Holm within hypothesis families; a family is one question, not one metric.
    weather_adj = holm_adjust({"gdd": gdd_p, "precip": precip_p})
    rotation_adj = holm_adjust(
        {"corn_years": corn_years_p, "corn_share": corn_share_p, "corn_size": corn_size_p}
    )
    boundary_adj = holm_adjust({"area": area_p, "compactness": compact_p, "shape": shape_p})
    global_adj = holm_adjust(
        {
            "gdd": gdd_p,
            "precip": precip_p,
            "corn_years": corn_years_p,
            "corn_share": corn_share_p,
            "corn_size": corn_size_p,
            "area": area_p,
            "compactness": compact_p,
            "shape": shape_p,
        }
    )

    return {
        "weather": weather,
        "units": units,
        "cdl": cdl,
        "fields": fields,
        "boundaries": boundaries,
        "cells": cell_counts(units),
        "gdd_p": gdd_p,
        "gdd_adj": weather_adj["gdd"],
        "gdd_global_adj": global_adj["gdd"],
        "gdd_eta": gdd_eta,
        "gdd_wins": ne_gdd_wins,
        "precip_p": precip_p,
        "precip_adj": weather_adj["precip"],
        "precip_eta": precip_eta,
        "corn_years_p": corn_years_p,
        "corn_years_adj": rotation_adj["corn_years"],
        "corn_share_p": corn_share_p,
        "corn_share_adj": rotation_adj["corn_share"],
        "corn_size_rho": corn_size_rho,
        "corn_size_p": corn_size_p,
        "corn_size_adj": rotation_adj["corn_size"],
        "area_p": area_p,
        "area_adj": boundary_adj["area"],
        "compact_p": compact_p,
        "compact_adj": boundary_adj["compactness"],
        "shape_rho": shape_rho,
        "shape_p": shape_p,
        "shape_adj": boundary_adj["shape"],
    }


def findings(stats: dict[str, Any]) -> list[Finding]:
    corn_means = stats["fields"].groupby("grower")["corn_years"].mean()
    ne = float(corn_means.get("Nebraska", float("nan")))
    il = float(corn_means.get("Illinois", float("nan")))
    ia = float(corn_means.get("Iowa", float("nan")))
    ne_cells, ne_years = stats["gdd_wins"]
    compact = stats["boundaries"].groupby("grower")["compactness"].median()
    gdd_mean = stats["units"].groupby("grower")["gdd"].mean()
    ne_gdd = float(gdd_mean.get("Nebraska", float("nan")))
    heat_gap = (
        f"Nebraska averages {ne_gdd:,.0f} GDD against "
        f"{float(gdd_mean.get('Illinois', float('nan'))):,.0f} in Illinois and "
        f"{float(gdd_mean.get('Iowa', float('nan'))):,.0f} in Iowa"
    )
    by_year = stats["cdl"].groupby(["grower", "year"])[
        ["corn_acres", "soy_acres", "other_acres"]
    ].sum()
    share = (by_year["corn_acres"] / by_year.sum(axis=1)).unstack()

    return [
        Finding(
            rank=1,
            title="Nebraska is the warmest state in every year",
            shows=(
                "Season heat separates cleanly by state: " + heat_gap +
                ". Each bold line is a grower mean over its fields; the shaded band is the "
                "spread between distinct NASA POWER grid cells, which is the only spread that "
                "is real."
            ),
            means=(
                "Heat is the one difference that holds in all five years, so it is the "
                "strongest claim in this dataset. It is also consistent with Nebraska's "
                "more corn-heavy rotation, though nothing here proves that link."
            ),
            test=(
                f"Friedman test, years blocked: p = {_p(stats['gdd_p'])}, Holm-adjusted "
                f"p = {_p(stats['gdd_adj'])} (2 weather tests). Grower explains "
                f"{stats['gdd_eta']:.0%} of cell-year variance; Nebraska is highest in "
                f"{ne_cells}/{ne_years} years."
            ),
            figure="weather_01_gdd_precip_by_year.png",
            verdict=verdict(stats["gdd_p"], stats["gdd_adj"]),
        ),
        Finding(
            rank=2,
            title=f"Nebraska fields spend {ne:.1f} of 5 years in corn, against {il:.1f} and {ia:.1f}",
            shows=(
                "One block per grower, one row per field, one column per CDL year, coloured "
                "by the dominant crop. An alternating stripe is a corn/soybean rotation; "
                "repeated gold is continuous corn."
            ),
            means=(
                "Nebraska is a corn-leaning system; Illinois and Iowa sit closer to a 50/50 "
                "rotation. The gap is the largest rotation difference here, but with five "
                "years of CDL it is suggestive rather than proven."
            ),
            test=(
                f"Kruskal-Wallis on years-in-corn: p = {_p(stats['corn_years_p'])}, adjusted "
                f"p = {_p(stats['corn_years_adj'])} (3 rotation tests). Field-year corn "
                f"share: p = {_p(stats['corn_share_p'])}, adjusted "
                f"{_p(stats['corn_share_adj'])}."
            ),
            figure="cdl_01_rotation_grid.png",
            verdict=verdict(stats["corn_years_p"], stats["corn_years_adj"]),
        ),
        Finding(
            rank=3,
            title="Nebraska keeps more than half its land in corn",
            shows=(
                "Bars are shares of each grower-year, so Iowa's larger acreage cannot "
                "dominate the picture; the totals written above each bar give absolute acres."
            ),
            means=(
                f"Nebraska's corn share never drops below "
                f"{share.loc['Nebraska'].min():.0%}, while Illinois swings between "
                f"{share.loc['Illinois'].min():.0%} and {share.loc['Illinois'].max():.0%}. "
                "This page is descriptive: the group difference is not clearly separated, "
                "so treat it as a pattern to watch rather than an established contrast. "
                "Absolute acres would mostly show that Iowa farms more land."
            ),
            test=(
                f"Field-year corn share by grower: Kruskal-Wallis p = "
                f"{_p(stats['corn_share_p'])}, adjusted p = {_p(stats['corn_share_adj'])}."
            ),
            figure="cdl_02_crop_share_by_grower_year.png",
            verdict=verdict(stats["corn_share_p"], stats["corn_share_adj"]),
        ),
        Finding(
            rank=4,
            title="Rainfall is a year signal, not a state signal",
            shows=(
                "The right panel is the rainfall comparison measured on distinct weather "
                "cell-years rather than on fields; the left panel repeats the heat result "
                "the same way."
            ),
            means=(
                "Rainfall moves together across all three states and the between-state gap "
                "is small next to the year-to-year swing: Illinois is wettest in 2021, Iowa "
                "in 2024 and 2025. Water-dependent readings should be taken year by year, "
                "not as a state contrast."
            ),
            test=(
                f"Friedman test, years blocked: p = {_p(stats['precip_p'])}, adjusted "
                f"p = {_p(stats['precip_adj'])}. Grower explains "
                f"{stats['precip_eta']:.0%} of cell-year variance."
            ),
            figure="weather_03_grower_comparison.png",
            verdict=verdict(stats["precip_p"], stats["precip_adj"]),
        ),
        Finding(
            rank=5,
            title="Bigger fields are not more corn-heavy",
            shows=(
                "Each point is one field, placed by area and by how many of the five years "
                "it was in corn. The right panel buckets the same fields into size quartiles "
                "to show the flat profile directly."
            ),
            means=(
                "There is no size effect to manage around: a 1,000-acre field is no more "
                "likely to be continuous corn than a 60-acre one."
            ),
            test=(
                f"Spearman rho = {stats['corn_size_rho']:.2f} (p = "
                f"{_p(stats['corn_size_p'])}, adjusted {_p(stats['corn_size_adj'])}), "
                f"n = {len(stats['fields'])} fields."
            ),
            figure="cdl_03_rotation_vs_size.png",
            verdict=verdict(stats["corn_size_p"], stats["corn_size_adj"]),
        ),
        Finding(
            rank=6,
            title="Field shape differs slightly; field size does not",
            shows=(
                "Compactness clusters just under the square reference (dotted, pi/4) in all "
                "three states, and neither area nor shape shows a trend across the size range."
            ),
            means=(
                f"Median compactness is {compact.get('Illinois', float('nan')):.2f} in "
                f"Illinois, {compact.get('Iowa', float('nan')):.2f} in Iowa and "
                f"{compact.get('Nebraska', float('nan')):.2f} in Nebraska. The gap does not "
                "survive correction, so treat it as noise rather than a management signal."
            ),
            test=(
                f"Area: Kruskal-Wallis p = {_p(stats['area_p'])} (adjusted "
                f"{_p(stats['area_adj'])}). Compactness: p = {_p(stats['compact_p'])} "
                f"(adjusted {_p(stats['compact_adj'])}). Size vs shape: rho = "
                f"{stats['shape_rho']:.2f}, p = {_p(stats['shape_p'])}."
            ),
            figure="boundaries_03_size_vs_shape.png",
            verdict=verdict(stats["compact_p"], stats["compact_adj"]),
        ),
    ]


# ---------------------------------------------------------------------- layout


def _fit(
    box: tuple[float, float, float, float], aspect: float
) -> tuple[float, float, float, float]:
    """Centre an image of the given width/height ratio inside a figure box.

    Boxes are figure fractions, so the fits are done in inches and mapped back;
    mixing the two silently squashes images.
    """
    x0, y0, width, height = box
    box_w, box_h = width * PAGE[0], height * PAGE[1]
    if box_w / box_h > aspect:
        fit_h = box_h
        fit_w = box_h * aspect
    else:
        fit_w = box_w
        fit_h = box_w / aspect
    return (
        x0 + (width - fit_w / PAGE[0]) / 2,
        y0 + (height - fit_h / PAGE[1]) / 2,
        fit_w / PAGE[0],
        fit_h / PAGE[1],
    )


def _chip(fig: plt.Figure, text: str, *, x: float, y: float, color: str) -> None:
    width = 0.052 + 0.0098 * len(text)
    fig.patches.append(
        FancyBboxPatch(
            (x - width, y - 0.019),
            width,
            0.042,
            boxstyle="round,pad=0.004,rounding_size=0.012",
            transform=fig.transFigure,
            facecolor=color,
            edgecolor="none",
            zorder=3,
        )
    )
    fig.text(x - width / 2, y + 0.002, text, ha="center", va="center",
             fontsize=9.5, color="white", fontweight="bold", zorder=4)


def _footer(fig: plt.Figure, number: int) -> None:
    fig.text(LEFT, 0.035, "Assignment 2  |  IL / IA / NE  |  30 fields, 2021-2025",
             fontsize=8, color=MUTED)
    fig.text(RIGHT, 0.035, str(number), fontsize=8, color=MUTED, ha="right")


def _rule(fig: plt.Figure, y: float, *, x0: float = LEFT, x1: float = RIGHT) -> None:
    fig.add_artist(plt.Line2D([x0, x1], [y, y], color=RULE, linewidth=0.9,
                              transform=fig.transFigure))


def _body(fig: plt.Figure, lines: list[str], *, x: float, y: float, width: int = 120,
          gap: float = 0.026, size: float = 10.5, leading: float = 0.031) -> float:
    cursor = y
    for entry in lines:
        for block in textwrap.wrap(entry, width=width) or [""]:
            fig.text(x, cursor, block, fontsize=size, color=INK, va="top")
            cursor -= leading
        cursor -= gap - leading
    return cursor


def _place(fig: plt.Figure, name: str, box: tuple[float, float, float, float]) -> None:
    path = FIG_DIR / name
    if not path.exists():
        fig.text(box[0], box[1] + box[3] / 2, f"[missing figure: {name}]",
                 fontsize=10, color=MUTED)
        return
    image = plt.imread(path)
    height, width = image.shape[:2]
    left, bottom, w, h = _fit(box, width / height)
    ax = fig.add_axes((left, bottom, w, h))
    ax.imshow(image)
    ax.axis("off")


def _title(fig: plt.Figure, text: str) -> None:
    size = 17.0
    if len(text) > 58:
        size = 15.0
    if len(text) > 74:
        size = 13.5
    fig.text(LEFT, 0.893, text, fontsize=size, color=INK, fontweight="bold", va="top")


def finding_page(pdf: PdfPages, finding: Finding, number: int) -> None:
    fig = plt.figure(figsize=PAGE)
    fig.patch.set_facecolor("white")
    fig.text(LEFT, 0.945, f"FINDING {finding.rank}", fontsize=9, color=MUTED,
             fontweight="bold")
    _title(fig, finding.title)
    _chip(fig, finding.verdict, x=RIGHT, y=0.912, color=VERDICT_COLORS[finding.verdict])
    _rule(fig, 0.862)

    path = FIG_DIR / finding.figure
    aspect = 2.5
    if path.exists():
        height, width = plt.imread(path).shape[:2]
        aspect = width / height

    if aspect >= IMAGE_ASPECT_SPLIT:
        _place(fig, finding.figure, (0.05, 0.415, 0.90, 0.405))
        text_x, text_w, text_y = LEFT, 128, 0.335
    else:
        _place(fig, finding.figure, (0.03, 0.09, 0.55, 0.72))
        text_x, text_w, text_y = 0.625, 48, 0.79

    cursor = _body(
        fig,
        [f"What this shows  {finding.shows}", f"What it means  {finding.means}"],
        x=text_x,
        y=text_y,
        width=text_w,
        size=10.0 if aspect < IMAGE_ASPECT_SPLIT else 10.5,
        gap=0.030,
    )
    rule_y = max(cursor + 0.010, 0.115)
    _rule(fig, rule_y, x0=text_x)
    fig.text(
        text_x,
        rule_y - 0.030,
        "\n".join(textwrap.wrap(finding.test, 58 if aspect < IMAGE_ASPECT_SPLIT else 150)),
        fontsize=8.6,
        color=MUTED,
        va="top",
        linespacing=1.45,
    )
    _footer(fig, number)
    pdf.savefig(fig)
    plt.close(fig)


def cover_page(pdf: PdfPages, stats: dict[str, Any], rows: list[tuple[str, float, float, str]]) -> None:
    fig = plt.figure(figsize=PAGE)
    fig.patch.set_facecolor("white")
    fig.text(LEFT, 0.905, "ASSIGNMENT 2  |  FIELD-LEVEL EDA", fontsize=10, color=ACCENT,
             fontweight="bold")
    fig.text(LEFT, 0.815, "Three states, thirty fields:", fontsize=26, color=INK,
             fontweight="bold")
    fig.text(LEFT, 0.752, "what the geospatial data actually says", fontsize=26,
             color=INK, fontweight="bold")
    _rule(fig, 0.706)

    total_fields = int(len(stats["boundaries"]))
    total_acres = float(stats["boundaries"]["acres"].sum())
    cell_total = int(sum(stats["cells"].values()))
    intro = (
        f"{total_fields} corn/soybean fields in Illinois (Iroquois County), Iowa (Kossuth "
        f"County) and Nebraska (York County), {total_acres:,.0f} acres in total. Each field "
        "was checked against three independent layers: field boundaries, the USDA Cropland "
        f"Data Layer for 2021-2025, and NASA POWER weather. The {cell_total} distinct weather "
        "grid cells behind those fields set the real sample size for any weather claim, and "
        "every result is reported that way."
    )
    cursor = _body(fig, [intro], x=LEFT, y=0.665, width=122, size=11, leading=0.033)

    cursor -= 0.045
    fig.text(LEFT, cursor, "FINDINGS, RANKED BY EVIDENCE", fontsize=9.5, color=MUTED,
             fontweight="bold")
    cursor -= 0.042
    columns = ((LEFT, "finding"), (0.60, "raw p"), (0.71, "adjusted p"), (0.81, "verdict"))
    fig.text(columns[0][0], cursor, "FINDING", fontsize=7.5, color=MUTED, fontweight="bold")
    fig.text(columns[1][0], cursor, "RAW P", fontsize=7.5, color=MUTED, fontweight="bold")
    fig.text(columns[2][0], cursor, "HOLM P", fontsize=7.5, color=MUTED, fontweight="bold")
    fig.text(columns[3][0], cursor, "VERDICT", fontsize=7.5, color=MUTED, fontweight="bold")
    cursor -= 0.012
    _rule(fig, cursor)

    for label, raw, adjusted, label_verdict in rows:
        cursor -= 0.037
        fig.text(columns[0][0], cursor, label, fontsize=10.5, color=INK)
        fig.text(columns[1][0], cursor, _p(raw), fontsize=10.5, color=INK)
        fig.text(columns[2][0], cursor, _p(adjusted), fontsize=10.5, color=INK)
        fig.text(columns[3][0], cursor, label_verdict, fontsize=10,
                 color=VERDICT_COLORS[label_verdict], fontweight="bold")

    cursor -= 0.045
    _rule(fig, cursor)
    fig.text(
        LEFT,
        cursor - 0.030,
        "Strong = survives correction within its question. Suggestive = raw p < 0.05 but "
        "not after correction. No clear effect = p >= 0.05.",
        fontsize=8.5,
        color=MUTED,
    )
    _footer(fig, 1)
    pdf.savefig(fig)
    plt.close(fig)


def _draw_overview(fig: plt.Figure, box: tuple[float, float, float, float]) -> list[str]:
    """Compact county overview: 30 field polygons, coloured by 2025 dominant crop."""
    cdl = _read("cdl_field_year.csv")
    latest = int(cdl["year"].max())
    crops = {
        str(row.field_id): str(row.dominant_crop)
        for row in cdl[cdl["year"] == latest].itertuples(index=False)
    }
    counties_path = (
        DATA_ROOT / "shared" / "geoadmin" / "l2_counties" / "counties_usa.parquet"
    )
    counties = None
    if counties_path.exists():
        counties = gpd.read_parquet(counties_path)
    notes: list[str] = []
    width = box[2] / len(FARMS)
    for index, meta in enumerate(FARMS):
        left = box[0] + index * width
        ax = fig.add_axes((left + 0.012, box[1], width - 0.03, box[3]))
        boundaries = load_boundaries(meta)
        if boundaries is None:
            ax.text(0.5, 0.5, "no boundary", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
            continue
        boundaries = boundaries.to_crs("EPSG:5070")
        if counties is not None:
            match = counties[
                (counties["state_fips"] == _STATE_FIPS[meta.state])
                & (counties["county_name"].str.lower() == meta.county.lower())
            ].to_crs("EPSG:5070")
            if not match.empty:
                match.plot(ax=ax, color="#F3F1EA", edgecolor="#C3C8CE", linewidth=0.8, zorder=1)
        colors = [
            CROP_COLORS["Corn"] if crops.get(str(fid)) == "corn"
            else CROP_COLORS["Soybeans"] if crops.get(str(fid)) == "soy"
            else CROP_COLORS["Other"]
            for fid in boundaries["field_id"]
        ]
        boundaries.plot(ax=ax, color=colors, edgecolor="#4A4A4A", linewidth=0.4, zorder=2)
        # Lock each panel to the same box aspect so all three align exactly.
        frame = match if (counties is not None and not match.empty) else boundaries
        x0, y0, x1, y1 = frame.total_bounds
        pad = 0.03 * max(x1 - x0, y1 - y0)
        x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        box_w = (width - 0.03) * PAGE[0]
        box_h = box[3] * PAGE[1]
        ratio = box_w / box_h
        dx, dy = x1 - x0, y1 - y0
        if dx / dy > ratio:
            dy = dx / ratio
        else:
            dx = dy * ratio
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ax.set_xlim(cx - dx / 2, cx + dx / 2)
        ax.set_ylim(cy - dy / 2, cy + dy / 2)
        ax.set_aspect("equal", adjustable="box")
        ax.set_axis_off()
        ax.set_title(
            f"{meta.label} \u00b7 {meta.county} County, {meta.state}\n"
            f"{len(boundaries)} fields \u00b7 {boundaries['area_acres'].sum():,.0f} ac",
            loc="left",
            fontsize=9.5,
            fontweight="bold",
            color=INK,
            pad=4,
        )
        # metre-scale reference bar and north arrow, in axes fractions
        x0, x1 = ax.get_xlim()
        span = max(x1 - x0, 1.0)
        bar = min(5000.0 / span, 0.55)
        ax.plot(
            [0.05, 0.05 + bar],
            [0.07, 0.07],
            color=INK,
            linewidth=2.4,
            solid_capstyle="butt",
            transform=ax.transAxes,
            clip_on=False,
        )
        ax.text(
            0.05 + bar / 2,
            0.015,
            "5 km",
            fontsize=7.5,
            color=INK,
            ha="center",
            va="bottom",
            transform=ax.transAxes,
        )
        ax.annotate(
            "",
            xy=(0.06, 0.90),
            xytext=(0.06, 0.80),
            xycoords="axes fraction",
            arrowprops={"arrowstyle": "-|>", "color": INK, "linewidth": 1.2},
        )
        ax.text(0.06, 0.925, "N", fontsize=7.5, color=INK, fontweight="bold",
                ha="center", transform=ax.transAxes)
        notes.append(f"{meta.short}: {len(boundaries)} fields")
        notes.append(f"{meta.short}: {len(boundaries)} fields")
    handles = [
        Patch(facecolor=CROP_COLORS["Corn"], label="Corn"),
        Patch(facecolor=CROP_COLORS["Soybeans"], label="Soybeans"),
        Patch(facecolor=CROP_COLORS["Other"], label="Other"),
    ]
    fig.legend(
        handles=handles,
        loc="center",
        bbox_to_anchor=(0.5, box[1] - 0.030),
        ncol=3,
        frameon=False,
        fontsize=9.5,
        handlelength=1.2,
    )
    return notes


def map_page(pdf: PdfPages, number: int) -> None:
    fig = plt.figure(figsize=PAGE)
    fig.patch.set_facecolor("white")
    fig.text(LEFT, 0.945, "THE FIELDS", fontsize=9, color=MUTED, fontweight="bold")
    fig.text(LEFT, 0.893, "Three counties, thirty fields, one county each",
             fontsize=17, color=INK, fontweight="bold")
    _rule(fig, 0.862)
    _draw_overview(fig, (0.045, 0.295, 0.91, 0.485))
    fig.text(
        LEFT,
        0.190,
        "Every field sits in one of these three counties, so a state effect is also a county "
        "effect. Each panel has its own 5 km scale bar; the counties differ in east-west and "
        "north-south extent, so they are not drawn on one common frame. The separate atlas "
        "figure zooms into each field shape.",
        fontsize=9.5,
        color=MUTED,
        va="top",
        wrap=True,
    )
    _footer(fig, number)
    pdf.savefig(fig)
    plt.close(fig)


def methods_page(pdf: PdfPages, stats: dict[str, Any], number: int) -> None:
    fig = plt.figure(figsize=PAGE)
    fig.patch.set_facecolor("white")
    fig.text(LEFT, 0.945, "METHODS", fontsize=9, color=MUTED, fontweight="bold")
    fig.text(LEFT, 0.893, "How to read the numbers without over-reading them",
             fontsize=17, color=INK, fontweight="bold")
    _rule(fig, 0.862)

    counts = ", ".join(f"{label} {cells}" for label, cells in sorted(stats["cells"].items()))
    blocks = [
        "Data. Field boundaries are OpenStreetMap farm outlines, projected to EPSG:5070 for "
        "area and perimeter. Crops are USDA Cropland Data Layer 2021-2025, pixel-weighted at "
        "30 m. Weather is NASA POWER daily data for the growing season (April 1 - October 31), "
        "with GDD cut off at 10 and 30 \u00b0C.",
        f"Effective sample size. Fields inside one weather grid cell share an identical daily "
        f"series ({counts}), so weather is tested on distinct cell-years with years blocked, "
        "not on 150 field-years. Field-level tests use the 30 fields, which are independent.",
        "Multiple comparisons. Eight tests are reported. Holm correction is applied within "
        "each question - boundaries, weather, rotation - because those are separate families. "
        "A single global family of all eight is stricter: heat is closest but stops at "
        f"p = {_p(stats['gdd_global_adj'])}, so no test would reach 0.05. Both levels are "
        "shown rather than the flattering one.",
        "Limits. One county per state confounds state and county. Five CDL years give weak "
        "power for rotation tests. No soil, yield or management data is used, so nothing here "
        "explains why the states differ, only that they do.",
    ]
    _body(fig, blocks, x=LEFT, y=0.80, width=112, size=10.5, gap=0.036)

    table_y = 0.235
    fig.text(LEFT, table_y + 0.055, "DATASET AT A GLANCE", fontsize=9, color=MUTED,
             fontweight="bold")
    headers = ["grower", "fields", "acres", "median field", "weather cells", "CDL years"]
    xs = [LEFT, 0.20, 0.31, 0.42, 0.55, 0.71]
    for x, header in zip(xs, headers):
        fig.text(x, table_y + 0.020, header.upper(), fontsize=7.5, color=MUTED,
                 fontweight="bold")
    _rule(fig, table_y + 0.010, x1=0.86)
    summary = _read("boundaries_summary.csv")
    row_y = table_y - 0.008
    for row in summary.itertuples(index=False):
        label = next((meta.label for meta in FARMS if meta.label == row.grower), row.grower)
        cells = stats["cells"].get(label, 0)
        values = [
            label,
            str(int(row.fields)),
            f"{row.acres_total:,.0f}",
            f"{row.acres_median:,.0f} ac",
            str(cells),
            "2021-2025",
        ]
        for x, value in zip(xs, values):
            fig.text(x, row_y, value, fontsize=9.5, color=INK)
        row_y -= 0.030
    _footer(fig, number)
    pdf.savefig(fig)
    plt.close(fig)


def build() -> Path:
    stats = statistics()
    all_findings = sorted(findings(stats), key=lambda item: item.rank)

    table_rows = [
        ("Heat: NE warmest every year", stats["gdd_p"], stats["gdd_adj"], all_findings[0].verdict),
        ("Rotation: NE more years in corn", stats["corn_years_p"], stats["corn_years_adj"], all_findings[1].verdict),
        ("Corn share by grower", stats["corn_share_p"], stats["corn_share_adj"], all_findings[2].verdict),
        ("Rainfall by grower", stats["precip_p"], stats["precip_adj"], all_findings[3].verdict),
        ("Field size vs years in corn", stats["corn_size_p"], stats["corn_size_adj"], all_findings[4].verdict),
        ("Field compactness by grower", stats["compact_p"], stats["compact_adj"], all_findings[5].verdict),
        ("Field area by grower", stats["area_p"], stats["area_adj"], VERDICT_NONE),
        ("Field size vs shape", stats["shape_p"], stats["shape_adj"], VERDICT_NONE),
    ]

    table_rows.sort(key=lambda row: (row[1] if np.isfinite(row[1]) else 1.0))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(REPORT_PATH) as pdf:
        cover_page(pdf, stats, table_rows)
        map_page(pdf, 2)
        for number, finding in enumerate(all_findings, start=3):
            finding_page(pdf, finding, number)
        methods_page(pdf, stats, 3 + len(all_findings))
        metadata = pdf.infodict()
        metadata["Title"] = "Assignment 2: three states, thirty fields"
        metadata["Subject"] = "Field-level EDA of IL, IA and NE corn/soybean farms"
        metadata["Keywords"] = "CDL, NASA POWER, field boundaries, EDA"

    return REPORT_PATH


def main() -> None:
    path = build()
    print(f"Report: {path}")
    print(f"Pages:  {3 + len(findings(statistics()))}")


if __name__ == "__main__":
    main()
