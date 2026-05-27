#!/usr/bin/env python3
"""Toxicity robustness analyses for Scientific Reports reviewer response.

This script treats RoBERTa ToxiGen as a measurement instrument. All outputs use
"mean ToxiGen probability" language and report both equal-user and
activity-weighted estimates.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("ARROW_NUM_THREADS", "1")

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
NORMAL_COMMUNITIES = ["funny", "gaming", "gifs", "pics", "technology", "videos"]


@dataclass(frozen=True)
class Event:
    key: str
    label: str
    date: pd.Timestamp


EVENTS_CHRONO = [
    Event("fph", "FPH", pd.Timestamp("2015-06-10")),
    Event("pg", "Pizzagate", pd.Timestamp("2016-11-23")),
    Event("ga", "GreatAwakening", pd.Timestamp("2018-09-12")),
    Event("td", "The_Donald", pd.Timestamp("2020-06-29")),
]
EVENT_ORDER = {event.key: idx for idx, event in enumerate(EVENTS_CHRONO)}


def epoch_to_datetime(values: pd.Series) -> pd.Series:
    """Convert epoch seconds or milliseconds to naive pandas timestamps."""
    numeric = pd.to_numeric(values, errors="coerce")
    seconds = numeric.where(numeric <= 100_000_000_000, numeric / 1000.0)
    return pd.to_datetime(seconds, unit="s", errors="coerce")


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    """Return a finite weighted mean or NaN when no positive weights exist."""
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return np.nan
    return float(np.average(values.loc[mask], weights=weights.loc[mask]))


def clean_numeric(values: pd.Series | np.ndarray) -> np.ndarray:
    """Return finite numeric values as a one-dimensional array."""
    array = np.asarray(pd.Series(values), dtype=float)
    return array[np.isfinite(array)]


def lag1_autocorrelation(values: pd.Series | np.ndarray) -> float:
    """Estimate lag-1 autocorrelation for a paired-difference series."""
    array = clean_numeric(values)
    if len(array) < 3:
        return np.nan
    if np.nanstd(array) == 0:
        return np.nan
    return float(pd.Series(array).autocorr(lag=1))


def ar1_effective_n(n_obs: int, rho: float) -> float:
    """Approximate effective sample size under AR(1) autocorrelation."""
    if n_obs <= 0 or pd.isna(rho) or rho <= -1:
        return np.nan
    return float(n_obs * (1 - rho) / (1 + rho))


def moving_block_bootstrap_mean_ci(
    values: pd.Series | np.ndarray,
    block_length: int = 6,
    iterations: int = 5000,
    seed: int = 2025,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Return percentile CI for the mean using overlapping moving blocks."""
    array = clean_numeric(values)
    n_obs = len(array)
    if n_obs == 0:
        return np.nan, np.nan
    if n_obs == 1:
        return float(array[0]), float(array[0])

    block_length = max(1, min(block_length, n_obs))
    starts = np.arange(n_obs - block_length + 1)
    rng = np.random.default_rng(seed)
    boot_means = np.empty(iterations, dtype=float)
    for idx in range(iterations):
        sampled = []
        while len(sampled) < n_obs:
            start = int(rng.choice(starts))
            sampled.extend(array[start : start + block_length])
        boot_means[idx] = float(np.mean(sampled[:n_obs]))

    lower = float(np.quantile(boot_means, alpha / 2))
    upper = float(np.quantile(boot_means, 1 - alpha / 2))
    return lower, upper


def moving_block_bootstrap_ratio_ci(
    numerator: pd.Series | np.ndarray,
    denominator: pd.Series | np.ndarray,
    block_length: int = 6,
    iterations: int = 5000,
    seed: int = 2025,
    alpha: float = 0.05,
    paired: bool = False,
) -> tuple[float, float]:
    """Return percentile CI for a mean ratio using moving-block bootstrap."""
    num = clean_numeric(numerator)
    den = clean_numeric(denominator)
    if len(num) == 0 or len(den) == 0:
        return np.nan, np.nan
    if paired and len(num) != len(den):
        raise ValueError("Paired ratio bootstrap requires equal-length arrays")

    rng = np.random.default_rng(seed)
    ratio_samples = np.empty(iterations, dtype=float)

    def draw_series(array: np.ndarray) -> np.ndarray:
        n_obs = len(array)
        local_block = max(1, min(block_length, n_obs))
        starts = np.arange(n_obs - local_block + 1)
        sampled = []
        while len(sampled) < n_obs:
            start = int(rng.choice(starts))
            sampled.extend(array[start : start + local_block])
        return np.asarray(sampled[:n_obs], dtype=float)

    for idx in range(iterations):
        if paired:
            n_obs = len(num)
            local_block = max(1, min(block_length, n_obs))
            starts = np.arange(n_obs - local_block + 1)
            sampled_idx = []
            while len(sampled_idx) < n_obs:
                start = int(rng.choice(starts))
                sampled_idx.extend(range(start, start + local_block))
            sampled_idx = np.asarray(sampled_idx[:n_obs], dtype=int)
            sampled_num = num[sampled_idx]
            sampled_den = den[sampled_idx]
        else:
            sampled_num = draw_series(num)
            sampled_den = draw_series(den)
        den_mean = float(np.mean(sampled_den))
        ratio_samples[idx] = float(np.mean(sampled_num) / den_mean) if den_mean > 0 else np.nan

    ratio_samples = ratio_samples[np.isfinite(ratio_samples)]
    if len(ratio_samples) == 0:
        return np.nan, np.nan
    lower = float(np.quantile(ratio_samples, alpha / 2))
    upper = float(np.quantile(ratio_samples, 1 - alpha / 2))
    return lower, upper


