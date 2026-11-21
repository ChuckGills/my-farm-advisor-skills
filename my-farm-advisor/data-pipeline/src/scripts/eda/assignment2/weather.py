#!/usr/bin/env python3
"""Weather EDA: multi-year heat and rainfall, monthly profiles, grower comparison.

Weather comes from NASA POWER, which serves one series per ~0.5 degree grid
cell, so fields in the same cell share an identical daily series. ``weather_units``
collapses those duplicates before anything is tested: the effective samples are
distinct weather cells, not fields.

Outputs
-------
figures/weather_01_gdd_precip_by_year.png
figures/weather_02_monthly_profile.png
figures/weather_03_grower_comparison.png
tables/weather_field_year.csv
tables/weather_grower_year.csv
tables/weather_monthly.csv
tables/weather_summary.csv
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common import (
    TABLE_DIR,
    FarmData,
    add_gdd,
    box_groups,
    eta_squared,
    footnote,
    kruskal,
    p_label,
    ranking_consistency,
    save_figure,
    style_axes,
    weather_field_year,
    year_block_test,
)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
UNIT_COLUMNS = ["year", "gdd", "precip_mm"]


def field_year_metrics(data: list[FarmData]) -> pd.DataFrame:
    """One row per field-year (every field kept, duplicates included)."""
    frames = []
    for farm in data:
        if farm.weather is None or farm.weather.frame.empty:
            continue
        metrics = weather_field_year(farm.weather.frame)
        if metrics.empty:
            continue
        metrics = metrics.assign(grower=farm.meta.label)
        frames.append(metrics)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)[
        ["grower", "field_id", "year", "gdd", "precip_mm", "days"]
    ]


def weather_units(metrics: pd.DataFrame) -> pd.DataFrame:
    """Collapse field-years that share one grid cell into cell-years."""
    if metrics.empty:
        return metrics
    return metrics.drop_duplicates(subset=["grower", *UNIT_COLUMNS]).reset_index(drop=True)


def cell_counts(units: pd.DataFrame) -> dict[str, int]:
    """Distinct grid cells per grower (the cells present in every year)."""
    counts: dict[str, int] = {}
    for grower, group in units.groupby("grower"):
        per_year = (
            group.drop_duplicates(subset=UNIT_COLUMNS).groupby("year").size()
        )
        counts[grower] = int(per_year.min()) if len(per_year) else 0
    return counts


def grower_year_table(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for grower, group in metrics.groupby("grower"):
        for year, block in group.groupby("year"):
            rows.append(
                {
                    "grower": grower,
                    "year": int(year),
                    "fields": int(block["field_id"].nunique()),
                    "cells": int(len(block.drop_duplicates(subset=UNIT_COLUMNS))),
                    "gdd_mean": round(float(block["gdd"].mean()), 1),
                    "gdd_min": round(float(block["gdd"].min()), 1),
                    "gdd_max": round(float(block["gdd"].max()), 1),
                    "precip_mean_mm": round(float(block["precip_mm"].mean()), 1),
                    "precip_min_mm": round(float(block["precip_mm"].min()), 1),
                    "precip_max_mm": round(float(block["precip_mm"].max()), 1),
                }
            )
    return pd.DataFrame(rows)


def monthly_metrics(data: list[FarmData]) -> pd.DataFrame:
    frames = []
    for farm in data:
        if farm.weather is None or farm.weather.frame.empty:
            continue
        frame = add_gdd(farm.weather.frame)
        frame["year"] = frame["date"].dt.year
        frame["month"] = frame["date"].dt.month
        per_field_year = (
            frame.groupby(["field_id", "year", "month"])
            .agg(t2m=("T2M", "mean"), precip_mm=("PRECTOTCORR", "sum"))
            .reset_index()
        )
        per_field = (
            per_field_year.groupby(["field_id", "month"])
            .agg(t2m=("t2m", "mean"), precip_mm=("precip_mm", "mean"))
            .reset_index()
        )
        per_field = per_field.assign(grower=farm.meta.label)
        frames.append(per_field)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def figure_annual(data: list[FarmData]) -> plt.Figure:
    metrics = field_year_metrics(data)
    units = weather_units(metrics)
    usable = [farm for farm in data if farm.weather is not None]
    years = sorted(metrics["year"].unique())
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.0))

    for ax, column, ylabel, title in (
        (
            axes[0],
            "gdd",
            "Growing-season GDD (base 10 \u00b0C)",
            "Heat: grower mean and spread between weather cells",
        ),
        (
            axes[1],
            "precip_mm",
            "Growing-season precipitation (mm)",
            "Rainfall: grower mean and spread between weather cells",
        ),
    ):
        for farm in usable:
            subset = units[units["grower"] == farm.meta.label]
            if subset.empty:
                continue
            stats = subset.groupby("year")[column].agg(["mean", "min", "max"]).sort_index()
            ax.fill_between(
                stats.index,
                stats["min"],
                stats["max"],
                color=farm.meta.color,
                alpha=0.16,
                linewidth=0,
                zorder=2,
            )
            ax.plot(
                stats.index,
                stats["mean"],
                color=farm.meta.color,
                linewidth=3.0,
                marker="o",
                markersize=6,
                markeredgecolor="white",
                markeredgewidth=1.0,
                zorder=4,
            )
            last = stats.index.max()
            ax.annotate(
                farm.meta.label,
                xy=(last, float(stats.loc[last, "mean"])),
                xytext=(8, 0),
                textcoords="offset points",
                va="center",
                color=farm.meta.color,
                fontweight="bold",
                fontsize=10,
                annotation_clip=False,
            )
        ax.set_xticks(years)
        ax.set_xlim(years[0] - 0.35, years[-1] + 0.9)
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontweight="bold", fontsize=11.5)
        style_axes(ax, grid_axis="y")

    counts = cell_counts(units)
    cell_counts_text = ", ".join(
        f"{farm.meta.short} {counts[farm.meta.label]} cells"
        for farm in usable
        if counts.get(farm.meta.label)
    )
    footnote(
        fig,
        "Bold line = grower mean; band = range between distinct weather grid cells "
        f"({cell_counts_text}). Season Apr 1 - Oct 31.",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    return fig


def figure_monthly(data: list[FarmData]) -> plt.Figure:
    monthly = monthly_metrics(data)
    usable = [farm for farm in data if farm.weather is not None]
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.0))

    for ax, column, ylabel, title in (
        (axes[0], "t2m", "Mean air temperature (\u00b0C)", "Monthly temperature profile"),
        (axes[1], "precip_mm", "Mean monthly precipitation (mm)", "Monthly rainfall profile"),
    ):
        for farm in usable:
            subset = monthly[monthly["grower"] == farm.meta.label]
            if subset.empty:
                continue
            stats = subset.groupby("month")[column].agg(["mean", "min", "max"]).sort_index()
            ax.fill_between(
                stats.index,
                stats["min"],
                stats["max"],
                color=farm.meta.color,
                alpha=0.13,
                linewidth=0,
            )
            ax.plot(
                stats.index,
                stats["mean"],
                color=farm.meta.color,
                linewidth=2.4,
                marker="o",
                markersize=4,
                label=farm.meta.label,
                zorder=3,
            )
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(MONTHS, fontsize=9)
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontweight="bold", fontsize=11.5)
        style_axes(ax, grid_axis="y")
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    footnote(
        fig,
        "Line = grower mean, band = field-to-field range, averaged over 2021-2025. "
        "Shared grid cells make some fields identical.",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    return fig


def figure_comparison(data: list[FarmData]) -> plt.Figure:
    metrics = field_year_metrics(data)
    units = weather_units(metrics)
    usable = [farm for farm in data if farm.weather is not None]
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 5.0))

    for ax, column, ylabel, title in (
        (axes[0], "gdd", "Growing-season GDD", "Heat by grower"),
        (axes[1], "precip_mm", "Growing-season precipitation (mm)", "Rainfall by grower"),
    ):
        groups = [
            (farm.meta, units.loc[units["grower"] == farm.meta.label, column].to_numpy())
            for farm in usable
        ]
        box_groups(ax, groups)
        _, p_value = year_block_test(units, column)
        eta = eta_squared([values for _, values in groups])
        wins, total = ranking_consistency(units, column, "Nebraska")
        wide = units.pivot_table(index="year", columns="grower", values=column, aggfunc="mean")
        leaders = int(wide.idxmax(axis=1).nunique()) if not wide.empty else 0
        if wins * 2 >= total:
            rank_line = f"Nebraska highest in {wins}/{total} years"
        else:
            rank_line = f"{leaders} growers take the lead in different years"
        ax.set_ylabel(ylabel)
        ax.set_title(
            f"{title}  \u00b7  year-blocked Friedman {p_label(p_value)}\n"
            f"grower explains {eta:.0%} of cell-year variance; {rank_line}",
            loc="left",
            fontsize=10.5,
            pad=8,
        )
        style_axes(ax, grid_axis="y")

    footnote(
        fig,
        "Each point is a distinct weather cell-year, not a field: fields in the same "
        "NASA POWER cell share one series. Years are the replication unit for the test.",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    return fig


def summary_table(metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for grower, group in metrics.groupby("grower"):
        cells = group.drop_duplicates(subset=["field_id", *UNIT_COLUMNS])
        rows.append(
            {
                "grower": grower,
                "fields": int(group["field_id"].nunique()),
                "field_years": int(len(group)),
                "weather_cells": int(cells["field_id"].nunique()),
                "gdd_mean": round(float(group["gdd"].mean()), 0),
                "gdd_sd": round(float(group["gdd"].std(ddof=1)), 0),
                "precip_mean_mm": round(float(group["precip_mm"].mean()), 0),
                "precip_sd_mm": round(float(group["precip_mm"].std(ddof=1)), 0),
            }
        )
    return pd.DataFrame(rows)


def run(data: list[FarmData]) -> dict[str, Any]:
    usable = [farm for farm in data if farm.weather is not None and not farm.weather.frame.empty]
    if not usable:
        raise RuntimeError("No weather data available for any farm")

    metrics = field_year_metrics(usable)
    units = weather_units(metrics)
    monthly = monthly_metrics(usable)
    grower_year = grower_year_table(metrics)

    figures = [
        save_figure(figure_annual(usable), "weather_01_gdd_precip_by_year.png"),
        save_figure(figure_monthly(usable), "weather_02_monthly_profile.png"),
        save_figure(figure_comparison(usable), "weather_03_grower_comparison.png"),
    ]

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(TABLE_DIR / "weather_field_year.csv", index=False)
    grower_year.to_csv(TABLE_DIR / "weather_grower_year.csv", index=False)
    monthly.to_csv(TABLE_DIR / "weather_monthly.csv", index=False)
    summary_table(metrics).to_csv(TABLE_DIR / "weather_summary.csv", index=False)

    _, gdd_p = year_block_test(units, "gdd")
    _, precip_p = year_block_test(units, "precip_mm")
    _, gdd_cell_p = kruskal(
        [group["gdd"].to_numpy() for _, group in units.groupby("grower")]
    )
    _, precip_cell_p = kruskal(
        [group["precip_mm"].to_numpy() for _, group in units.groupby("grower")]
    )
    gdd_eta = eta_squared([group["gdd"].to_numpy() for _, group in units.groupby("grower")])
    precip_eta = eta_squared(
        [group["precip_mm"].to_numpy() for _, group in units.groupby("grower")]
    )
    return {
        "figures": [str(path) for path in figures],
        "tables": [
            str(TABLE_DIR / "weather_field_year.csv"),
            str(TABLE_DIR / "weather_grower_year.csv"),
            str(TABLE_DIR / "weather_monthly.csv"),
            str(TABLE_DIR / "weather_summary.csv"),
        ],
        "tests": {
            "weather.gdd_friedman_p": round(gdd_p, 4),
            "weather.precip_friedman_p": round(precip_p, 4),
            "weather.gdd_grower_eta2": round(gdd_eta, 3),
            "weather.precip_grower_eta2": round(precip_eta, 3),
            "weather.gdd_cell_kruskal_p": round(gdd_cell_p, 6),
            "weather.precip_cell_kruskal_p": round(precip_cell_p, 6),
            "weather.weather_cells": int(sum(cell_counts(units).values())),
            "weather.cell_years": int(len(units)),
            "weather.field_years": int(len(metrics)),
        },
    }
