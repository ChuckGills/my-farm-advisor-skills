#!/usr/bin/env python3
"""CDL/cropland EDA: rotation, crop mix, and rotation intensity vs. field size.

Outputs
-------
figures/cdl_01_rotation_grid.png
figures/cdl_02_crop_share_by_grower_year.png
figures/cdl_03_rotation_vs_size.png
tables/cdl_field_year.csv
tables/cdl_field_stats.csv
tables/cdl_summary.csv
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.ticker import FuncFormatter, NullFormatter
from matplotlib.patches import Patch

from .common import (
    CDL_PIXEL_ACRES,
    CORN,
    CROP_COLORS,
    DIVERSITY_MIN_SHARE,
    SOY,
    TABLE_DIR,
    FarmData,
    footnote,
    jitter,
    kruskal,
    p_label,
    save_figure,
    spearman,
    style_axes,
)

INK_TEXT = "#1F2933"
EXCLUDED_CLASSES = {"No Data", "Unknown"}
MIXED_THRESHOLD = 0.80
DOMINANT_CODES = {"corn": 0, "soy": 1, "other": 2, "missing": 3}
DOMINANT_NAMES = {0: CORN, 1: SOY, 2: "Other", 3: "No CDL"}


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
            other_share = float(max(0.0, 1.0 - corn_share - soy_share))
            dominant = max(
                (("corn", corn_share), ("soy", soy_share), ("other", other_share)),
                key=lambda item: item[1],
            )
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
                    "other_share": round(other_share, 4),
                    "dominant_crop": dominant[0],
                    "dominant_share": round(float(dominant[1]), 4),
                    "n_crop_classes": int(len(significant)),
                    "crop_diversity": round(_shannon(shares), 4),
                }
            )
    return pd.DataFrame(rows)


def field_rotation_table(table: pd.DataFrame, data: list[FarmData]) -> pd.DataFrame:
    """One row per field: acres and rotation history across the CDL window."""
    acres = {
        (farm.meta.label, str(row.field_id)): float(row.area_acres)
        for farm in data
        if farm.boundaries is not None
        for row in farm.boundaries.itertuples(index=False)
    }
    rows: list[dict[str, Any]] = []
    for (grower, field_id), group in table.groupby(["grower", "field_id"], sort=True):
        group = group.sort_values("year")
        crops = group["dominant_crop"].tolist()
        switches = sum(1 for prev, cur in zip(crops, crops[1:]) if prev != cur)
        rows.append(
            {
                "grower": grower,
                "field_id": field_id,
                "acres": round(acres.get((grower, field_id), float("nan")), 2),
                "cdl_years": int(len(group)),
                "corn_years": int((group["dominant_crop"] == "corn").sum()),
                "soy_years": int((group["dominant_crop"] == "soy").sum()),
                "other_years": int((group["dominant_crop"] == "other").sum()),
                "corn_share_mean": round(float(group["corn_share"].mean()), 3),
                "switches": int(switches),
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
    """Small multiples: one 10-field block per grower, years across."""
    table = field_year_table(data)
    usable = [farm for farm in data if farm.cdl is not None]
    years = sorted(table["year"].unique())

    fig, axes = plt.subplots(
        1, len(usable), figsize=(12.6, 4.9), sharey=True, gridspec_kw={"wspace": 0.12}
    )
    if len(usable) == 1:
        axes = [axes]

    colors = [
        CROP_COLORS[CORN],
        CROP_COLORS[SOY],
        CROP_COLORS["Other"],
        CROP_COLORS["No CDL"],
    ]
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(np.arange(-0.5, 4.5, 1.0), cmap.N)

    for ax, farm in zip(axes, usable):
        subset = table[table["grower"] == farm.meta.label]
        field_ids = sorted(subset["field_id"].unique())
        matrix = np.full((len(field_ids), len(years)), DOMINANT_CODES["missing"], dtype=float)
        mixed: list[tuple[int, int]] = []
        for i, field_id in enumerate(field_ids):
            block = subset[subset["field_id"] == field_id]
            for j, year in enumerate(years):
                row = block[block["year"] == year]
                if row.empty:
                    continue
                matrix[i, j] = DOMINANT_CODES.get(str(row["dominant_crop"].iloc[0]),
                                                  DOMINANT_CODES["missing"])
                if float(row["dominant_share"].iloc[0]) < MIXED_THRESHOLD:
                    mixed.append((i, j))
        ax.pcolormesh(
            np.arange(len(years) + 1),
            np.arange(len(field_ids) + 1),
            matrix,
            cmap=cmap,
            norm=norm,
            edgecolors="white",
            linewidth=1.2,
        )
        if mixed:
            ax.scatter(
                [j + 0.5 for _, j in mixed],
                [i + 0.5 for i, _ in mixed],
                s=34,
                facecolor="none",
                edgecolor="#1B1B1B",
                linewidth=1.1,
                zorder=5,
            )
        ax.set_xlim(0, len(years))
        ax.set_ylim(len(field_ids), 0)
        ax.set_xticks(np.arange(len(years)) + 0.5)
        ax.set_xticklabels([str(year) for year in years], fontsize=9.5)
        ax.set_yticks(np.arange(len(field_ids)) + 0.5)
        ax.set_yticklabels([f"{idx + 1:02d}" for idx in range(len(field_ids))], fontsize=8.5)
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        count = int(subset["field_id"].nunique())
        ax.set_title(
            f"{farm.meta.label} ({farm.meta.short}) \u00b7 {count} fields",
            loc="left",
            fontweight="bold",
            fontsize=11.5,
            pad=8,
        )
        ax.set_xlabel("CDL year", fontsize=9.5)

    axes[0].set_ylabel("field", fontsize=9.5)
    fig.suptitle(
        "Dominant crop per field: a stripe is rotation, repeated gold is continuous corn",
        x=0.005,
        y=0.985,
        ha="left",
        fontsize=12.5,
        fontweight="bold",
    )
    handles = [
        Patch(facecolor=CROP_COLORS[CORN], label=CORN),
        Patch(facecolor=CROP_COLORS[SOY], label=SOY),
        Patch(facecolor=CROP_COLORS["Other"], label="Other crop"),
        Patch(
            facecolor="none",
            edgecolor="#1B1B1B",
            linewidth=1.1,
            label=f"Dot: no crop reaches {MIXED_THRESHOLD:.0%}",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=4,
        frameon=False,
        fontsize=9.5,
        handlelength=1.2,
    )
    footnote(fig, "CDL 2021-2025; dominant class by pixel share.", y=0.012)
    fig.subplots_adjust(left=0.055, right=0.985, top=0.795, bottom=0.26, wspace=0.12)
    return fig


def figure_crop_share(data: list[FarmData]) -> plt.Figure:
    table = field_year_table(data)
    per_year = (
        table.groupby(["grower", "year"])[["corn_acres", "soy_acres", "other_acres"]]
        .sum()
        .reset_index()
    )
    per_year["total_acres"] = per_year[["corn_acres", "soy_acres", "other_acres"]].sum(axis=1)
    growers = [farm.meta.label for farm in data if farm.cdl is not None]
    fig, axes = plt.subplots(1, len(growers), figsize=(4.3 * len(growers), 4.6), sharey=True)
    if len(growers) == 1:
        axes = [axes]
    classes = [(CORN, "corn_acres"), (SOY, "soy_acres"), ("Other", "other_acres")]
    for ax, grower in zip(axes, growers):
        subset = per_year[per_year["grower"] == grower].sort_values("year")
        if subset.empty:
            ax.text(0.5, 0.5, "No CDL", transform=ax.transAxes, ha="center", va="center")
            ax.set_title(grower, loc="left", fontweight="bold")
            continue
        years = subset["year"].astype(int).astype(str).tolist()
        bottom = np.zeros(len(subset))
        for crop, column in classes:
            shares = (subset[column] / subset["total_acres"]).to_numpy(dtype=float) * 100.0
            ax.bar(
                years,
                shares,
                bottom=bottom,
                color=CROP_COLORS[crop],
                width=0.72,
                label=crop,
                edgecolor="white",
                linewidth=0.8,
            )
            bottom += shares
        for x, (_, row) in zip(years, subset.iterrows()):
            ax.text(
                x,
                101.0,
                f"{row['total_acres']:,.0f} ac",
                ha="center",
                va="bottom",
                fontsize=8,
                color="#444444",
            )
        ax.set_title(grower, loc="left", fontweight="bold", fontsize=12)
        ax.set_xlabel("CDL year")
        ax.set_ylim(0, 118)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
        style_axes(ax, grid_axis="y")
    axes[0].set_ylabel("Share of mapped cropland")
    handles = [Patch(facecolor=CROP_COLORS[crop], label=crop) for crop, _ in classes]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(handles),
        frameon=False,
        fontsize=9.5,
        bbox_to_anchor=(0.5, 0.045),
    )
    fig.suptitle(
        "Corn share: Nebraska stays above half, Illinois alternates",
        x=0.005,
        y=0.99,
        ha="left",
        fontsize=12.5,
        fontweight="bold",
    )
    footnote(
        fig,
        "Each bar is 100% of that grower-year, so farm size does not distort the comparison; "
        "totals above bars are absolute mapped acres.",
        y=0.008,
    )
    fig.tight_layout(rect=(0, 0.15, 1, 0.93))
    return fig


def figure_rotation_vs_size(data: list[FarmData]) -> plt.Figure:
    table = field_year_table(data)
    fields = field_rotation_table(table, data).dropna(subset=["acres"])
    usable = [farm for farm in data if farm.cdl is not None]
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.9))

    ax = axes[0]
    for farm in usable:
        subset = fields[fields["grower"] == farm.meta.label]
        if subset.empty:
            continue
        ax.scatter(
            subset["acres"],
            subset["corn_years"] + jitter(len(subset), width=0.07),
            s=62,
            color=farm.meta.color,
            edgecolor="white",
            linewidth=0.7,
            alpha=0.9,
            label=farm.meta.label,
            zorder=3,
        )
    rho, p_value = spearman(
        fields["acres"].to_numpy(dtype=float), fields["corn_years"].to_numpy(dtype=float)
    )
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Field area (acres, log scale)")
    ax.set_ylabel("Years in corn out of 5")
    ax.set_yticks([0, 1, 2, 3, 4, 5])
    ax.set_ylim(-0.6, 5.6)
    ax.set_title("One point per field", loc="left", fontweight="bold", fontsize=11.5)
    ax.text(
        0.03,
        0.96,
        f"Spearman rho = {rho:.2f} ({p_label(p_value)})\nn = {len(fields)} fields",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox={"facecolor": "white", "alpha": 0.92, "edgecolor": "#dddddd"},
    )
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    style_axes(ax, grid_axis="y")

    ax = axes[1]
    bins = pd.qcut(fields["acres"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
    binned = (
        fields.assign(size_quartile=bins)
        .groupby("size_quartile", observed=True)
        .agg(
            median_corn=("corn_years", "median"),
            low=("acres", "min"),
            high=("acres", "max"),
            n=("corn_years", "size"),
        )
    )
    positions = np.arange(len(binned))
    ax.bar(
        positions,
        binned["median_corn"],
        width=0.62,
        color="#8FA9BF",
        edgecolor="white",
        linewidth=0.8,
        zorder=3,
    )
    for pos, (_, row) in zip(positions, binned.iterrows()):
        ax.text(
            pos,
            float(row["median_corn"]) + 0.12,
            f"{float(row['median_corn']):.1f}",
            ha="center",
            va="bottom",
            fontsize=10,
            color=INK_TEXT,
            fontweight="bold",
        )
    ax.set_xticks(positions)
    ax.set_xticklabels(
        [
            f"{row['low']:,.0f}-{row['high']:,.0f} ac\n(n={int(row['n'])})"
            for _, row in binned.iterrows()
        ],
        fontsize=8.5,
    )
    ax.set_ylim(0, 5)
    ax.set_yticks([0, 1, 2, 3, 4, 5])
    ax.set_ylabel("Median years in corn out of 5")
    ax.set_title(
        "Same answer by size quartile", loc="left", fontweight="bold", fontsize=11.5
    )
    ax.annotate(
        f"Spearman rho = {rho:.2f} ({p_label(p_value)})",
        xy=(0.03, 0.96),
        xycoords="axes fraction",
        ha="left",
        va="top",
        fontsize=9,
        bbox={"facecolor": "white", "alpha": 0.92, "edgecolor": "#dddddd"},
    )
    style_axes(ax, grid_axis="y")
    ax.margins(x=0.06)

    footnote(
        fig,
        "One point per field. A year counts as corn (soy) when corn (soy) is the dominant "
        "CDL class. p-values are corrected across the report's tests.",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
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
    fields = field_rotation_table(table, usable)
    summary = summary_table(usable, table)

    figures = [
        save_figure(figure_rotation(usable), "cdl_01_rotation_grid.png"),
        save_figure(figure_crop_share(usable), "cdl_02_crop_share_by_grower_year.png"),
        save_figure(figure_rotation_vs_size(usable), "cdl_03_rotation_vs_size.png"),
    ]

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(TABLE_DIR / "cdl_field_year.csv", index=False)
    fields.to_csv(TABLE_DIR / "cdl_field_stats.csv", index=False)
    summary.to_csv(TABLE_DIR / "cdl_summary.csv", index=False)

    rho, rho_p = spearman(
        fields["acres"].to_numpy(dtype=float), fields["corn_years"].to_numpy(dtype=float)
    )
    _, corn_p = kruskal(
        [group["corn_share"].to_numpy() for _, group in table.groupby("grower")]
    )
    _, corn_years_p = kruskal(
        [group["corn_years"].to_numpy() for _, group in fields.groupby("grower")]
    )
    return {
        "figures": [str(path) for path in figures],
        "tables": [
            str(TABLE_DIR / "cdl_field_year.csv"),
            str(TABLE_DIR / "cdl_field_stats.csv"),
            str(TABLE_DIR / "cdl_summary.csv"),
        ],
        "tests": {
            "cdl.corn_share_kruskal_p": round(corn_p, 4),
            "cdl.corn_years_kruskal_p": round(corn_years_p, 4),
            "cdl.size_corn_years_spearman_rho": round(rho, 3),
            "cdl.size_corn_years_spearman_p": round(rho_p, 4),
        },
    }
