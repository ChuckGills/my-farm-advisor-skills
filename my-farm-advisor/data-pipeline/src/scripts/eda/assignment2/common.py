#!/usr/bin/env python3
"""Shared loaders, styling, and statistics for the Assignment 2 EDA.

The EDA is read-only: it consumes canonical runtime outputs under
``$DATA_PIPELINE_DATA_ROOT/data-pipeline`` and never downloads or rewrites farm
data. Missing layers are returned as ``None`` with a note instead of raising.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
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

from lib.paths import DATA_ROOT, farm_boundary_path  # noqa: E402

OUT_ROOT = DATA_ROOT / "eda" / "assignment-2"
FIG_DIR = OUT_ROOT / "figures"
TABLE_DIR = OUT_ROOT / "tables"

GROWING_SEASON = (4, 10)
GDD_BASE_C = 10.0
GDD_CAP_C = 30.0
MIN_WEATHER_ROWS = 300
MIN_SEASON_DAYS = 180
DIVERSITY_MIN_SHARE = 0.05
CDL_PIXEL_ACRES = 30.0 * 30.0 / 4046.8564224
ARCHIVE_GLOB = "archive/*/fields/*/weather/daily_weather.csv"

CORN = "Corn"
SOY = "Soybeans"
CROP_COLORS = {
    CORN: "#E0A32E",
    SOY: "#4F7D3A",
    "Other": "#8A8F98",
    "No CDL": "#D5D8DD",
}


@dataclass(frozen=True)
class FarmMeta:
    grower: str
    farm: str
    label: str
    short: str
    state: str
    county: str
    color: str


FARMS: tuple[FarmMeta, ...] = (
    FarmMeta("il-corn-grower", "il-corn-grower-illinois", "Illinois", "IL", "IL", "Iroquois", "#2F6D9E"),
    FarmMeta("ia-corn-grower", "ia-corn-grower-iowa", "Iowa", "IA", "IA", "Kossuth", "#D08A2E"),
    FarmMeta("ne-corn-grower", "ne-corn-grower-nebraska", "Nebraska", "NE", "NE", "York", "#3F8F5B"),
)


@dataclass
class CdlLayer:
    frame: pd.DataFrame
    source: str
    years: list[int]
    notes: list[str] = field(default_factory=list)


@dataclass
class WeatherLayer:
    frame: pd.DataFrame
    sources: dict[str, str]
    notes: list[str] = field(default_factory=list)


@dataclass
class FarmData:
    meta: FarmMeta
    boundaries: gpd.GeoDataFrame | None = None
    cdl: CdlLayer | None = None
    weather: WeatherLayer | None = None
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------- loading


def read_csv(path: Path, *, min_rows: int = 1) -> pd.DataFrame | None:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return None
        frame = pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return None
    if len(frame) < min_rows:
        return None
    return frame


def farm_dir(meta: FarmMeta) -> Path:
    return DATA_ROOT / "growers" / meta.grower / "farms" / meta.farm


def load_boundaries(meta: FarmMeta) -> gpd.GeoDataFrame | None:
    path = farm_boundary_path(meta.grower, meta.farm)
    if not path.exists():
        return None
    frame = gpd.read_file(path)
    if frame.empty:
        return None
    frame = frame.copy()
    frame["field_id"] = frame["field_id"].astype(str)
    projected = frame.to_crs("EPSG:5070")
    frame["area_acres"] = projected.area / 4046.8564224
    frame["perimeter_m"] = projected.length
    frame["compactness"] = (
        4.0 * math.pi * projected.area / (projected.length**2)
    ).clip(lower=0.0, upper=1.0)
    return frame


def latest_cdl_table(meta: FarmMeta) -> tuple[Path | None, str]:
    tables = farm_dir(meta) / "derived" / "tables"
    if not tables.is_dir():
        return None, "missing"
    candidates = sorted(tables.glob("*_cdl_*_full_composition.csv"))
    if not candidates:
        return None, "missing"
    preferred = [path for path in candidates if "_2021_2025_" in path.name]
    chosen = preferred[0] if preferred else candidates[-1]
    return chosen, ("2021-2025" if preferred else "latest available")


def load_cdl(
    meta: FarmMeta, current_ids: set[str], *, allow_archive: bool
) -> CdlLayer | None:
    path, window = latest_cdl_table(meta)
    if path is None:
        return None
    frame = read_csv(path, min_rows=1)
    if frame is None:
        return None

    frame = frame.copy()
    frame["field_id"] = frame["field_id"].astype(str)
    matching = frame[frame["field_id"].isin(current_ids)]
    matched_fields = int(matching["field_id"].nunique())
    notes: list[str] = []
    keep_previous = matched_fields == 0 or matched_fields < max(2, len(current_ids) // 2)
    if keep_previous:
        if not allow_archive:
            return None
        source = "previous-sample"
        notes.append(
            f"{meta.short}: CDL uses the previous sample because the current "
            "pipeline has not written reseeded-field CDL yet"
        )
    else:
        frame = matching.copy()
        source = "current"
    frame["year"] = frame["year"].astype(int)
    frame["pixel_count"] = frame["pixel_count"].astype(float)
    years = sorted(int(year) for year in frame["year"].unique())
    return CdlLayer(frame=frame, source=f"{source} ({window})", years=years, notes=notes)


def load_weather(
    meta: FarmMeta, current_ids: set[str], *, allow_archive: bool
) -> WeatherLayer | None:
    root = farm_dir(meta)
    frames: list[pd.DataFrame] = []
    sources: dict[str, str] = {}
    notes: list[str] = []

    for field_id in sorted(current_ids):
        path = root / "fields" / field_id / "weather" / "daily_weather.csv"
        frame = read_csv(path, min_rows=MIN_WEATHER_ROWS)
        if frame is None:
            continue
        frame = frame.copy()
        frame["field_id"] = str(field_id)
        frames.append(frame)
        sources[field_id] = "current"

    if len(frames) < len(current_ids) and allow_archive:
        for path in sorted(root.glob(ARCHIVE_GLOB)):
            frame = read_csv(path, min_rows=MIN_WEATHER_ROWS)
            if frame is None:
                continue
            frame = frame.copy()
            field_id = str(frame["field_id"].iloc[0])
            if field_id in sources:
                continue
            frame["field_id"] = field_id
            frames.append(frame)
            sources[field_id] = "archive"
        archived = sum(1 for value in sources.values() if value == "archive")
        if archived:
            notes.append(
                f"{meta.short}: {archived} archived previous-sample weather "
                "series used because the current pipeline is still running"
            )

    if not frames:
        notes.append(f"{meta.short}: no complete weather series found")
        return None
    frame = pd.concat(frames, ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame[(frame["date"].dt.year >= 2021) & (frame["date"].dt.year <= 2025)]
    if frame.empty:
        return None
    return WeatherLayer(frame=frame, sources=sources, notes=notes)


def load_farm(meta: FarmMeta, *, allow_archive: bool) -> FarmData:
    data = FarmData(meta=meta)
    data.boundaries = load_boundaries(meta)
    if data.boundaries is None:
        data.notes.append(f"{meta.short}: no boundary file")
        return data
    ids = set(data.boundaries["field_id"].astype(str))
    data.cdl = load_cdl(meta, ids, allow_archive=allow_archive)
    if data.cdl is not None:
        data.notes.extend(data.cdl.notes)
    data.weather = load_weather(meta, ids, allow_archive=allow_archive)
    if data.weather is not None:
        data.notes.extend(data.weather.notes)
    return data


# --------------------------------------------------------------------- metrics


def add_gdd(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["gdd"] = (
        ((frame["T2M_MAX"] + frame["T2M_MIN"]) / 2.0)
        .clip(lower=GDD_BASE_C, upper=GDD_CAP_C)
        - GDD_BASE_C
    )
    return frame


def weather_field_year(frame: pd.DataFrame) -> pd.DataFrame:
    frame = add_gdd(frame)
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.month
    season = frame[
        (frame["month"] >= GROWING_SEASON[0]) & (frame["month"] <= GROWING_SEASON[1])
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
    return grouped[grouped["days"] >= MIN_SEASON_DAYS].reset_index(drop=True)


# --------------------------------------------------------------------- analysis


def kruskal(groups: list[np.ndarray]) -> tuple[float, float]:
    usable = [np.asarray(group, dtype=float) for group in groups if len(group) >= 2]
    if len(usable) < 2:
        return float("nan"), float("nan")
    try:
        result = stats.kruskal(*usable)
    except ValueError:
        return float("nan"), float("nan")
    return float(result.statistic), float(result.pvalue)


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 3 or len(y) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan"), float("nan")
    result = stats.spearmanr(x, y)
    return float(result.statistic), float(result.pvalue)


def eta_squared(groups: list[np.ndarray]) -> float:
    """Share of total variance explained by group membership (one-way)."""
    usable = [np.asarray(group, dtype=float) for group in groups if len(group)]
    if len(usable) < 2:
        return float("nan")
    all_values = np.concatenate(usable)
    grand = float(all_values.mean())
    ss_between = sum(len(group) * (float(group.mean()) - grand) ** 2 for group in usable)
    ss_total = float(((all_values - grand) ** 2).sum())
    if ss_total <= 0:
        return float("nan")
    return float(ss_between / ss_total)


def p_label(p: float) -> str:
    if not np.isfinite(p):
        return "n/a"
    if p < 0.001:
        return "p < 0.001"
    return f"p = {p:.3f}"


# --------------------------------------------------------------------- plotting


def style_axes(ax: plt.Axes, *, grid_axis: str = "both") -> None:
    ax.grid(True, axis=grid_axis, color="#dddddd", linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def grower_legend(ax: plt.Axes, metas: list[FarmMeta], **kwargs: Any) -> None:
    handles = [
        Line2D([0], [0], marker="o", linestyle="", color=meta.color, label=meta.label)
        for meta in metas
    ]
    ax.legend(handles=handles, frameon=False, **kwargs)


def jitter(n: int, width: float = 0.12) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.uniform(-width, width, n)


def box_groups(
    ax: plt.Axes,
    groups: list[tuple[FarmMeta, np.ndarray]],
    *,
    log: bool = False,
) -> None:
    usable = [(meta, np.asarray(values, dtype=float)) for meta, values in groups if len(values)]
    positions = np.arange(1, len(usable) + 1)
    if not usable:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center", va="center")
        return
    bp = ax.boxplot(
        [values for _, values in usable],
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
            pos + jitter(len(values)),
            values,
            s=26,
            color=meta.color,
            edgecolor="white",
            linewidth=0.5,
            alpha=0.9,
            zorder=4,
        )
    ax.set_xticks(positions)
    ax.set_xticklabels(
        [f"{meta.label}\n(n={len(values)})" for meta, values in usable]
    )
    if log:
        ax.set_yscale("log")


def save_figure(fig: plt.Figure, name: str) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / name
    fig.savefig(path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return path


def footnote(fig: plt.Figure, text: str, *, y: float = 0.005) -> None:
    fig.text(0.995, y, text, ha="right", va="bottom", fontsize=7.0, color="#666666")
