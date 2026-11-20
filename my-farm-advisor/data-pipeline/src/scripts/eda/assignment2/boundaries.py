#!/usr/bin/env python3
"""Field-boundary EDA: acreage, shape, and their comparison.

Outputs
-------
figures/boundaries_01_acreage_by_grower.png
figures/boundaries_02_compactness_ecdf.png
figures/boundaries_03_size_vs_shape.png
tables/boundaries_fields.csv
tables/boundaries_summary.csv
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common import (
    FIG_DIR,
    TABLE_DIR,
    FarmData,
    box_groups,
    footnote,
    grower_legend,
    kruskal,
    p_label,
    save_figure,
    spearman,
    style_axes,
)


def field_table(data: list[FarmData]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for farm in data:
        if farm.boundaries is None:
            continue
        for row in farm.boundaries.itertuples(index=False):
            rows.append(
                {
                    "grower": farm.meta.label,
                    "field_id": str(row.field_id),
                    "acres": round(float(row.area_acres), 2),
                    "perimeter_m": round(float(row.perimeter_m), 1),
                    "compactness": round(float(row.compactness), 4),
                }
            )
    return pd.DataFrame(rows)


def summary_table(data: list[FarmData]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for farm in data:
        frame = farm.boundaries
        if frame is None:
            continue
        rows.append(
            {
                "grower": farm.meta.label,
                "fields": int(len(frame)),
                "acres_total": round(float(frame["area_acres"].sum()), 1),
                "acres_median": round(float(frame["area_acres"].median()), 1),
                "acres_min": round(float(frame["area_acres"].min()), 1),
                "acres_max": round(float(frame["area_acres"].max()), 1),
                "compactness_median": round(float(frame["compactness"].median()), 3),
                "compactness_min": round(float(frame["compactness"].min()), 3),
                "compactness_max": round(float(frame["compactness"].max()), 3),
            }
        )
    return pd.DataFrame(rows)


def figure_acreage(data: list[FarmData]) -> plt.Figure:
    usable = [farm for farm in data if farm.boundaries is not None]
    fig, ax = plt.subplots(figsize=(7.6, 5.2))
    groups = [(farm.meta, farm.boundaries["area_acres"].to_numpy()) for farm in usable]
    box_groups(ax, groups, log=True)
    for pos, (meta, values) in enumerate(groups, start=1):
        median = float(np.median(values))
        ax.annotate(
            f"median {median:,.0f} ac",
            xy=(pos, median),
            ha="center",
            va="center",
            fontsize=8,
            color=meta.color,
            fontweight="bold",
            zorder=6,
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.85},
        )
    ax.set_ylabel("Field area (acres, log scale)")
    ax.set_title("Field acreage by grower", loc="left", fontweight="bold")
    style_axes(ax)
    footnote(
        fig,
        "Segments: boxes = IQR, line = median, dots = fields (10 per grower). "
        "Areas computed in EPSG:5070.",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def figure_compactness(data: list[FarmData]) -> plt.Figure:
    usable = [farm for farm in data if farm.boundaries is not None]
    fig, ax = plt.subplots(figsize=(7.6, 5.2))
    values_by_grower = []
    for farm in usable:
        values = np.sort(farm.boundaries["compactness"].to_numpy())
        values_by_grower.append(values)
        y = np.arange(1, len(values) + 1) / len(values)
        ax.step(values, y, where="post", color=farm.meta.color, linewidth=2.2, label=farm.meta.label)
    _, p_value = kruskal(values_by_grower)
    ax.set_xlabel("Polsby-Popper compactness (1 = circle)")
    ax.set_ylabel("Cumulative share of fields")
    ax.set_xlim(0.0, 1.02)
    ax.set_ylim(0.0, 1.02)
    ax.set_title(
        f"Field shape compactness by grower (Kruskal-Wallis {p_label(p_value)})",
        loc="left",
        fontweight="bold",
    )
    style_axes(ax)
    grower_legend(ax, [farm.meta for farm in usable], loc="lower right", fontsize=9)
    footnote(
        fig,
        "Polsby-Popper = 4*pi*area / perimeter^2 in EPSG:5070 metres. "
        "Higher is more compact; 1.0 is a circle.",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def figure_size_vs_shape(data: list[FarmData]) -> plt.Figure:
    usable = [farm for farm in data if farm.boundaries is not None]
    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    for farm in usable:
        ax.scatter(
            farm.boundaries["area_acres"],
            farm.boundaries["compactness"],
            s=46,
            color=farm.meta.color,
            edgecolor="white",
            linewidth=0.6,
            alpha=0.92,
            label=farm.meta.label,
            zorder=3,
        )
    areas = np.concatenate([farm.boundaries["area_acres"].to_numpy() for farm in usable])
    shapes = np.concatenate([farm.boundaries["compactness"].to_numpy() for farm in usable])
    rho, p_value = spearman(areas, shapes)
    area_h, area_p = kruskal([farm.boundaries["area_acres"].to_numpy() for farm in usable])
    comp_h, comp_p = kruskal([farm.boundaries["compactness"].to_numpy() for farm in usable])

    ax.set_xscale("log")
    ax.set_xlabel("Field area (acres, log scale)")
    ax.set_ylabel("Polsby-Popper compactness (1 = circle)")
    ax.set_title("Does field size explain shape?", loc="left", fontweight="bold")
    ax.axhline(0.785, color="#888888", linestyle=":", linewidth=1.0, zorder=1)
    ax.annotate(
        "square reference (\u03c0/4)",
        xy=(0.99, 0.785),
        xycoords=("axes fraction", "data"),
        xytext=(0, 3),
        textcoords="offset points",
        ha="right",
        va="bottom",
        fontsize=8,
        color="#777777",
    )
    ax.text(
        0.02,
        0.98,
        f"Spearman rho = {rho:.2f} ({p_label(p_value)}), n = {len(areas)}\n"
        f"Area across growers: {p_label(area_p)} (H = {area_h:.1f})\n"
        f"Shape across growers: {p_label(comp_p)} (H = {comp_h:.1f})",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8.8,
        bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "#cccccc"},
    )
    style_axes(ax)
    grower_legend(ax, [farm.meta for farm in usable], loc="lower right", fontsize=9)
    footnote(fig, "Dotted line = square (pi/4 = 0.785); a circle is 1.0. Kruskal-Wallis tests compare the three growers; Spearman tests size vs. shape.")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def run(data: list[FarmData]) -> dict[str, Any]:
    usable = [farm for farm in data if farm.boundaries is not None]
    if not usable:
        raise RuntimeError("No boundary data available for any farm")

    figures = [
        save_figure(figure_acreage(usable), "boundaries_01_acreage_by_grower.png"),
        save_figure(figure_compactness(usable), "boundaries_02_compactness_ecdf.png"),
        save_figure(figure_size_vs_shape(usable), "boundaries_03_size_vs_shape.png"),
    ]

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    fields = field_table(usable)
    summary = summary_table(usable)
    fields.to_csv(TABLE_DIR / "boundaries_fields.csv", index=False)
    summary.to_csv(TABLE_DIR / "boundaries_summary.csv", index=False)

    areas = np.concatenate([farm.boundaries["area_acres"].to_numpy() for farm in usable])
    shapes = np.concatenate([farm.boundaries["compactness"].to_numpy() for farm in usable])
    _, area_p = kruskal([farm.boundaries["area_acres"].to_numpy() for farm in usable])
    _, comp_p = kruskal([farm.boundaries["compactness"].to_numpy() for farm in usable])
    rho, rho_p = spearman(areas, shapes)

    return {
        "figures": [str(path) for path in figures],
        "tables": [str(TABLE_DIR / "boundaries_fields.csv"), str(TABLE_DIR / "boundaries_summary.csv")],
        "tests": {
            "boundaries.area_kruskal_p": round(area_p, 4),
            "boundaries.compactness_kruskal_p": round(comp_p, 4),
            "boundaries.size_compactness_spearman_rho": round(rho, 3),
            "boundaries.size_compactness_spearman_p": round(rho_p, 4),
        },
    }
