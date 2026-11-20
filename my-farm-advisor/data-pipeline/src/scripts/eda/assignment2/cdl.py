#!/usr/bin/env python3
"""CDL/cropland EDA: rotation, crop composition, and diversity vs. field size.

Outputs
-------
figures/cdl_01_rotation_heatmap.png
figures/cdl_02_crop_acres_by_grower_year.png
figures/cdl_03_size_vs_diversity.png
tables/cdl_field_year.csv
tables/cdl_summary.csv
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common import (
    CDL_PIXEL_ACRES,
    CORN,
    CROP_COLORS,
    DIVERSITY_MIN_SHARE,
    FARMS,
    SOY,
    TABLE_DIR,
    FarmData,
    footnote,
    grower_legend,
    jitter,
    kruskal,
    p_label,
    save_figure,
    spearman,
    style_axes,
)

EXCLUDED_CLASSES = {"No Data", "Unknown"}


def _shannon(shares: pd.Series) -> float:
    values = shares[shares > 0].to_numpy(dtype=float)
    if len(values) <= 1:
        return 0.0
    return float(-(values * np.log(values)).sum())


def field_year_table(data: list[FarmData]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for farm in data:
        if farm.cdl is None:
            continue
        frame = farm.cdl.frame
        for (field_id, year), group in frame.groupby(["field_id", "year"], sort=True):
            total_px = float(group["pixel_count"].sum())
            if total_px <= 0:
                continue
            valid = group[~group["crop_name"].isin(EXCLUDED_CLASSES)]
            valid_px = float(valid["pixel_count"].sum())
            if valid_px <= 0:
                continue
            totals = valid.groupby("crop_name")["pixel_count"].sum()
            shares = totals / valid_px
            significant = shares[shares >= DIVERSITY_MIN_SHARE]
            corn_share = float(shares.get(CORN, 0.0))
            soy_share = float(shares.get(SOY, 0.0))
            mapped_acres = valid_px * CDL_PIXEL_ACRES
            rows.append(
                {
                    "grower": farm.meta.label,
                    "field_id": str(field_id),
                    "year": int(year),
                    "mapped_acres": round(mapped_acres, 2),
                    "corn_acres": round(float(totals.get(CORN, 0.0)) * CDL_PIXEL_ACRES, 2),
                    "soy_acres": round(float(totals.get(SOY, 0.0)) * CDL_PIXEL_ACRES, 2),
                    "other_acres": round(
                        mapped_acres
                        - float(totals.get(CORN, 0.0)) * CDL_PIXEL_ACRES
                        - float(totals.get(SOY, 0.0)) * CDL_PIXEL_ACRES,
                        2,
                    ),
                    "corn_share": round(corn_share, 4),
                    "soy_share": round(soy_share, 4),
                    "other_share": round(max(0.0, 1.0 - corn_share - soy_share), 4),
                    "n_crop_classes": int(len(significant)),
                    "crop_diversity": round(_shannon(shares), 4),
                }
            )
    return pd.DataFrame(rows)


def summary_table(data: list[FarmData], table: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for farm in data:
        if farm.cdl is None:
            continue
        subset = table[table["grower"] == farm.meta.label]
        if subset.empty:
            continue
        rows.append(
            {
                "grower": farm.meta.label,
                "cdl_source": farm.cdl.source,
                "cdl_years": ",".join(str(year) for year in farm.cdl.years),
                "fields": int(subset["field_id"].nunique()),
                "field_years": int(len(subset)),
                "corn_share_median": round(float(subset["corn_share"].median()), 3),
                "soy_share_median": round(float(subset["soy_share"].median()), 3),
                "crop_classes_median": float(subset["n_crop_classes"].median()),
                "crop_diversity_median": round(float(subset["crop_diversity"].median()), 3),
            }
        )
    return pd.DataFrame(rows)


def figure_rotation(data: list[FarmData]) -> plt.Figure:
    usable = [farm for farm in data if farm.cdl is not None]
    table = field_year_table(usable)
    rows = []
    order = {meta.short: idx for idx, meta in enumerate(FARMS)}
    for farm in usable:
        subset = table[table["grower"] == farm.meta.label]
        for field_id, group in subset.groupby("field_id", sort=True):
            values = group.set_index("year")["corn_share"]
            rows.append({"grower": farm.meta.short, "field_id": field_id, "values": values, "order": order[farm.meta.short]})
    rows.sort(key=lambda row: (row["order"], row["field_id"]))
    years = sorted({int(year) for row in rows for year in row["values"].index})
    matrix = np.full((len(rows), len(years)), np.nan)
    for i, row in enumerate(rows):
        for j, year in enumerate(years):
            if year in row["values"].index:
                matrix[i, j] = float(row["values"].loc[year])

    labels: list[str] = []
    counters: dict[str, int] = {}
    for row in rows:
        counters[row["grower"]] = counters.get(row["grower"], 0) + 1
        labels.append(f"{row['grower']}-{counters[row['grower']]:02d}")

    fig, ax = plt.subplots(figsize=(7.8, max(5.4, 0.24 * len(rows) + 2.0)))
    image = ax.imshow(
        np.ma.masked_invalid(matrix),
        aspect="auto",
        cmap="YlGn",
        vmin=0.0,
        vmax=1.0,
        interpolation="nearest",
    )
    ax.set_xticks(np.arange(len(years)))
    ax.set_xticklabels([str(year) for year in years])
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    seen = 0
    for row in rows[:-1]:
        seen += 1
        if row["grower"] != rows[seen]["grower"]:
            ax.axhline(seen - 0.5, color="white", linewidth=3.0)
    ax.set_title("Corn share of CDL pixels by field and year", loc="left", fontweight="bold")
    colorbar = fig.colorbar(image, ax=ax, fraction=0.04, pad=0.02)
    colorbar.set_label("Corn share", fontsize=8)
    colorbar.ax.tick_params(labelsize=7)
    sources = "; ".join(
        f"{farm.meta.short}: {farm.cdl.source}" for farm in usable
    )
    footnote(fig, f"CDL: {sources}. Pixel-weighted class shares; rows grouped by grower.")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def figure_crop_acres(data: list[FarmData]) -> plt.Figure:
    usable = [farm for farm in data if farm.cdl is not None]
    table = field_year_table(usable)
    per_year = (
        table.groupby(["grower", "year"])[["corn_acres", "soy_acres", "other_acres"]]
        .sum()
        .reset_index()
    )
    growers = [farm.meta.label for farm in usable]
    fig, axes = plt.subplots(1, len(growers), figsize=(4.8 * len(growers), 4.9), sharey=True)
    if len(growers) == 1:
        axes = [axes]
    classes = [(CORN, "corn_acres"), (SOY, "soy_acres"), ("Other", "other_acres")]
    for ax, grower in zip(axes, growers):
        subset = per_year[per_year["grower"] == grower].sort_values("year")
        if subset.empty:
            ax.text(0.5, 0.5, "No CDL", transform=ax.transAxes, ha="center", va="center")
            ax.set_title(grower, loc="left", fontweight="bold")
            continue
        bottom = np.zeros(len(subset))
        for crop, column in classes:
            values = subset[column].to_numpy(dtype=float)
            ax.bar(
                subset["year"].astype(int).astype(str),
                values,
                bottom=bottom,
                color=CROP_COLORS[crop],
                width=0.72,
                label=crop,
                edgecolor="white",
                linewidth=0.6,
            )
            bottom += values
        ax.set_title(grower, loc="left", fontweight="bold")
        ax.set_xlabel("CDL year")
        style_axes(ax, grid_axis="y")
    axes[0].set_ylabel("Mapped acres (pixel-weighted)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=CROP_COLORS[crop]) for crop, _ in classes]
    fig.suptitle(
        "Crop class acreage by grower and year",
        x=0.01,
        y=0.995,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    fig.legend(
        handles,
        [crop for crop, _ in classes],
        loc="lower center",
        ncol=len(classes),
        frameon=False,
        fontsize=9,
        bbox_to_anchor=(0.5, 0.028),
    )
    footnote(fig, "Each CDL pixel = 30 m x 30 m = 0.2224 ac; acres exclude No Data pixels.", y=0.002)
    fig.tight_layout(rect=(0, 0.085, 1, 0.93))
    return fig


def figure_size_vs_diversity(data: list[FarmData]) -> plt.Figure:
    usable = [farm for farm in data if farm.cdl is not None]
    table = field_year_table(usable)
    acres = {
        (farm.meta.label, str(row.field_id)): float(row.area_acres)
        for farm in usable
        for row in farm.boundaries.itertuples(index=False)
    }
    table = table.assign(acres=[acres.get((row.grower, str(row.field_id)), np.nan) for row in table.itertuples()])
    table = table.dropna(subset=["acres"])

    # Distinct crop classes are integer and often saturate; fall back to Shannon
    # diversity when the class count carries no usable variation.
    y_field = "n_crop_classes"
    y_label = "Distinct crop classes per field-year (>= 5% share)"
    if table[y_field].nunique() < 2:
        y_field = "crop_diversity"
        y_label = "Shannon crop diversity per field-year"

    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    for farm in usable:
        subset = table[table["grower"] == farm.meta.label]
        if subset.empty:
            continue
        x = subset["acres"].to_numpy(dtype=float)
        y = subset[y_field].to_numpy(dtype=float)
        offset = jitter(len(y), width=0.06) if y_field == "n_crop_classes" else 0.0
        ax.scatter(
            x,
            y + offset,
            s=38,
            color=farm.meta.color,
            edgecolor="white",
            linewidth=0.5,
            alpha=0.85,
            label=farm.meta.label,
            zorder=3,
        )
    rho, p_value = spearman(table["acres"].to_numpy(dtype=float), table[y_field].to_numpy(dtype=float))
    per_grower = []
    for farm in usable:
        subset = table[table["grower"] == farm.meta.label]
        if len(subset) >= 3:
            r, _ = spearman(subset["acres"].to_numpy(dtype=float), subset[y_field].to_numpy(dtype=float))
            per_grower.append(f"{farm.meta.short} rho = {r:.2f}")
    ax.set_xscale("log")
    ax.set_xlabel("Field area (acres, log scale)")
    ax.set_ylabel(y_label)
    ax.set_title("Does field size explain crop diversity?", loc="left", fontweight="bold")
    ax.text(
        0.02,
        0.98,
        f"Spearman rho = {rho:.2f} ({p_label(p_value)}), n = {len(table)} field-years\n"
        + " | ".join(per_grower),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8.8,
        bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "#cccccc"},
    )
    if y_field == "n_crop_classes":
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.set_ylim(0.6, max(3.2, float(table[y_field].max()) + 0.6))
    style_axes(ax)
    grower_legend(ax, [farm.meta for farm in usable], loc="upper right", fontsize=9)
    footnote(fig, "Each point is one field-year; diversity counts CDL classes covering >= 5% of the field.")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def dominant_crop(data: list[FarmData], year: int) -> dict[str, str]:
    """field_id -> dominant CDL crop name for ``year`` (or the latest year)."""
    out: dict[str, str] = {}
    for farm in data:
        if farm.cdl is None:
            continue
        frame = farm.cdl.frame
        years = sorted(frame["year"].unique())
        target = year if year in years else years[-1]
        subset = frame[(frame["year"] == target) & (~frame["crop_name"].isin(EXCLUDED_CLASSES))]
        for field_id, group in subset.groupby("field_id"):
            top = group.sort_values("pixel_count", ascending=False).iloc[0]
            out[str(field_id)] = str(top["crop_name"])
    return out


def run(data: list[FarmData]) -> dict[str, Any]:
    usable = [farm for farm in data if farm.cdl is not None]
    if not usable:
        raise RuntimeError("No CDL composition data available for any farm")

    table = field_year_table(usable)
    summary = summary_table(usable, table)

    figures = [
        save_figure(figure_rotation(usable), "cdl_01_rotation_heatmap.png"),
        save_figure(figure_crop_acres(usable), "cdl_02_crop_acres_by_grower_year.png"),
        save_figure(figure_size_vs_diversity(usable), "cdl_03_size_vs_diversity.png"),
    ]

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(TABLE_DIR / "cdl_field_year.csv", index=False)
    summary.to_csv(TABLE_DIR / "cdl_summary.csv", index=False)

    acres = {
        (farm.meta.label, str(row.field_id)): float(row.area_acres)
        for farm in usable
        for row in farm.boundaries.itertuples(index=False)
    }
    table = table.assign(acres=[acres.get((row.grower, str(row.field_id)), np.nan) for row in table.itertuples()])
    table = table.dropna(subset=["acres"])
    y_field = "n_crop_classes"
    if table[y_field].nunique() < 2:
        y_field = "crop_diversity"
    rho, p_value = spearman(table["acres"].to_numpy(dtype=float), table[y_field].to_numpy(dtype=float))
    _, corn_p = kruskal(
        [group["corn_share"].to_numpy() for _, group in table.groupby("grower")]
    )
    return {
        "figures": [str(path) for path in figures],
        "tables": [str(TABLE_DIR / "cdl_field_year.csv"), str(TABLE_DIR / "cdl_summary.csv")],
        "tests": {
            "cdl.corn_share_kruskal_p": round(corn_p, 4),
            "cdl.size_diversity_spearman_rho": round(rho, 3),
            "cdl.size_diversity_spearman_p": round(p_value, 4),
            "cdl.diversity_field": y_field,
        },
    }
