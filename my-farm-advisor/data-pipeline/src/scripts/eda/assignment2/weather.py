#!/usr/bin/env python3
"""Weather EDA: multi-year field series, monthly profiles, and grower comparison.

Outputs
-------
figures/weather_01_gdd_precip_by_year.png
figures/weather_02_monthly_profile.png
figures/weather_03_grower_comparison.png
tables/weather_field_year.csv
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
    grower_legend,
    kruskal,
    p_label,
    save_figure,
    style_axes,
    weather_field_year,
)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def field_year_metrics(data: list[FarmData]) -> pd.DataFrame:
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
    usable = [farm for farm in data if farm.weather is not None]
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2))

    for ax, column, ylabel, title in (
        (axes[0], "gdd", "Growing-season GDD (base 10 \u00b0C, cap 30 \u00b0C)", "Growing-season heat by year"),
        (axes[1], "precip_mm", "Growing-season precipitation (mm)", "Growing-season rainfall by year"),
    ):
        for farm in usable:
            subset = metrics[metrics["grower"] == farm.meta.label]
            for _, group in subset.groupby("field_id"):
                group = group.sort_values("year")
                ax.plot(
                    group["year"],
                    group[column],
                    color=farm.meta.color,
                    linewidth=0.8,
                    alpha=0.22,
                    zorder=2,
                )
            mean = subset.groupby("year")[column].mean().sort_index()
            if not mean.empty:
                ax.plot(
                    mean.index,
                    mean.values,
                    color=farm.meta.color,
                    linewidth=2.8,
                    marker="o",
                    markersize=4,
                    label=farm.meta.label,
                    zorder=4,
                )
        ax.set_xticks(sorted(metrics["year"].unique()))
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontweight="bold")
        style_axes(ax)
    grower_legend(axes[0], [farm.meta for farm in usable], loc="upper left", fontsize=9)
    footnote(
        fig,
        "Thin lines = one field, bold = grower mean. Season Apr 1 - Oct 31; "
        "field-years need >= 180 daily records.",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def figure_monthly(data: list[FarmData]) -> plt.Figure:
    monthly = monthly_metrics(data)
    usable = [farm for farm in data if farm.weather is not None]
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2))

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
                alpha=0.12,
                linewidth=0,
            )
            ax.plot(
                stats.index,
                stats["mean"],
                color=farm.meta.color,
                linewidth=2.2,
                marker="o",
                markersize=3.5,
                label=farm.meta.label,
            )
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(MONTHS, fontsize=8.5)
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontweight="bold")
        style_axes(ax)
    grower_legend(axes[0], [farm.meta for farm in usable], loc="upper left", fontsize=9)
    footnote(fig, "Lines = grower mean, band = field-to-field range. Monthly values averaged over 2021-2025.")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def figure_comparison(data: list[FarmData]) -> plt.Figure:
    metrics = field_year_metrics(data)
    usable = [farm for farm in data if farm.weather is not None]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.2))

    for ax, column, ylabel, title in (
        (axes[0], "gdd", "Growing-season GDD", "Heat by grower"),
        (axes[1], "precip_mm", "Growing-season precipitation (mm)", "Rainfall by grower"),
    ):
        groups = [
            (farm.meta, metrics.loc[metrics["grower"] == farm.meta.label, column].to_numpy())
            for farm in usable
        ]
        box_groups(ax, groups)
        _, p_value = kruskal([values for _, values in groups])
        eta = eta_squared([values for _, values in groups])
        ax.set_ylabel(ylabel)
        ax.set_title(
            f"{title}\nKW {p_label(p_value)}, eta2 = {eta:.2f}",
            loc="left",
            fontweight="bold",
            fontsize=11,
        )
        style_axes(ax)
    footnote(fig, "Kruskal-Wallis across growers; eta2 = share of field-year variance explained by grower.")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def summary_table(metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for grower, group in metrics.groupby("grower"):
        rows.append(
            {
                "grower": grower,
                "fields": int(group["field_id"].nunique()),
                "field_years": int(len(group)),
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
    monthly = monthly_metrics(usable)

    figures = [
        save_figure(figure_annual(usable), "weather_01_gdd_precip_by_year.png"),
        save_figure(figure_monthly(usable), "weather_02_monthly_profile.png"),
        save_figure(figure_comparison(usable), "weather_03_grower_comparison.png"),
    ]

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(TABLE_DIR / "weather_field_year.csv", index=False)
    monthly.to_csv(TABLE_DIR / "weather_monthly.csv", index=False)
    summary = summary_table(metrics)
    summary.to_csv(TABLE_DIR / "weather_summary.csv", index=False)

    _, gdd_p = kruskal([group["gdd"].to_numpy() for _, group in metrics.groupby("grower")])
    _, precip_p = kruskal([group["precip_mm"].to_numpy() for _, group in metrics.groupby("grower")])
    gdd_eta = eta_squared([group["gdd"].to_numpy() for _, group in metrics.groupby("grower")])
    precip_eta = eta_squared([group["precip_mm"].to_numpy() for _, group in metrics.groupby("grower")])
    return {
        "figures": [str(path) for path in figures],
        "tables": [
            str(TABLE_DIR / "weather_field_year.csv"),
            str(TABLE_DIR / "weather_monthly.csv"),
            str(TABLE_DIR / "weather_summary.csv"),
        ],
        "tests": {
            "weather.gdd_kruskal_p": round(gdd_p, 4),
            "weather.precip_kruskal_p": round(precip_p, 4),
            "weather.gdd_grower_eta2": round(gdd_eta, 3),
            "weather.precip_grower_eta2": round(precip_eta, 3),
        },
    }
