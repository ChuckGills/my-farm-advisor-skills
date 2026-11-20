#!/usr/bin/env python3
"""Assignment 2 field-level EDA: boundaries, CDL, and weather.

Produces three reviewable static figures plus tidy statistics tables:

* boundaries: field size, shape compactness, and a cross-grower test
* CDL: per-field corn rotation heatmap, crop diversity, and corn-share test
* weather: annual growing-season GDD, precipitation distributions, and a
  GDD-precipitation correlation

The generator reads existing runtime pipeline outputs only. It never downloads
or rewrites farm data. Missing layers are skipped and recorded in
``data_manifest.json`` instead of failing the run.

Run from the installed runtime source tree:

    export DATA_PIPELINE_DATA_ROOT=/path/to/runtime
    cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline/src"
    python scripts/eda/assignment2_eda.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for _candidate in (_SCRIPTS_DIR, _SCRIPTS_DIR / "lib"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from lib.paths import DATA_ROOT, farm_boundary_path  # noqa: E402

OUTPUT_DIR = DATA_ROOT / "eda" / "assignment-2"
GROWING_SEASON_MONTHS = (4, 10)
GDD_BASE_C = 10.0
GDD_CAP_C = 30.0
MIN_WEATHER_ROWS = 300
ARCHIVE_PATTERN = "archive/*/fields/*/weather/daily_weather.csv"


@dataclass(frozen=True)
class FarmMeta:
    grower: str
    farm: str
    label: str
    short: str
    color: str


FARMS: tuple[FarmMeta, ...] = (
    FarmMeta("il-corn-grower", "il-corn-grower-illinois", "Illinois", "IL", "#2F6D9E"),
    FarmMeta("ia-corn-grower", "ia-corn-grower-iowa", "Iowa", "IA", "#D08A2E"),
    FarmMeta("ne-corn-grower", "ne-corn-grower-nebraska", "Nebraska", "NE", "#3F8F5B"),
)


@dataclass
class FarmData:
    meta: FarmMeta
    boundaries: gpd.GeoDataFrame | None = None
    cdl: pd.DataFrame | None = None
    cdl_source: str = "missing"
    cdl_years: list[int] = field(default_factory=list)
    weather: pd.DataFrame | None = None
    weather_sources: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- helpers


def _read_csv(path: Path, *, min_rows: int = 1) -> pd.DataFrame | None:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return None
        frame = pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return None
    if len(frame) < min_rows:
        return None
    return frame


def _latest_cdl_table(farm_dir: Path) -> tuple[Path | None, str]:
    tables = farm_dir / "derived" / "tables"
    if not tables.is_dir():
        return None, "missing"
    candidates = sorted(tables.glob("*_cdl_*_full_composition.csv"))
    if not candidates:
        return None, "missing"
    preferred = [p for p in candidates if "_2021_2025_" in p.name]
    chosen = preferred[0] if preferred else candidates[-1]
    return chosen, ("2021-2025" if preferred else "latest available")


def _load_boundaries(meta: FarmMeta) -> gpd.GeoDataFrame | None:
    path = farm_boundary_path(meta.grower, meta.farm)
    if not path.exists():
        return None
    frame = gpd.read_file(path)
    if frame.empty:
        return None
    frame = frame.copy()
    frame["field_id"] = frame["field_id"].astype(str)
    projected = frame.to_crs("EPSG:5070")
    frame["area_acres_calc"] = projected.area / 4046.8564224
    frame["perimeter_m"] = projected.length
    frame["compactness"] = (
        4.0 * math.pi * projected.area / (projected.length**2)
    ).clip(lower=0.0, upper=1.0)
    frame["grower"] = meta.short
    return frame


def _load_cdl(
    meta: FarmMeta, current_ids: set[str], *, allow_archive: bool
) -> tuple[pd.DataFrame | None, str, list[int], list[str]]:
    """Return CDL composition rows, a source label, years, and notes."""
    farm_dir = DATA_ROOT / "growers" / meta.grower / "farms" / meta.farm
    path, window = _latest_cdl_table(farm_dir)
    if path is None:
        return None, "missing", [], [f"{meta.short}: no CDL composition table"]
    frame = _read_csv(path, min_rows=1)
    if frame is None:
        return None, "missing", [], [f"{meta.short}: CDL table unreadable"]

    frame = frame.copy()
    frame["field_id"] = frame["field_id"].astype(str)
    matching = frame[frame["field_id"].isin(current_ids)]
    notes: list[str] = []
    matched_fields = int(matching["field_id"].nunique())
    keep_previous = matched_fields == 0 or matched_fields < max(2, len(current_ids) // 2)
    if keep_previous and not allow_archive:
        return None, "missing", [], [
            f"{meta.short}: CDL table only covers previous-sample fields"
        ]
    if keep_previous:
        source = "previous-sample"
        notes.append(
            f"{meta.short}: CDL uses the previous sample because the current "
            "pipeline has not written reseeded-field CDL yet"
        )
    else:
        frame = matching.copy()
        source = "current"
    years = sorted(int(year) for year in frame["year"].unique())
    frame["year"] = frame["year"].astype(int)
    return frame, f"{source} ({window})", years, notes


def _field_year_cdl(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (field_id, year), group in frame.groupby(["field_id", "year"], sort=True):
        group = group[~group["crop_name"].isin(["No Data", "Unknown"])]
        total = float(group["pixel_count"].sum())
        if total <= 0:
            continue
        shares = {
            str(row.crop_name): float(row.pixel_count) / total
            for row in group.itertuples(index=False)
        }
        rows.append(
            {
                "field_id": str(field_id),
                "year": int(year),
                "corn_share": shares.get("Corn", 0.0),
                "soy_share": shares.get("Soybeans", 0.0),
                "other_share": max(0.0, 1.0 - shares.get("Corn", 0.0) - shares.get("Soybeans", 0.0)),
                "crop_shares": shares,
            }
        )
    return pd.DataFrame(rows)


def _shannon_diversity(shares: dict[str, float]) -> float:
    values = [p for p in shares.values() if p > 0]
    if len(values) <= 1:
        return 0.0
    return float(-sum(p * math.log(p) for p in values))


def _field_diversity(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for field_id, group in frame.groupby("field_id", sort=True):
        group = group[~group["crop_name"].isin(["No Data", "Unknown"])]
        totals = group.groupby("crop_name")["pixel_count"].sum()
        total = float(totals.sum())
        if total <= 0:
            continue
        shares = {str(k): float(v) / total for k, v in totals.items()}
        corn_share = shares.get("Corn", 0.0)
        rows.append(
            {
                "field_id": str(field_id),
                "crop_diversity": _shannon_diversity(shares),
                "corn_share": corn_share,
                "soy_share": shares.get("Soybeans", 0.0),
                "n_crop_classes": len(shares),
            }
        )
    return pd.DataFrame(rows)


def _load_weather(
    meta: FarmMeta,
    current_ids: set[str],
    *,
    allow_archive: bool,
) -> tuple[pd.DataFrame | None, dict[str, str], list[str]]:
    farm_dir = DATA_ROOT / "growers" / meta.grower / "farms" / meta.farm
    frames: list[pd.DataFrame] = []
    sources: dict[str, str] = {}
    notes: list[str] = []

    for field_id in sorted(current_ids):
        path = farm_dir / "fields" / field_id / "weather" / "daily_weather.csv"
        frame = _read_csv(path, min_rows=MIN_WEATHER_ROWS)
        if frame is None:
            continue
        frame = frame.copy()
        frame["field_id"] = frame["field_id"].astype(str)
        frames.append(frame)
        sources[field_id] = "current"
    if len(frames) >= len(current_ids) or not allow_archive:
        if not frames:
            notes.append(f"{meta.short}: no complete current weather series")
        return _concat_weather(frames), sources, notes

    archived = sorted(farm_dir.glob(ARCHIVE_PATTERN))
    used_archive = 0
    for path in archived:
        frame = _read_csv(path, min_rows=MIN_WEATHER_ROWS)
        if frame is None:
            continue
        frame = frame.copy()
        frame["field_id"] = frame["field_id"].astype(str)
        field_id = str(frame["field_id"].iloc[0])
        if field_id in sources:
            continue
        frames.append(frame)
        sources[field_id] = "archive"
        used_archive += 1
    if used_archive:
        notes.append(
            f"{meta.short}: {used_archive} archived previous-sample weather "
            "series used because the current pipeline is still running"
        )
    if not frames:
        notes.append(f"{meta.short}: no complete weather series found")
    return _concat_weather(frames), sources, notes


def _concat_weather(frames: list[pd.DataFrame]) -> pd.DataFrame | None:
    if not frames:
        return None
    frame = pd.concat(frames, ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame[(frame["date"].dt.year >= 2021) & (frame["date"].dt.year <= 2025)]
    if frame.empty:
        return None
    return frame


def _weather_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.month
    frame["gdd"] = (
        ((frame["T2M_MAX"] + frame["T2M_MIN"]) / 2.0)
        .clip(lower=GDD_BASE_C, upper=GDD_CAP_C)
        - GDD_BASE_C
    )
    season = frame[
        (frame["month"] >= GROWING_SEASON_MONTHS[0])
        & (frame["month"] <= GROWING_SEASON_MONTHS[1])
    ]
    grouped = (
        season.groupby(["field_id", "year"], sort=True)
        .agg(
            gdd=("gdd", "sum"),
            precip_mm=("PRECTOTCORR", "sum"),
            days=("date", "nunique"),
        )
        .reset_index()
    )
    return grouped[grouped["days"] >= 180].reset_index(drop=True)


# --------------------------------------------------------------------------- figures


def _apply_axes_style(ax: plt.Axes) -> None:
    ax.grid(True, axis="both", color="#dddddd", linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def _grower_legend(ax: plt.Axes, metas: list[FarmMeta], **kwargs: Any) -> None:
    handles = [
        Line2D([0], [0], marker="o", linestyle="", color=meta.color, label=meta.label)
        for meta in metas
    ]
    ax.legend(handles=handles, frameon=False, **kwargs)


def _jitter(n: int, width: float = 0.12) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.uniform(-width, width, n)


def _box_groups(
    ax: plt.Axes,
    groups: list[tuple[FarmMeta, np.ndarray]],
    *,
    log: bool = False,
) -> None:
    usable = [(meta, values) for meta, values in groups if len(values)]
    positions = np.arange(1, len(usable) + 1)
    data = [values for _, values in usable]
    labels = [meta.label for meta, _ in usable]
    if not data:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center", va="center")
        return
    bp = ax.boxplot(
        data,
        positions=positions,
        widths=0.55,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#333333", "linewidth": 1.5},
    )
    for patch, (meta, _) in zip(bp["boxes"], usable):
        patch.set_facecolor(meta.color)
        patch.set_alpha(0.30)
        patch.set_edgecolor(meta.color)
    for pos, (meta, values) in zip(positions, usable):
        ax.scatter(
            pos + _jitter(len(values)),
            values,
            s=26,
            color=meta.color,
            edgecolor="white",
            linewidth=0.5,
            alpha=0.9,
            zorder=4,
        )
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    if log:
        ax.set_yscale("log")


def _kruskal(groups: list[np.ndarray]) -> tuple[float, float]:
    usable = [g for g in groups if len(g) >= 2]
    if len(usable) < 2:
        return float("nan"), float("nan")
    try:
        result = stats.kruskal(*usable)
        return float(result.statistic), float(result.pvalue)
    except ValueError:
        return float("nan"), float("nan")


def _p_label(p: float) -> str:
    if not np.isfinite(p):
        return "n/a"
    if p < 0.001:
        return "p < 0.001"
    return f"p = {p:.3f}"


def figure_boundaries(data: list[FarmData]) -> tuple[Path, pd.DataFrame]:
    usable = [d for d in data if d.boundaries is not None and not d.boundaries.empty]
    if not usable:
        raise RuntimeError("No boundary data available for any farm")

    fig, axes = plt.subplots(1, 3, figsize=(16.0, 5.2))
    fig.suptitle(
        "Field boundaries: size distribution, shape compactness, and cross-grower comparison",
        fontsize=14,
        fontweight="bold",
        y=0.985,
    )

    ax = axes[0]
    groups = [
        (d.meta, d.boundaries["area_acres_calc"].to_numpy()) for d in usable
    ]
    _box_groups(ax, groups, log=True)
    ax.set_ylabel("Field area (acres, log scale)")
    ax.set_title("A. Field size by grower", loc="left", fontweight="bold")
    _apply_axes_style(ax)
    for idx, (meta, values) in enumerate(groups, start=1):
        ax.text(
            idx,
            ax.get_ylim()[1] * 0.93,
            f"n={len(values)}",
            ha="center",
            va="top",
            fontsize=9,
            color="#555555",
        )

    ax = axes[1]
    for d in usable:
        ax.scatter(
            d.boundaries["area_acres_calc"],
            d.boundaries["compactness"],
            s=42,
            color=d.meta.color,
            edgecolor="white",
            linewidth=0.5,
            alpha=0.9,
            label=d.meta.label,
        )
    all_area = np.concatenate([d.boundaries["area_acres_calc"].to_numpy() for d in usable])
    all_compact = np.concatenate([d.boundaries["compactness"].to_numpy() for d in usable])
    shape_rho, shape_p = stats.spearmanr(all_area, all_compact)
    ax.set_xscale("log")
    ax.set_xlabel("Field area (acres, log scale)")
    ax.set_ylabel("Polsby-Popper compactness (1 = circle)")
    ax.set_title(
        f"B. Compactness vs. size (rho = {shape_rho:.2f}, {_p_label(float(shape_p))})",
        loc="left",
        fontweight="bold",
    )
    ax.axhline(0.785, color="#888888", linestyle=":", linewidth=1.0, zorder=1)
    ax.text(
        ax.get_xlim()[1],
        0.795,
        "circle reference",
        ha="right",
        va="bottom",
        fontsize=8,
        color="#777777",
    )
    _apply_axes_style(ax)
    _grower_legend(ax, [d.meta for d in usable], loc="lower right", fontsize=9)

    ax = axes[2]
    for d in usable:
        values = np.sort(d.boundaries["compactness"].to_numpy())
        if len(values) == 0:
            continue
        y = np.arange(1, len(values) + 1) / len(values)
        ax.step(values, y, where="post", color=d.meta.color, linewidth=2.0, label=d.meta.label)
    _, p_value = _kruskal(
        [d.boundaries["compactness"].to_numpy() for d in usable]
    )
    ax.set_xlabel("Polsby-Popper compactness")
    ax.set_ylabel("Cumulative share of fields")
    ax.set_title(
        f"C. Compactness distributions (KW {_p_label(p_value)})",
        loc="left",
        fontweight="bold",
    )
    ax.set_xlim(0.0, 1.02)
    ax.set_ylim(0.0, 1.02)
    _apply_axes_style(ax)
    _grower_legend(ax, [d.meta for d in usable], loc="lower right", fontsize=9)

    rows: list[dict[str, Any]] = []
    for d in usable:
        frame = d.boundaries
        rows.append(
            {
                "grower": d.meta.label,
                "fields": int(len(frame)),
                "acres_total": round(float(frame["area_acres_calc"].sum()), 1),
                "acres_median": round(float(frame["area_acres_calc"].median()), 1),
                "acres_min": round(float(frame["area_acres_calc"].min()), 1),
                "acres_max": round(float(frame["area_acres_calc"].max()), 1),
                "compactness_median": round(float(frame["compactness"].median()), 3),
                "compactness_min": round(float(frame["compactness"].min()), 3),
                "compactness_max": round(float(frame["compactness"].max()), 3),
            }
        )
    stats_frame = pd.DataFrame(rows)
    area_h, area_p = _kruskal([d.boundaries["area_acres_calc"].to_numpy() for d in usable])
    comp_h, comp_p = _kruskal([d.boundaries["compactness"].to_numpy() for d in usable])
    stats_frame.attrs["kruskal_area_p"] = area_p
    stats_frame.attrs["kruskal_compactness_p"] = comp_p

    notes = "Boundaries: current reseeded farm boundaries (EPSG:5070 areas)."
    fig.text(0.995, 0.005, notes, ha="right", va="bottom", fontsize=7.0, color="#666666")
    fig.tight_layout(rect=(0, 0.035, 1, 0.93))
    out = OUTPUT_DIR / "assignment2_boundaries.png"
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    return out, stats_frame


def figure_cdl(data: list[FarmData]) -> tuple[Path, pd.DataFrame] | None:
    usable = [d for d in data if d.cdl is not None and not d.cdl.empty]
    if not usable:
        return None

    fig = plt.figure(figsize=(16.0, 6.3))
    grid = fig.add_gridspec(1, 3, width_ratios=(1.55, 1.0, 1.0), wspace=0.30)
    fig.suptitle(
        "CDL/cropland: within-field rotation, crop diversity, and corn share by grower",
        fontsize=14,
        fontweight="bold",
        y=0.985,
    )

    ax = fig.add_subplot(grid[0, 0])
    field_year = pd.concat(
        [
            _field_year_cdl(d.cdl).assign(
                grower=d.meta.short, grower_label=d.meta.label
            )
            for d in usable
        ],
        ignore_index=True,
    )
    pivot = field_year.pivot_table(
        index=["grower", "field_id"], columns="year", values="corn_share", aggfunc="mean"
    )
    grower_order = {meta.short: idx for idx, meta in enumerate(FARMS)}
    pivot = (
        pivot.reset_index()
        .assign(__order=lambda f: f["grower"].map(grower_order))
        .sort_values(["__order", "field_id"])
        .drop(columns="__order")
        .set_index(["grower", "field_id"])
    )
    matrix = pivot.to_numpy(dtype=float)
    years = [int(year) for year in pivot.columns]
    image = ax.imshow(
        np.ma.masked_invalid(matrix),
        aspect="auto",
        cmap="YlGn",
        vmin=0.0,
        vmax=1.0,
        interpolation="nearest",
    )
    ax.set_xticks(np.arange(len(years)))
    ax.set_xticklabels([str(year) for year in years], rotation=0)
    labels = []
    counters: dict[str, int] = {}
    for grower, field_id in pivot.index:
        counters[grower] = counters.get(grower, 0) + 1
        labels.append(f"{grower}-{counters[grower]:02d}")
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            if np.isfinite(value):
                ax.text(
                    j,
                    i,
                    f"{value:.0%}",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color="white" if value > 0.55 else "#333333",
                )
    ax.set_title("A. Corn share of CDL pixels by field and year", loc="left", fontweight="bold")
    colorbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02)
    colorbar.set_label("Corn share", fontsize=8)
    colorbar.ax.tick_params(labelsize=7)

    ax = fig.add_subplot(grid[0, 1])
    groups = []
    for d in usable:
        diversity = _field_diversity(d.cdl)
        groups.append((d.meta, diversity["crop_diversity"].to_numpy()))
    _box_groups(ax, groups)
    ax.set_ylabel("Shannon diversity across CDL crops")
    ax.set_title("B. Crop diversity by field", loc="left", fontweight="bold")
    _apply_axes_style(ax)

    ax = fig.add_subplot(grid[0, 2])
    groups = []
    for d in usable:
        diversity = _field_diversity(d.cdl)
        groups.append((d.meta, diversity["corn_share"].to_numpy()))
    _box_groups(ax, groups)
    _, p_value = _kruskal([values for _, values in groups])
    ax.set_ylabel("Corn share (all years)")
    ax.set_ylim(-0.03, 1.03)
    ax.set_title(
        f"C. Corn share by grower (KW {_p_label(p_value)})",
        loc="left",
        fontweight="bold",
        fontsize=11,
    )
    _apply_axes_style(ax)

    rows: list[dict[str, Any]] = []
    for d in usable:
        diversity = _field_diversity(d.cdl)
        rows.append(
            {
                "grower": d.meta.label,
                "cdl_source": d.cdl_source,
                "cdl_years": ",".join(str(y) for y in d.cdl_years),
                "fields": int(diversity["field_id"].nunique()),
                "corn_share_median": round(float(diversity["corn_share"].median()), 3),
                "crop_diversity_median": round(float(diversity["crop_diversity"].median()), 3),
            }
        )
    stats_frame = pd.DataFrame(rows)
    stats_frame.attrs["kruskal_corn_share_p"] = p_value

    notes = []
    for d in usable:
        if d.cdl_source.startswith("previous-sample"):
            notes.append(f"{d.meta.short}: previous-sample CDL")
        else:
            notes.append(f"{d.meta.short}: current CDL {d.cdl_years[0]}-{d.cdl_years[-1]}")
    missing = [d.meta.short for d in data if d.cdl is None or d.cdl.empty]
    if missing:
        notes.append("no CDL yet: " + ", ".join(missing))
    fig.text(
        0.995,
        0.005,
        "CDL: " + "; ".join(notes) + ". Pixel-weighted class shares.",
        ha="right",
        va="bottom",
        fontsize=7.0,
        color="#666666",
    )
    fig.subplots_adjust(top=0.88, bottom=0.10, left=0.06, right=0.985)
    out = OUTPUT_DIR / "assignment2_cdl.png"
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    return out, stats_frame


def figure_weather(data: list[FarmData]) -> tuple[Path, pd.DataFrame] | None:
    usable: list[tuple[FarmMeta, pd.DataFrame]] = []
    for d in data:
        if d.weather is None or d.weather.empty:
            continue
        metrics = _weather_metrics(d.weather)
        if metrics.empty:
            continue
        usable.append((d.meta, metrics))
    if not usable:
        return None

    fig, axes = plt.subplots(1, 3, figsize=(16.0, 5.4))
    fig.suptitle(
        "Weather: growing-season GDD, precipitation, and their cross-grower relationship",
        fontsize=14,
        fontweight="bold",
        y=0.985,
    )

    ax = axes[0]
    for meta, metrics in usable:
        for field_id, group in metrics.groupby("field_id"):
            group = group.sort_values("year")
            ax.plot(
                group["year"],
                group["gdd"],
                color=meta.color,
                linewidth=1.0,
                alpha=0.35,
                zorder=2,
            )
        mean = metrics.groupby("year")["gdd"].mean().sort_index()
        ax.plot(
            mean.index,
            mean.values,
            color=meta.color,
            linewidth=3.0,
            marker="o",
            markersize=4,
            label=meta.label,
            zorder=4,
        )
    ax.set_xticks([2021, 2022, 2023, 2024, 2025])
    ax.set_ylabel("Growing-season GDD (base 10 °C, cap 30 °C)")
    ax.set_title("A. Annual GDD by field (thin) and grower mean (bold)", loc="left", fontweight="bold")
    _apply_axes_style(ax)
    _grower_legend(ax, [meta for meta, _ in usable], loc="lower right", fontsize=9)

    ax = axes[1]
    groups = [(meta, metrics["precip_mm"].to_numpy()) for meta, metrics in usable]
    _box_groups(ax, groups)
    ax.set_ylabel("Growing-season precipitation (mm)")
    ax.set_title("B. Seasonal precipitation by grower", loc="left", fontweight="bold")
    _apply_axes_style(ax)

    ax = axes[2]
    correlation_rows: list[dict[str, Any]] = []
    for meta, metrics in usable:
        ax.scatter(
            metrics["precip_mm"],
            metrics["gdd"],
            s=34,
            color=meta.color,
            edgecolor="white",
            linewidth=0.4,
            alpha=0.9,
            label=meta.label,
        )
        if len(metrics) >= 3:
            rho, p_value = stats.spearmanr(metrics["precip_mm"], metrics["gdd"])
            correlation_rows.append(
                {
                    "grower": meta.label,
                    "spearman_n": int(len(metrics)),
                    "spearman_rho": round(float(rho), 3),
                    "p_value": round(float(p_value), 4),
                }
            )
    combined = pd.concat([frame for _, frame in usable], ignore_index=True)
    low, high = ax.get_ylim()
    ax.set_ylim(low, high + 0.32 * (high - low))
    if len(combined) >= 3:
        rho, p_value = stats.spearmanr(combined["precip_mm"], combined["gdd"])
        ax.text(
            0.02,
            0.98,
            f"All growers: rho = {rho:.2f} ({_p_label(float(p_value))})\n"
            + "\n".join(
                f"{row['grower']}: rho = {row['spearman_rho']:.2f}"
                for row in correlation_rows
            ),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8.5,
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#cccccc"},
        )
    ax.set_xlabel("Growing-season precipitation (mm)")
    ax.set_ylabel("Growing-season GDD")
    ax.set_title("C. GDD vs. precipitation (field-years)", loc="left", fontweight="bold")
    _apply_axes_style(ax)
    _grower_legend(ax, [meta for meta, _ in usable], loc="lower left", fontsize=9)

    rows: list[dict[str, Any]] = []
    for meta, metrics in usable:
        rows.append(
            {
                "grower": meta.label,
                "fields": int(metrics["field_id"].nunique()),
                "field_years": int(len(metrics)),
                "gdd_mean": round(float(metrics["gdd"].mean()), 0),
                "gdd_sd": round(float(metrics["gdd"].std(ddof=1)), 0),
                "precip_mean_mm": round(float(metrics["precip_mm"].mean()), 0),
                "precip_sd_mm": round(float(metrics["precip_mm"].std(ddof=1)), 0),
            }
        )
    for row in correlation_rows:
        match = next(r for r in rows if r["grower"] == row["grower"])
        match.update({k: v for k, v in row.items() if k != "grower"})
    if len(combined) >= 3:
        rho, p_value = stats.spearmanr(combined["precip_mm"], combined["gdd"])
        stats_frame = pd.DataFrame(rows)
        stats_frame.attrs["overall_spearman_rho"] = float(rho)
        stats_frame.attrs["overall_spearman_p"] = float(p_value)
    else:
        stats_frame = pd.DataFrame(rows)

    notes = []
    for d in data:
        archived = sum(1 for source in d.weather_sources.values() if source == "archive")
        if archived:
            notes.append(f"{d.meta.short}: {archived} archived previous-sample fields")
    missing = [d.meta.short for d in data if d.weather is None or d.weather.empty]
    if missing:
        notes.append("no weather yet: " + ", ".join(missing))
    if not notes:
        notes.append("current reseeded fields")
    fig.text(
        0.995,
        0.005,
        "Weather: " + "; ".join(notes) + ". GDD uses (Tmax+Tmin)/2, base 10 °C, cap 30 °C; season Apr-Oct.",
        ha="right",
        va="bottom",
        fontsize=7.0,
        color="#666666",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.93))
    out = OUTPUT_DIR / "assignment2_weather.png"
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    return out, stats_frame


# --------------------------------------------------------------------------- main


def _load_farm(meta: FarmMeta, *, allow_archive: bool) -> FarmData:
    data = FarmData(meta=meta)
    data.boundaries = _load_boundaries(meta)
    current_ids = (
        set(data.boundaries["field_id"].astype(str)) if data.boundaries is not None else set()
    )
    if data.boundaries is None:
        data.notes.append(f"{meta.short}: no boundary file")
        return data

    cdl, cdl_source, cdl_years, cdl_notes = _load_cdl(
        meta, current_ids, allow_archive=allow_archive
    )
    data.cdl = cdl
    data.cdl_source = cdl_source
    data.cdl_years = cdl_years
    data.notes.extend(cdl_notes)

    weather, sources, weather_notes = _load_weather(
        meta, current_ids, allow_archive=allow_archive
    )
    data.weather = weather
    data.weather_sources = sources
    data.notes.extend(weather_notes)
    return data


def _manifest(
    data: list[FarmData], figures: list[Path], tests: dict[str, float]
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": "assignment-2",
        "output_dir": str(OUTPUT_DIR.relative_to(DATA_ROOT)),
        "figures": [path.name for path in figures],
        "tests": tests,
        "farms": [
            {
                "grower": d.meta.grower,
                "farm": d.meta.farm,
                "label": d.meta.label,
                "fields": int(len(d.boundaries)) if d.boundaries is not None else 0,
                "cdl_source": d.cdl_source,
                "cdl_years": d.cdl_years,
                "weather_fields": len(d.weather_sources),
                "weather_archive_fields": sum(
                    1 for source in d.weather_sources.values() if source == "archive"
                ),
                "notes": d.notes,
            }
            for d in data
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-archive-fallback",
        action="store_true",
        help=(
            "Use archived previous-sample weather and CDL when the current "
            "reseeded pipeline has not produced data yet"
        ),
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = [_load_farm(meta, allow_archive=args.allow_archive_fallback) for meta in FARMS]

    written: list[Path] = []
    tests: dict[str, float] = {}
    boundary_out, boundary_stats = figure_boundaries(data)
    boundary_stats.to_csv(OUTPUT_DIR / "assignment2_boundaries_stats.csv", index=False)
    written.append(boundary_out)
    for key, value in boundary_stats.attrs.items():
        tests[key] = round(float(value), 4)

    cdl_result = figure_cdl(data)
    if cdl_result is not None:
        cdl_out, cdl_stats = cdl_result
        cdl_stats.to_csv(OUTPUT_DIR / "assignment2_cdl_stats.csv", index=False)
        written.append(cdl_out)
        for key, value in cdl_stats.attrs.items():
            tests[key] = round(float(value), 4)

    weather_result = figure_weather(data)
    if weather_result is not None:
        weather_out, weather_stats = weather_result
        weather_stats.to_csv(OUTPUT_DIR / "assignment2_weather_stats.csv", index=False)
        written.append(weather_out)
        for key, value in weather_stats.attrs.items():
            tests[key] = round(float(value), 4)

    manifest = _manifest(data, written, tests)
    (OUTPUT_DIR / "data_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Output: {OUTPUT_DIR}")
    for path in written:
        print(f"  {path.name}")
    for item in manifest["farms"]:
        print(
            f"  {item['label']:10s} fields={item['fields']:2d} "
            f"cdl={item['cdl_source']:24s} weather_fields={item['weather_fields']}"
        )
    if any(item["notes"] for item in manifest["farms"]):
        print("Notes:")
        for item in manifest["farms"]:
            for note in item["notes"]:
                print(f"  - {note}")


if __name__ == "__main__":
    main()