def newey_west_mean_ci(
    values: pd.Series | np.ndarray,
    max_lag: int = 6,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Return HAC/Newey-West SE and normal-approximation CI for the mean."""
    array = clean_numeric(values)
    n_obs = len(array)
    if n_obs == 0:
        return np.nan, np.nan, np.nan
    mean = float(np.mean(array))
    if n_obs == 1:
        return 0.0, mean, mean

    residuals = array - mean
    max_lag = max(0, min(max_lag, n_obs - 1))
    gamma0 = float(np.dot(residuals, residuals) / n_obs)
    long_run_var = gamma0
    for lag in range(1, max_lag + 1):
        weight = 1 - lag / (max_lag + 1)
        gamma = float(np.dot(residuals[lag:], residuals[:-lag]) / n_obs)
        long_run_var += 2 * weight * gamma

    long_run_var = max(long_run_var, 0.0)
    se = float(np.sqrt(long_run_var / n_obs))
    z = 1.959963984540054
    return se, mean - z * se, mean + z * se


def latest_event_for_month(month_period: pd.Period) -> Event | None:
    """Return the latest ban event whose calendar month is active."""
    current = None
    for event in EVENTS_CHRONO:
        if month_period >= event.date.to_period("M"):
            current = event
    return current


def dynamic_monthly_user_type(first_seen: pd.Timestamp, month_period: pd.Period) -> str:
    """Classify a user-month as event-newcomer or existing.

    Event months are treated as post-event months, but exact first-seen timestamps
    still decide whether a user first appeared before or after the event date.
    """
    event = latest_event_for_month(month_period)
    if event is None or pd.isna(first_seen):
        return "existing"
    return "newcomer" if first_seen >= event.date else "existing"


def monday_week_start(timestamps: pd.Series) -> pd.Series:
    """Return Monday week starts for timestamp values."""
    normalized = timestamps.dt.normalize()
    return normalized - pd.to_timedelta(normalized.dt.weekday, unit="D")


def event_week_index(week_start: pd.Series, event_date: pd.Timestamp) -> pd.Series:
    """Return Monday-start week index relative to the event week."""
    event_week_start = event_date.normalize() - pd.Timedelta(days=event_date.weekday())
    return ((week_start - event_week_start).dt.days // 7).astype(int)


def find_user_month_metrics(results_root: Path, community: str) -> Path:
    filename = f"voat_{community}_user_month_metrics.parquet"
    candidates = [
        results_root / "voat" / community / filename,
        results_root / "basic" / "voat" / "results" / filename,
        REPO_ROOT / "results" / "voat" / community / filename,
        REPO_ROOT / "results" / "basic" / "voat" / "results" / filename,
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise FileNotFoundError(f"Missing user-month metrics for {community}: {candidates}")
    return path


def find_monthly_aggregates(results_root: Path, platform: str, community: str) -> Path:
    filename = f"{platform}_{community}_monthly_aggregates.csv"
    candidates = [
        results_root / platform / community / filename,
        REPO_ROOT / "results" / platform / community / filename,
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise FileNotFoundError(
            f"Missing monthly aggregates for {platform}/{community}: {candidates}"
        )
    return path


def load_platform_toxicity_monthly(
    results_root: Path,
    platform: str,
    community: str,
) -> pd.DataFrame:
    path = find_monthly_aggregates(results_root, platform, community)
    df = pd.read_csv(path, usecols=["month", "toxicity_mean"])
    df["community"] = community
    df["platform"] = platform
    df["month"] = df["month"].astype(str)
    df["month_period"] = pd.PeriodIndex(df["month"], freq="M")
    df["toxicity_mean"] = pd.to_numeric(df["toxicity_mean"], errors="coerce")
    return df.dropna(subset=["toxicity_mean"]).sort_values("month_period")


def load_raw_activity(data_dir: Path, community: str) -> pd.DataFrame:
    path = data_dir / f"voat_{community}_madoc.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing raw Voat parquet: {path}")
    df = pd.read_parquet(
        path,
        columns=["user_id", "publish_date", "interaction_type", "toxicity_toxigen"],
    )
    df["user_id"] = df["user_id"].astype(str)
    df["interaction_type"] = df["interaction_type"].astype(str).str.lower()
    df = df[df["interaction_type"].isin(["post", "comment"])].copy()
    df["timestamp"] = epoch_to_datetime(df["publish_date"])
    df["toxicity_toxigen"] = pd.to_numeric(df["toxicity_toxigen"], errors="coerce")
    df = df.dropna(subset=["user_id", "timestamp"])
    return df[["user_id", "timestamp", "toxicity_toxigen"]]


def first_seen_from_raw(raw: pd.DataFrame) -> pd.DataFrame:
    return (
        raw.groupby("user_id", as_index=False)["timestamp"]
        .min()
        .rename(columns={"timestamp": "first_seen_dt"})
    )


def build_monthly_user_rows(
    community: str,
    user_month_path: Path,
    first_seen: pd.DataFrame,
) -> pd.DataFrame:
    df = pd.read_parquet(user_month_path)
    df["user_id"] = df["user_id"].astype(str)
    df["mean_toxicity"] = pd.to_numeric(df["mean_toxicity"], errors="coerce")
    df["activity_count"] = pd.to_numeric(df["activity_count"], errors="coerce")
    df = df.merge(first_seen, on="user_id", how="left")
    df["month_period"] = pd.PeriodIndex(df["month"], freq="M")
    df["user_type"] = [
        dynamic_monthly_user_type(first_seen_dt, month_period)
        for first_seen_dt, month_period in zip(df["first_seen_dt"], df["month_period"])
    ]
    df["community"] = community
    return df[
        [
            "community",
            "user_id",
            "month",
            "month_period",
            "first_seen_dt",
            "user_type",
            "mean_toxicity",
            "activity_count",
        ]
    ].dropna(subset=["mean_toxicity"])


def aggregate_user_periods(
    df: pd.DataFrame,
    group_cols: list[str],
    value_col: str,
    weight_col: str,
) -> pd.DataFrame:
    rows = []
    for keys, group in df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_cols, keys))
        row.update(
            {
                "active_user_periods": int(group["user_id"].nunique()),
                "activity_count": float(group[weight_col].sum()),
                "mean_toxigen_probability_equal_user": float(group[value_col].mean()),
                "mean_toxigen_probability_activity_weighted": weighted_mean(
                    group[value_col], group[weight_col]
                ),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_with_all_user_type(
    df: pd.DataFrame,
    base_group_cols: list[str],
    value_col: str = "mean_toxicity",
    weight_col: str = "activity_count",
) -> pd.DataFrame:
    specific = df.copy()
    all_rows = df.copy()
    all_rows["user_type"] = "all"
    combined = pd.concat([specific, all_rows], ignore_index=True)
    return aggregate_user_periods(
        combined,
        base_group_cols + ["user_type"],
        value_col=value_col,
        weight_col=weight_col,
    )


def monthly_cohort_decomposition(monthly_users: pd.DataFrame) -> pd.DataFrame:
    by_community = summarize_with_all_user_type(monthly_users, ["community", "month"])
    pooled = summarize_with_all_user_type(monthly_users, ["month"])
    pooled.insert(0, "community", "global")
    out = pd.concat([by_community, pooled], ignore_index=True)
    out["period_type"] = "month"
    out = out.rename(columns={"user_type": "cohort"})
    return out[
        [
            "period_type",
            "community",
            "month",
            "cohort",
            "active_user_periods",
            "activity_count",
            "mean_toxigen_probability_equal_user",
            "mean_toxigen_probability_activity_weighted",
        ]
    ].sort_values(["community", "month", "cohort"])


def build_weekly_event_user_rows(
    community: str,
    raw: pd.DataFrame,
    first_seen: pd.DataFrame,
    window_weeks: int,
) -> pd.DataFrame:
    raw = raw.dropna(subset=["toxicity_toxigen"]).copy()
    first_seen_map = first_seen.set_index("user_id")["first_seen_dt"]
    rows = []
    for event in EVENTS_CHRONO:
        event_week_start = event.date.normalize() - pd.Timedelta(days=event.date.weekday())
        window_start = event_week_start - pd.Timedelta(weeks=window_weeks)
        window_end = event_week_start + pd.Timedelta(weeks=window_weeks + 1)
        window = raw[(raw["timestamp"] >= window_start) & (raw["timestamp"] < window_end)].copy()
        if window.empty:
            continue
        window["first_seen_dt"] = window["user_id"].map(first_seen_map)
        window["week_start"] = monday_week_start(window["timestamp"])
        window["week_index"] = event_week_index(window["week_start"], event.date)
        window["user_type"] = np.where(
            window["first_seen_dt"] >= event.date, "newcomer", "existing"
        )
        window["event_key"] = event.key
        window["event_label"] = event.label
        window["event_date"] = event.date.strftime("%Y-%m-%d")
        grouped = (
            window.groupby(
                [
                    "event_key",
                    "event_label",
                    "event_date",
                    "week_start",
                    "week_index",
                    "user_id",
                    "user_type",
                ],
                as_index=False,
            )
            .agg(
                mean_toxicity=("toxicity_toxigen", "mean"),
                activity_count=("toxicity_toxigen", "count"),
            )
        )
        grouped["community"] = community
        rows.append(grouped)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def build_weekly_event_activity_user_rows(
    community: str,
    raw: pd.DataFrame,
    first_seen: pd.DataFrame,
    window_weeks: int,
) -> pd.DataFrame:
    """Return user-week activity counts around each ban event."""
    first_seen_map = first_seen.set_index("user_id")["first_seen_dt"]
    rows = []
    for event in EVENTS_CHRONO:
        event_week_start = event.date.normalize() - pd.Timedelta(days=event.date.weekday())
        window_start = event_week_start - pd.Timedelta(weeks=window_weeks)
        window_end = event_week_start + pd.Timedelta(weeks=window_weeks + 1)
        window = raw[(raw["timestamp"] >= window_start) & (raw["timestamp"] < window_end)].copy()
        if window.empty:
            continue
        window["first_seen_dt"] = window["user_id"].map(first_seen_map)
        window["week_start"] = monday_week_start(window["timestamp"])
        window["week_index"] = event_week_index(window["week_start"], event.date)
        window["user_type"] = np.where(
            window["first_seen_dt"] >= event.date, "newcomer", "existing"
        )
        window["event_key"] = event.key
        window["event_label"] = event.label
        window["event_date"] = event.date.strftime("%Y-%m-%d")
        grouped = (
            window.groupby(
                [
                    "event_key",
                    "event_label",
                    "event_date",
                    "week_start",
                    "week_index",
                    "user_id",
                    "user_type",
                ],
                as_index=False,
            )
            .agg(activity_count=("user_id", "size"))
        )
        grouped["community"] = community
        rows.append(grouped)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def aggregate_activity_periods(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Aggregate user-period activity counts without toxicity-score filtering."""
    rows = []
    for keys, group in df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        activity = float(group["activity_count"].sum())
        active_users = int(group["user_id"].nunique())
        row = dict(zip(group_cols, keys))
        row.update(
            {
                "active_user_periods": active_users,
                "activity_count": activity,
                "mean_activity_per_active_user": (
                    activity / active_users if active_users > 0 else np.nan
                ),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_activity_with_all_user_type(
    df: pd.DataFrame,
    base_group_cols: list[str],
) -> pd.DataFrame:
    """Add existing/newcomer/all weekly activity summaries."""
    specific = df.copy()
    all_rows = df.copy()
    all_rows["user_type"] = "all"
    combined = pd.concat([specific, all_rows], ignore_index=True)
    return aggregate_activity_periods(combined, base_group_cols + ["user_type"])


def weekly_activity_window_summary(weekly_activity_users: pd.DataFrame) -> pd.DataFrame:
    base_cols = ["community", "event_key", "event_label", "event_date", "week_start", "week_index"]
    by_community = summarize_activity_with_all_user_type(weekly_activity_users, base_cols)
    pooled = summarize_activity_with_all_user_type(
        weekly_activity_users,
        ["event_key", "event_label", "event_date", "week_start", "week_index"],
    )
    pooled.insert(0, "community", "global")
    out = pd.concat([by_community, pooled], ignore_index=True)
    out = out.rename(columns={"user_type": "cohort"})
    out["period_type"] = "activity_event_week"
    out["week_start"] = pd.to_datetime(out["week_start"]).dt.strftime("%Y-%m-%d")
    return out[
        [
            "period_type",
            "community",
            "event_key",
            "event_label",
            "event_date",
            "week_start",
            "week_index",
            "cohort",
            "active_user_periods",
            "activity_count",
            "mean_activity_per_active_user",
        ]
    ].sort_values(["community", "event_key", "week_index", "cohort"])


def weekly_event_window_summary(weekly_users: pd.DataFrame) -> pd.DataFrame:
    base_cols = ["community", "event_key", "event_label", "event_date", "week_start", "week_index"]
    by_community = summarize_with_all_user_type(weekly_users, base_cols)
    pooled = summarize_with_all_user_type(
        weekly_users,
        ["event_key", "event_label", "event_date", "week_start", "week_index"],
    )
    pooled.insert(0, "community", "global")
    out = pd.concat([by_community, pooled], ignore_index=True)
    out = out.rename(columns={"user_type": "cohort"})
    out["period_type"] = "event_week"
    out["week_start"] = pd.to_datetime(out["week_start"]).dt.strftime("%Y-%m-%d")
    return out[
        [
            "period_type",
            "community",
            "event_key",
            "event_label",
            "event_date",
            "week_start",
            "week_index",
            "cohort",
            "active_user_periods",
            "activity_count",
            "mean_toxigen_probability_equal_user",
            "mean_toxigen_probability_activity_weighted",
        ]
    ].sort_values(["community", "event_key", "week_index", "cohort"])


def weighting_comparison_summary(monthly_summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (community, cohort), group in monthly_summary.groupby(["community", "cohort"]):
        equal = group["mean_toxigen_probability_equal_user"]
        weighted = group["mean_toxigen_probability_activity_weighted"]
        diff = weighted - equal
        valid = equal.notna() & weighted.notna()
        rows.append(
            {
                "community": community,
                "cohort": cohort,
                "n_months": int(valid.sum()),
                "mean_equal_user_probability": (
                    float(equal[valid].mean()) if valid.any() else np.nan
                ),
                "mean_activity_weighted_probability": (
                    float(weighted[valid].mean()) if valid.any() else np.nan
                ),
                "mean_activity_minus_equal": float(diff[valid].mean()) if valid.any() else np.nan,
                "median_abs_difference": (
                    float(diff[valid].abs().median()) if valid.any() else np.nan
                ),
                "max_abs_difference": float(diff[valid].abs().max()) if valid.any() else np.nan,
                "activity_weighted_higher_share": (
                    float((diff[valid] > 0).mean()) if valid.any() else np.nan
                ),
                "pearson_correlation": (
                    float(equal[valid].corr(weighted[valid])) if valid.sum() >= 2 else np.nan
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["community", "cohort"])


def paired_interval_row(
    comparison: str,
    community: str,
    series_label: str,
    values: pd.Series | np.ndarray,
    block_length: int,
    bootstrap_iterations: int,
    hac_lags: int,
    seed: int,
) -> dict[str, float | int | str]:
    """Summarize one monthly paired-difference series with robust intervals."""
    array = clean_numeric(values)
    n_obs = len(array)
    mean = float(np.mean(array)) if n_obs else np.nan
    median = float(np.median(array)) if n_obs else np.nan
    sd = float(np.std(array, ddof=1)) if n_obs > 1 else np.nan
    rho = lag1_autocorrelation(array)
    mbb_low, mbb_high = moving_block_bootstrap_mean_ci(
        array,
        block_length=block_length,
        iterations=bootstrap_iterations,
        seed=seed,
    )
    hac_se, hac_low, hac_high = newey_west_mean_ci(array, max_lag=hac_lags)
    return {
        "comparison": comparison,
        "community": community,
        "series": series_label,
        "n_months": n_obs,
        "mean_difference": mean,
        "median_difference": median,
        "sd_difference": sd,
        "lag1_autocorrelation": rho,
        "effective_n_ar1": ar1_effective_n(n_obs, rho),
        "block_length": block_length,
        "bootstrap_iterations": bootstrap_iterations,
        "mbb_mean_ci_low": mbb_low,
        "mbb_mean_ci_high": mbb_high,
        "hac_lags": hac_lags,
        "hac_se": hac_se,
        "hac_mean_ci_low": hac_low,
        "hac_mean_ci_high": hac_high,
    }


def monthly_paired_interval_summary(
    monthly_summary: pd.DataFrame,
    block_length: int,
    bootstrap_iterations: int,
    hac_lags: int,
    seed: int,
) -> pd.DataFrame:
    """Create autocorrelation-aware intervals for monthly paired differences."""
    rows = []
    ordered = monthly_summary.sort_values(["community", "cohort", "month"])

    for (community, cohort), group in ordered.groupby(["community", "cohort"]):
        diff = (
            group["mean_toxigen_probability_activity_weighted"]
            - group["mean_toxigen_probability_equal_user"]
        )
        rows.append(
            paired_interval_row(
                comparison="activity_weighted_minus_equal_user",
                community=community,
                series_label=cohort,
                values=diff,
                block_length=block_length,
                bootstrap_iterations=bootstrap_iterations,
                hac_lags=hac_lags,
                seed=seed,
            )
        )

    for community, group in ordered.groupby("community"):
        for column, label in [
            ("mean_toxigen_probability_equal_user", "equal_user"),
            ("mean_toxigen_probability_activity_weighted", "activity_weighted"),
        ]:
            wide = group.pivot_table(index="month", columns="cohort", values=column)
            if {"newcomer", "existing"}.issubset(wide.columns):
                diff = wide["newcomer"] - wide["existing"]
                rows.append(
                    paired_interval_row(
                        comparison="newcomer_minus_existing",
                        community=community,
                        series_label=label,
                        values=diff,
                        block_length=block_length,
                        bootstrap_iterations=bootstrap_iterations,
                        hac_lags=hac_lags,
                        seed=seed,
                    )
                )

    return pd.DataFrame(rows).sort_values(["comparison", "community", "series"])


def cross_platform_ratio_uncertainty(
    results_root: Path,
    communities: list[str],
    block_length: int,
    bootstrap_iterations: int,
    hac_lags: int,
    seed: int,
) -> pd.DataFrame:
    """Estimate uncertainty for Voat/Reddit monthly mean toxicity ratios."""
    rows = []
    for community_index, community in enumerate(communities):
        voat = load_platform_toxicity_monthly(results_root, "voat", community)
        reddit = load_platform_toxicity_monthly(results_root, "reddit", community)
        voat_values = voat["toxicity_mean"]
        reddit_values = reddit["toxicity_mean"]
        voat_mean = float(voat_values.mean())
        reddit_mean = float(reddit_values.mean())
        all_low, all_high = moving_block_bootstrap_ratio_ci(
            voat_values,
            reddit_values,
            block_length=block_length,
            iterations=bootstrap_iterations,
            seed=seed + community_index,
            paired=False,
        )
        rows.append(
            {
                "community": community,
                "comparison_scope": "all_available_months",
                "n_voat_months": int(voat_values.notna().sum()),
                "n_reddit_months": int(reddit_values.notna().sum()),
                "n_paired_months": np.nan,
                "voat_mean_toxigen_probability": voat_mean,
                "reddit_mean_toxigen_probability": reddit_mean,
                "toxicity_ratio_voat_over_reddit": voat_mean / reddit_mean,
                "geometric_mean_monthly_ratio": np.nan,
                "lag1_log_ratio_autocorrelation": np.nan,
                "block_length": block_length,
                "bootstrap_iterations": bootstrap_iterations,
                "mbb_ratio_ci_low": all_low,
                "mbb_ratio_ci_high": all_high,
                "hac_lags": hac_lags,
                "hac_log_ratio_se": np.nan,
                "hac_geometric_ratio_ci_low": np.nan,
                "hac_geometric_ratio_ci_high": np.nan,
            }
        )

        paired = voat[["month", "toxicity_mean"]].merge(
            reddit[["month", "toxicity_mean"]],
            on="month",
            how="inner",
            suffixes=("_voat", "_reddit"),
        )
        paired = paired[
            (paired["toxicity_mean_voat"] > 0) & (paired["toxicity_mean_reddit"] > 0)
        ].copy()
        log_ratio = np.log(paired["toxicity_mean_voat"] / paired["toxicity_mean_reddit"])
        paired_low, paired_high = moving_block_bootstrap_ratio_ci(
            paired["toxicity_mean_voat"],
            paired["toxicity_mean_reddit"],
            block_length=block_length,
            iterations=bootstrap_iterations,
            seed=seed + 1000 + community_index,
            paired=True,
        )
        hac_se, hac_low, hac_high = newey_west_mean_ci(log_ratio, max_lag=hac_lags)
        rows.append(
            {
                "community": community,
                "comparison_scope": "overlapping_months_paired",
                "n_voat_months": int(paired["toxicity_mean_voat"].notna().sum()),
                "n_reddit_months": int(paired["toxicity_mean_reddit"].notna().sum()),
                "n_paired_months": int(len(paired)),
                "voat_mean_toxigen_probability": float(paired["toxicity_mean_voat"].mean()),
                "reddit_mean_toxigen_probability": float(
                    paired["toxicity_mean_reddit"].mean()
                ),
                "toxicity_ratio_voat_over_reddit": float(
                    paired["toxicity_mean_voat"].mean()
                    / paired["toxicity_mean_reddit"].mean()
                ),
                "geometric_mean_monthly_ratio": float(np.exp(log_ratio.mean())),
                "lag1_log_ratio_autocorrelation": lag1_autocorrelation(log_ratio),
                "block_length": block_length,
                "bootstrap_iterations": bootstrap_iterations,
                "mbb_ratio_ci_low": paired_low,
                "mbb_ratio_ci_high": paired_high,
                "hac_lags": hac_lags,
                "hac_log_ratio_se": hac_se,
                "hac_geometric_ratio_ci_low": float(np.exp(hac_low)),
                "hac_geometric_ratio_ci_high": float(np.exp(hac_high)),
            }
        )
    return pd.DataFrame(rows).sort_values(["community", "comparison_scope"])


def ratio(numerator: float, denominator: float) -> float:
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return np.nan
    return float(numerator / denominator)


def weekly_activity_spike_summary(weekly_activity_summary: pd.DataFrame) -> pd.DataFrame:
    """Summarize short-window activity spikes before versus after ban weeks."""
    rows = []
    group_cols = ["community", "event_key", "event_label", "event_date", "cohort"]
    for keys, group in weekly_activity_summary.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        pre = group[group["week_index"] < 0]
        post = group[group["week_index"] >= 0]
        event_week = group[group["week_index"] == 0]

        def avg(frame: pd.DataFrame, column: str) -> float:
            return float(frame[column].mean()) if not frame.empty else np.nan

        def first_or_nan(frame: pd.DataFrame, column: str) -> float:
            return float(frame[column].iloc[0]) if not frame.empty else np.nan

        pre_activity = avg(pre, "activity_count")
        post_activity = avg(post, "activity_count")
        event_activity = first_or_nan(event_week, "activity_count")
        max_post_idx = post["activity_count"].idxmax() if not post.empty else None
        max_post_activity = (
            float(post.loc[max_post_idx, "activity_count"]) if max_post_idx is not None else np.nan
        )
        max_post_week = (
            int(post.loc[max_post_idx, "week_index"]) if max_post_idx is not None else np.nan
        )

        pre_users = avg(pre, "active_user_periods")
        post_users = avg(post, "active_user_periods")
        event_users = first_or_nan(event_week, "active_user_periods")

        row = dict(zip(group_cols, keys))
        row.update(
            {
                "pre_weeks_observed": int(pre["week_index"].nunique()),
                "post_weeks_observed": int(post["week_index"].nunique()),
                "pre_mean_weekly_activity_count": pre_activity,
                "event_week_activity_count": event_activity,
                "post_mean_weekly_activity_count": post_activity,
                "post_minus_pre_mean_weekly_activity_count": post_activity - pre_activity,
                "post_pre_activity_ratio": ratio(post_activity, pre_activity),
                "event_pre_activity_ratio": ratio(event_activity, pre_activity),
                "max_post_week_index": max_post_week,
                "max_post_week_activity_count": max_post_activity,
                "max_post_pre_activity_ratio": ratio(max_post_activity, pre_activity),
                "pre_mean_weekly_active_users": pre_users,
                "event_week_active_users": event_users,
                "post_mean_weekly_active_users": post_users,
                "post_minus_pre_mean_weekly_active_users": post_users - pre_users,
                "post_pre_active_user_ratio": ratio(post_users, pre_users),
                "event_pre_active_user_ratio": ratio(event_users, pre_users),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["community", "event_key", "cohort"])


def weekly_prepost_change_summary(weekly_summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    group_cols = ["community", "event_key", "event_label", "event_date", "cohort"]
    for keys, group in weekly_summary.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        pre = group[group["week_index"] < 0]
        post = group[group["week_index"] >= 0]

        def avg(frame: pd.DataFrame, column: str) -> float:
            return float(frame[column].mean()) if not frame.empty else np.nan

        pre_equal = avg(pre, "mean_toxigen_probability_equal_user")
        post_equal = avg(post, "mean_toxigen_probability_equal_user")
        pre_weighted = avg(pre, "mean_toxigen_probability_activity_weighted")
        post_weighted = avg(post, "mean_toxigen_probability_activity_weighted")
        row = dict(zip(group_cols, keys))
        row.update(
            {
                "pre_weeks_observed": int(pre["week_index"].nunique()),
                "post_weeks_observed": int(post["week_index"].nunique()),
                "pre_equal_user_probability": pre_equal,
                "post_equal_user_probability": post_equal,
                "post_minus_pre_equal_user": post_equal - pre_equal,
                "pre_activity_weighted_probability": pre_weighted,
                "post_activity_weighted_probability": post_weighted,
                "post_minus_pre_activity_weighted": post_weighted - pre_weighted,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["community", "event_key", "cohort"])


def plot_monthly_global(monthly_summary: pd.DataFrame, output_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        LOGGER.warning("matplotlib unavailable; skipping %s", output_path)
        return

    df = monthly_summary[
        (monthly_summary["community"] == "global")
        & (monthly_summary["cohort"].isin(["all", "existing", "newcomer"]))
    ].copy()
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    cols = [
        ("mean_toxigen_probability_equal_user", "Equal-user mean"),
        ("mean_toxigen_probability_activity_weighted", "Activity-weighted mean"),
    ]
    colors = {"all": "#111111", "existing": "#2c7fb8", "newcomer": "#d95f0e"}
    for ax, (column, title) in zip(axes, cols):
        for cohort in ["all", "existing", "newcomer"]:
            subset = df[df["cohort"] == cohort]
            ax.plot(
                subset["month_dt"],
                subset[column],
                label=cohort,
                linewidth=1.6,
                color=colors[cohort],
            )
        for event in EVENTS_CHRONO:
            ax.axvline(event.date, color="0.55", linestyle=":", linewidth=1)
        ax.set_title(title)
        ax.set_ylabel("Mean ToxiGen probability")
        ax.grid(alpha=0.25)
    axes[-1].set_xlabel("Month")
    axes[0].legend(ncol=3, frameon=False)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_weekly_global(weekly_summary: pd.DataFrame, output_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        LOGGER.warning("matplotlib unavailable; skipping %s", output_path)
        return

    df = weekly_summary[
        (weekly_summary["community"] == "global")
        & (weekly_summary["cohort"].isin(["all", "existing", "newcomer"]))
    ].copy()
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
    colors = {"all": "#111111", "existing": "#2c7fb8", "newcomer": "#d95f0e"}
    for ax, event in zip(axes.ravel(), EVENTS_CHRONO):
        event_df = df[df["event_key"] == event.key]
        for cohort in ["all", "existing", "newcomer"]:
            subset = event_df[event_df["cohort"] == cohort]
            if subset.empty:
                continue
            ax.plot(
                subset["week_index"],
                subset["mean_toxigen_probability_equal_user"],
                marker="o",
                markersize=3,
                linewidth=1.4,
                label=cohort,
                color=colors[cohort],
            )
        ax.axvline(0, color="0.45", linestyle=":", linewidth=1)
        ax.set_title(f"{event.label} ({event.date.date()})")
        ax.grid(alpha=0.25)
    for ax in axes[:, 0]:
        ax.set_ylabel("Mean ToxiGen probability")
    for ax in axes[-1, :]:
        ax.set_xlabel("Event-relative week")
    axes[0, 0].legend(frameon=False)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def format_float(value: float) -> str:
    if pd.isna(value):
        return "NA"
    return f"{value:.4f}"


def write_review_note(
    output_path: Path,
    monthly_summary: pd.DataFrame,
    weighting_summary: pd.DataFrame,
    interval_summary: pd.DataFrame,
    cross_platform_ratio_summary: pd.DataFrame,
    prepost_summary: pd.DataFrame,
    activity_spike_summary: pd.DataFrame,
    results_dir: Path,
    figures_dir: Path,
) -> None:
    global_weighting = weighting_summary[
        (weighting_summary["community"] == "global") & (weighting_summary["cohort"] == "all")
    ].iloc[0]

    monthly_global = monthly_summary[monthly_summary["community"] == "global"].copy()
    monthly_wide = monthly_global.pivot_table(
        index="month",
        columns="cohort",
        values="mean_toxigen_probability_equal_user",
    )
    monthly_delta = monthly_wide["newcomer"] - monthly_wide["existing"]
    monthly_delta = monthly_delta.dropna()
    global_activity_interval = interval_summary[
        (interval_summary["comparison"] == "activity_weighted_minus_equal_user")
        & (interval_summary["community"] == "global")
        & (interval_summary["series"] == "all")
    ].iloc[0]
    global_newcomer_interval = interval_summary[
        (interval_summary["comparison"] == "newcomer_minus_existing")
        & (interval_summary["community"] == "global")
        & (interval_summary["series"] == "equal_user")
    ].iloc[0]
    all_month_ratios = cross_platform_ratio_summary[
        cross_platform_ratio_summary["comparison_scope"] == "all_available_months"
    ].copy()
    above_one = int((all_month_ratios["mbb_ratio_ci_low"] > 1.0).sum())
    total_ratio_rows = int(len(all_month_ratios))

    prepost_global = prepost_summary[
        (prepost_summary["community"] == "global") & (prepost_summary["cohort"] == "all")
    ].copy()
    prepost_global["event_order"] = prepost_global["event_key"].map(EVENT_ORDER)
    activity_spike_global = activity_spike_summary[
        (activity_spike_summary["community"] == "global")
        & (activity_spike_summary["cohort"] == "all")
    ].copy()
    activity_spike_global["event_order"] = activity_spike_global["event_key"].map(EVENT_ORDER)

    def display_path(path: Path) -> str:
        try:
            return str(path.relative_to(REPO_ROOT))
        except ValueError:
            return str(path)

    lines = [
        "# Toxicity Robustness Reviewer-Response Note",
        "",
        "Measurement model:",
        "- Latent construct: toxic, hateful, abusive, or demeaning discourse.",
        "- Observed input: Voat posts and comments with timestamps and user IDs.",
        "- Instrument output: RoBERTa ToxiGen probability in [0, 1].",
        (
            "- Noise/error: domain shift, coded Voat-specific language, "
            "calibration drift, and user/post aggregation choices."
        ),
        (
            "- Downstream estimand: longitudinal changes in mean ToxiGen "
            "probabilities, not manually observed toxicity prevalence."
        ),
        "",
        "Evidence files:",
        f"- `{display_path(results_dir / 'toxicity_cohort_decomposition_summary.csv')}`",
        f"- `{display_path(results_dir / 'toxicity_weighting_comparison_summary.csv')}`",
        f"- `{display_path(results_dir / 'toxicity_monthly_paired_interval_summary.csv')}`",
        f"- `{display_path(results_dir / 'toxicity_cross_platform_ratio_uncertainty.csv')}`",
        f"- `{display_path(results_dir / 'toxicity_weekly_event_window_summary.csv')}`",
        f"- `{display_path(results_dir / 'toxicity_weekly_prepost_change_summary.csv')}`",
        f"- `{display_path(results_dir / 'toxicity_weekly_activity_spike_summary.csv')}`",
        f"- `{display_path(figures_dir / 'toxicity_cohort_decomposition_global.png')}`",
        f"- `{display_path(figures_dir / 'toxicity_weekly_event_window_global.png')}`",
        "",
        "Key descriptive results:",
        (
            "- Equal-user and activity-weighted global monthly estimates are highly aligned "
            f"(Pearson r={format_float(global_weighting['pearson_correlation'])}; "
            f"mean activity-minus-equal difference="
            f"{format_float(global_weighting['mean_activity_minus_equal'])})."
        ),
        (
            "- Across global months where both groups are observed, newcomer minus existing "
            f"equal-user mean ToxiGen probability averages {format_float(monthly_delta.mean())} "
            f"(median {format_float(monthly_delta.median())})."
        ),
        (
            "- Autocorrelation-aware intervals for the global monthly paired differences "
            "support the same descriptive interpretation: activity-weighted minus "
            f"equal-user mean={format_float(global_activity_interval['mean_difference'])}, "
            f"MBB 95% CI [{format_float(global_activity_interval['mbb_mean_ci_low'])}, "
            f"{format_float(global_activity_interval['mbb_mean_ci_high'])}], "
            f"HAC 95% CI [{format_float(global_activity_interval['hac_mean_ci_low'])}, "
            f"{format_float(global_activity_interval['hac_mean_ci_high'])}]; "
            "newcomer minus existing equal-user "
            f"mean={format_float(global_newcomer_interval['mean_difference'])}, "
            f"MBB 95% CI [{format_float(global_newcomer_interval['mbb_mean_ci_low'])}, "
            f"{format_float(global_newcomer_interval['mbb_mean_ci_high'])}], "
            f"HAC 95% CI [{format_float(global_newcomer_interval['hac_mean_ci_low'])}, "
            f"{format_float(global_newcomer_interval['hac_mean_ci_high'])}]."
        ),
        (
            "- Cross-platform Voat/Reddit mean ToxiGen probability ratios remain "
            "descriptive rather than causal. Moving-block bootstrap intervals for "
            "all available months place "
            f"{above_one}/{total_ratio_rows} community ratios above 1.0; "
            "technology is the exception where the interval includes 1.0."
        ),
        "- Weekly global all-user post-minus-pre changes by event:",
    ]
    for _, row in prepost_global.sort_values("event_order").iterrows():
        lines.append(
            "  - "
            f"{row['event_label']}: equal-user {format_float(row['post_minus_pre_equal_user'])}; "
            f"activity-weighted {format_float(row['post_minus_pre_activity_weighted'])}."
        )
    lines.append("- Weekly global all-user activity-volume changes by event:")
    for _, row in activity_spike_global.sort_values("event_order").iterrows():
        lines.append(
            "  - "
            f"{row['event_label']}: post/pre activity ratio "
            f"{format_float(row['post_pre_activity_ratio'])}; "
            f"event-week/pre activity ratio {format_float(row['event_pre_activity_ratio'])}; "
            f"max post-week/pre activity ratio {format_float(row['max_post_pre_activity_ratio'])}."
        )
    lines.extend(
        [
            "",
            "Reviewer-response framing:",
            (
                "- R1-M3: report both equal-user and activity-weighted mean "
                "ToxiGen probabilities and state whether the two estimands align."
            ),
            (
                "- R1-M7: replace `toxicity doubled` with `mean ToxiGen "
                "classifier probability approximately doubled`."
            ),
            (
                "- R2-5 / PDF M7: cite Hartvigsen et al. (2022) for ToxiGen "
                "validation and explicitly acknowledge platform/domain-shift "
                "limits; no manual validation sample was added."
            ),
            (
                "- R1-S1/R2-6: report uncertainty for cross-platform toxicity "
                "ratios and state that Reddit is a descriptive reference series, "
                "not a causal baseline."
            ),
            (
                "- R2-7.1: use the monthly newcomer-vs-existing decomposition "
                "as the cohort toxicity evidence."
            ),
            (
                "- R2-7.2: use the weekly event-window table/figure as the "
                "short-term post-ban evidence."
            ),
            (
                "- R2-4: use the weekly activity-spike table to answer whether "
                "there were immediate post-ban volume spikes around each event."
            ),
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--communities", nargs="+", default=NORMAL_COMMUNITIES)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--results-root", type=Path, default=REPO_ROOT / "results")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "results" / "basic" / "compare" / "results",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=REPO_ROOT / "results" / "basic" / "compare" / "figures",
    )
    parser.add_argument("--window-weeks", type=int, default=8)
    parser.add_argument("--interval-block-length", type=int, default=6)
    parser.add_argument("--interval-bootstrap-iterations", type=int, default=5000)
    parser.add_argument("--interval-hac-lags", type=int, default=6)
    parser.add_argument("--interval-seed", type=int, default=2025)
    parser.add_argument("--skip-figures", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.figures_dir.mkdir(parents=True, exist_ok=True)

    monthly_rows = []
    weekly_rows = []
    weekly_activity_rows = []
    for community in args.communities:
        LOGGER.info("Processing %s", community)
        raw = load_raw_activity(args.data_dir, community)
        first_seen = first_seen_from_raw(raw)
        user_month_path = find_user_month_metrics(args.results_root, community)
        monthly_rows.append(build_monthly_user_rows(community, user_month_path, first_seen))
        weekly_rows.append(
            build_weekly_event_user_rows(
                community=community,
                raw=raw,
                first_seen=first_seen,
                window_weeks=args.window_weeks,
            )
        )
        weekly_activity_rows.append(
            build_weekly_event_activity_user_rows(
                community=community,
                raw=raw,
                first_seen=first_seen,
                window_weeks=args.window_weeks,
            )
        )
        LOGGER.info(
            "%s: %s raw rows, %s first-seen users",
            community,
            f"{len(raw):,}",
            f"{len(first_seen):,}",
        )

    monthly_users = pd.concat(monthly_rows, ignore_index=True)
    weekly_users = pd.concat([df for df in weekly_rows if not df.empty], ignore_index=True)
    weekly_activity_users = pd.concat(
        [df for df in weekly_activity_rows if not df.empty],
        ignore_index=True,
    )

    monthly_summary = monthly_cohort_decomposition(monthly_users)
    weekly_summary = weekly_event_window_summary(weekly_users)
    weekly_activity_summary = weekly_activity_window_summary(weekly_activity_users)
    weighting_summary = weighting_comparison_summary(monthly_summary)
    interval_summary = monthly_paired_interval_summary(
        monthly_summary=monthly_summary,
        block_length=args.interval_block_length,
        bootstrap_iterations=args.interval_bootstrap_iterations,
        hac_lags=args.interval_hac_lags,
        seed=args.interval_seed,
    )
    cross_platform_ratio_summary = cross_platform_ratio_uncertainty(
        results_root=args.results_root,
        communities=args.communities,
        block_length=args.interval_block_length,
        bootstrap_iterations=args.interval_bootstrap_iterations,
        hac_lags=args.interval_hac_lags,
        seed=args.interval_seed,
    )
    prepost_summary = weekly_prepost_change_summary(weekly_summary)
    activity_spike_summary = weekly_activity_spike_summary(weekly_activity_summary)

    monthly_path = args.output_dir / "toxicity_cohort_decomposition_summary.csv"
    weighting_path = args.output_dir / "toxicity_weighting_comparison_summary.csv"
    interval_path = args.output_dir / "toxicity_monthly_paired_interval_summary.csv"
    cross_platform_ratio_path = (
        args.output_dir / "toxicity_cross_platform_ratio_uncertainty.csv"
    )
    weekly_path = args.output_dir / "toxicity_weekly_event_window_summary.csv"
    prepost_path = args.output_dir / "toxicity_weekly_prepost_change_summary.csv"
    activity_spike_path = args.output_dir / "toxicity_weekly_activity_spike_summary.csv"
    note_path = args.output_dir / "toxicity_review_response.md"

    monthly_summary.to_csv(monthly_path, index=False)
    weighting_summary.to_csv(weighting_path, index=False)
    interval_summary.to_csv(interval_path, index=False)
    cross_platform_ratio_summary.to_csv(cross_platform_ratio_path, index=False)
    weekly_summary.to_csv(weekly_path, index=False)
    prepost_summary.to_csv(prepost_path, index=False)
    activity_spike_summary.to_csv(activity_spike_path, index=False)

    if not args.skip_figures:
        plot_monthly_global(
            monthly_summary,
            args.figures_dir / "toxicity_cohort_decomposition_global.png",
        )
        plot_weekly_global(
            weekly_summary,
            args.figures_dir / "toxicity_weekly_event_window_global.png",
        )

    write_review_note(
        output_path=note_path,
        monthly_summary=monthly_summary,
        weighting_summary=weighting_summary,
        interval_summary=interval_summary,
        cross_platform_ratio_summary=cross_platform_ratio_summary,
        prepost_summary=prepost_summary,
        activity_spike_summary=activity_spike_summary,
        results_dir=args.output_dir,
        figures_dir=args.figures_dir,
    )
    LOGGER.info("Wrote toxicity robustness outputs under %s", args.output_dir)


if __name__ == "__main__":
    main()
