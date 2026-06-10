#!/usr/bin/env python3
"""Cohort toxicity follow-up for the merged exploratory notebook.

Outputs:
- 30-day sliding time series with equal-user and activity-weighted means only.
- Simplified A-D+ cohort summaries, where A-D+ means FPH ban through dataset end.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from scripts.migration_utils import EVENTS_CHRONO

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("ARROW_NUM_THREADS", "1")

LOGGER = logging.getLogger(__name__)

NORMAL_COMMUNITIES = ["funny", "gaming", "pics", "videos", "gifs", "technology"]
COHORT_ORDER = ["beforeA", "betweenA-B", "betweenB-C", "betweenC-D", "afterD"]
COHORT_LABELS = {
    "beforeA": "Before A",
    "betweenA-B": "A-B",
    "betweenB-C": "B-C",
    "betweenC-D": "C-D",
    "afterD": "D+",
}
Z_95 = 1.96


def epoch_to_datetime(values: pd.Series) -> pd.Series:
    """Convert epoch seconds or milliseconds to pandas timestamps."""
    numeric = pd.to_numeric(values, errors="coerce")
    seconds = numeric.where(numeric <= 100_000_000_000, numeric / 1000.0)
    return pd.to_datetime(seconds, unit="s", errors="coerce")


def cohort_from_first_seen(first_seen: pd.Timestamp) -> str:
    """Assign chronological event-arrival cohort from first observed Voat activity."""
    if first_seen < EVENTS_CHRONO["A"]:
        return "beforeA"
    if first_seen < EVENTS_CHRONO["B"]:
        return "betweenA-B"
    if first_seen < EVENTS_CHRONO["C"]:
        return "betweenB-C"
    if first_seen < EVENTS_CHRONO["D"]:
        return "betweenC-D"
    return "afterD"


def assign_cohorts_from_first_seen(data: pd.DataFrame) -> pd.DataFrame:
    """Assign cohorts using each user's first observed activity in the provided data."""
    out = data.copy()
    first_seen = out.groupby("user_id")["dt_time"].min()
    out["cohort"] = out["user_id"].map(first_seen.map(cohort_from_first_seen))
    return out


def load_community_activity(data_dir: Path, platform: str, community: str) -> pd.DataFrame:
    """Load raw activity needed for cohort toxicity aggregation."""
    path = data_dir / f"{platform}_{community}_madoc.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing input parquet: {path}")

    df = pd.read_parquet(path, columns=["user_id", "publish_date", "toxicity_toxigen"])
    df["user_id"] = df["user_id"].astype(str)
    df["dt_time"] = epoch_to_datetime(df["publish_date"]).dt.normalize()
    df = df.dropna(subset=["user_id", "dt_time"]).copy()

    df = assign_cohorts_from_first_seen(df)
    df["toxicity_toxigen"] = pd.to_numeric(df["toxicity_toxigen"], errors="coerce")
    df = df.dropna(subset=["toxicity_toxigen"]).copy()
    return df[["user_id", "dt_time", "cohort", "toxicity_toxigen"]]


def cohort_metrics(rows: pd.DataFrame) -> dict[str, float]:
    """Compute activity count, active users, equal-user mean, and activity mean."""
    if rows.empty:
        return {
            "active_users": 0,
            "activity_count": 0,
            "mean_toxigen_probability_user": np.nan,
            "mean_toxigen_probability_user_se": np.nan,
            "mean_toxigen_probability_user_ci95_low": np.nan,
            "mean_toxigen_probability_user_ci95_high": np.nan,
            "mean_toxigen_probability_activity": np.nan,
            "mean_toxigen_probability_activity_se": np.nan,
            "mean_toxigen_probability_activity_ci95_low": np.nan,
            "mean_toxigen_probability_activity_ci95_high": np.nan,
        }

    user_stats = rows.groupby("user_id")["toxicity_toxigen"].agg(["mean", "count"])
    user_means = user_stats["mean"]
    activity_weights = user_stats["count"]
    user_mean = float(user_means.mean())
    user_n = int(user_means.shape[0])
    user_se = float(user_means.std(ddof=1) / np.sqrt(user_n)) if user_n > 1 else np.nan

    activity_mean = float(np.average(user_means, weights=activity_weights))
    activity_n = int(activity_weights.sum())
    activity_weighted_var = np.average(
        (user_means - activity_mean) ** 2,
        weights=activity_weights,
    )
    activity_se = float(np.sqrt(activity_weighted_var / user_n)) if user_n > 1 else np.nan

    return {
        "active_users": user_n,
        "activity_count": activity_n,
        "mean_toxigen_probability_user": user_mean,
        "mean_toxigen_probability_user_se": user_se,
        "mean_toxigen_probability_user_ci95_low": user_mean - Z_95 * user_se,
        "mean_toxigen_probability_user_ci95_high": user_mean + Z_95 * user_se,
        "mean_toxigen_probability_activity": activity_mean,
        "mean_toxigen_probability_activity_se": activity_se,
        "mean_toxigen_probability_activity_ci95_low": activity_mean - Z_95 * activity_se,
        "mean_toxigen_probability_activity_ci95_high": activity_mean + Z_95 * activity_se,
    }


def calculate_sliding_timeseries(
    data: pd.DataFrame,
    community: str,
    platform: str = "voat",
    window_days: int = 30,
    step_days: int = 1,
) -> pd.DataFrame:
    """Calculate sliding-window cohort toxicity time series."""
    if data.empty:
        return pd.DataFrame()

    t_min = data["dt_time"].min()
    t_max = data["dt_time"].max()
    last_start = t_max - pd.Timedelta(days=window_days - 1)

    rows = []
    step = 0
    window_tmin = t_min
    while window_tmin <= last_start:
        window_tmax = window_tmin + pd.Timedelta(days=window_days)
        window = data[(data["dt_time"] >= window_tmin) & (data["dt_time"] < window_tmax)]
        for cohort in COHORT_ORDER:
            metrics = cohort_metrics(window[window["cohort"] == cohort])
            rows.append(
                {
                    "platform": platform,
                    "community": community,
                    "step": step,
                    "window_tmin": window_tmin.date().isoformat(),
                    "window_tmax": window_tmax.date().isoformat(),
                    "window_days": window_days,
                    "cohort": cohort,
                    "cohort_label": COHORT_LABELS[cohort],
                    **metrics,
                }
            )
        step += step_days
        window_tmin += pd.Timedelta(days=step_days)

    return pd.DataFrame(rows)


def summarize_adplus_period(
    data: pd.DataFrame,
    community: str,
    platform: str = "voat",
) -> pd.DataFrame:
    """Summarize cohort means over A-D+, defined as FPH ban through dataset end."""
    period_start = EVENTS_CHRONO["A"]
    period = data[data["dt_time"] >= period_start].copy()
    period_end = period["dt_time"].max() if not period.empty else pd.NaT

    rows = []
    for cohort in COHORT_ORDER:
        metrics = cohort_metrics(period[period["cohort"] == cohort])
        rows.append(
            {
                "platform": platform,
                "community": community,
                "period": "A-D+",
                "period_start": period_start.date().isoformat(),
                "period_end": period_end.date().isoformat() if pd.notna(period_end) else "",
                "cohort": cohort,
                "cohort_label": COHORT_LABELS[cohort],
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def plot_timeseries(
    timeseries: pd.DataFrame,
    output_path: Path,
    community: str,
    plot_step_days: int = 7,
    min_active_users_for_plot: int = 30,
    min_activity_count_for_plot: int = 30,
) -> None:
    """Plot equal-user and activity-weighted cohort time series."""
    import matplotlib.pyplot as plt

    if timeseries.empty:
        LOGGER.warning("No time-series rows for %s; skipping %s", community, output_path)
        return

    df = timeseries.copy()
    df["window_tmin"] = pd.to_datetime(df["window_tmin"])
    if plot_step_days > 1:
        df = df[df["step"] % plot_step_days == 0].copy()

    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    metrics = [
        (
            "mean_toxigen_probability_user",
            "mean_toxigen_probability_user_ci95_low",
            "mean_toxigen_probability_user_ci95_high",
            "active_users",
            min_active_users_for_plot,
            "Mean ToxiGen classifier probability, equal-user",
        ),
        (
            "mean_toxigen_probability_activity",
            "mean_toxigen_probability_activity_ci95_low",
            "mean_toxigen_probability_activity_ci95_high",
            "activity_count",
            min_activity_count_for_plot,
            "Mean ToxiGen classifier probability, activity",
        ),
    ]
    for ax, (metric, ci_low, ci_high, n_col, min_n, ylabel) in zip(axes, metrics):
        for cohort in COHORT_ORDER:
            cohort_df = df[(df["cohort"] == cohort) & (df[n_col] >= min_n)].copy()
            if cohort_df.empty:
                continue
            x = cohort_df["window_tmin"]
            y = cohort_df[metric].astype(float)
            low = cohort_df[ci_low].astype(float).clip(lower=0, upper=1)
            high = cohort_df[ci_high].astype(float).clip(lower=0, upper=1)
            line = ax.plot(x, y, label=COHORT_LABELS[cohort], linewidth=1.8)[0]
            ax.fill_between(
                x,
                low,
                high,
                color=line.get_color(),
                alpha=0.28,
                linewidth=0,
                zorder=line.get_zorder() - 1,
            )
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.18)

    for event_key, event_date in EVENTS_CHRONO.items():
        for ax in axes:
            ax.axvline(event_date, color="0.4", linestyle="--", linewidth=0.8, alpha=0.7)
        axes[0].text(event_date, axes[0].get_ylim()[1], event_key, va="top", ha="left")

    axes[0].legend(title="Cohort", ncol=3, fontsize=8, loc="upper left")
    axes[-1].set_xlabel("Window start")
    community_label = community.replace("_", " ")
    fig.suptitle(
        f"Voat {community_label}: 30-day cohort ToxiGen classifier-probability time series with cohort-size CIs"
    )
    fig.text(
        0.99,
        0.01,
        "Shaded bands: 95% CI from active users in each cohort-window",
        ha="right",
        va="bottom",
        fontsize=8,
        color="0.25",
    )
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_adplus_summary(summary: pd.DataFrame, output_path: Path, community: str) -> None:
    """Plot simplified A-D+ cohort barplot."""
    import matplotlib.pyplot as plt

    if summary.empty:
        LOGGER.warning("No A-D+ summary rows for %s; skipping %s", community, output_path)
        return

    df = summary.set_index("cohort").reindex(COHORT_ORDER).reset_index()
    x = np.arange(len(df))
    labels = [COHORT_LABELS[cohort] for cohort in df["cohort"]]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5))
    panels = [
        ("active_users", "Active users", True),
        ("mean_toxigen_probability_user", "Mean ToxiGen classifier probability, equal-user", False),
        ("mean_toxigen_probability_activity", "Mean ToxiGen classifier probability, activity", False),
    ]
    for ax, (metric, ylabel, log_scale) in zip(axes, panels):
        ax.bar(x, df[metric], color="#4C78A8")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right")
        ax.set_ylabel(ylabel)
        ax.grid(True, axis="y", alpha=0.25)
        if log_scale:
            ax.set_yscale("log")

    community_label = community.replace("_", " ")
    fig.suptitle(f"Voat {community_label}: cohort means over A-D+")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default="voat")
    parser.add_argument("--communities", nargs="+", default=NORMAL_COMMUNITIES)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "results" / "toxicity" / "voat" / "results",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=REPO_ROOT / "results" / "toxicity" / "voat" / "figures",
    )
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--step-days", type=int, default=1)
    parser.add_argument("--plot-step-days", type=int, default=7)
    parser.add_argument("--min-active-users-for-plot", type=int, default=30)
    parser.add_argument("--min-activity-count-for-plot", type=int, default=30)
    parser.add_argument("--skip-figures", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.figures_dir.mkdir(parents=True, exist_ok=True)

    all_timeseries = []
    all_summaries = []
    all_activity = []
    for community in args.communities:
        LOGGER.info("Processing %s/%s", args.platform, community)
        data = load_community_activity(args.data_dir, args.platform, community)
        all_activity.append(data)
        timeseries = calculate_sliding_timeseries(
            data,
            community=community,
            platform=args.platform,
            window_days=args.window_days,
            step_days=args.step_days,
        )
        summary = summarize_adplus_period(data, community=community, platform=args.platform)

        ts_path = args.output_dir / f"{args.platform}_{community}_toxicity_cohort_timeseries.csv"
        summary_path = args.output_dir / f"{args.platform}_{community}_toxicity_cohort_adplus_summary.csv"
        timeseries.to_csv(ts_path, index=False)
        summary.to_csv(summary_path, index=False)
        LOGGER.info("Wrote %s and %s", ts_path, summary_path)

        if not args.skip_figures:
            plot_timeseries(
                timeseries,
                args.figures_dir / f"{args.platform}_{community}_toxicity_cohort_timeseries.png",
                community,
                plot_step_days=args.plot_step_days,
                min_active_users_for_plot=args.min_active_users_for_plot,
                min_activity_count_for_plot=args.min_activity_count_for_plot,
            )
            plot_adplus_summary(
                summary,
                args.figures_dir / f"{args.platform}_{community}_toxicity_cohort_adplus_barplot.png",
                community,
            )

        all_timeseries.append(timeseries)
        all_summaries.append(summary)

    combined_ts = pd.concat(all_timeseries, ignore_index=True)
    combined_summary = pd.concat(all_summaries, ignore_index=True)
    combined_ts_path = args.output_dir / f"{args.platform}_toxicity_cohort_timeseries_all_communities.csv"
    combined_summary_path = (
        args.output_dir / f"{args.platform}_toxicity_cohort_adplus_summary_all_communities.csv"
    )
    combined_ts.to_csv(combined_ts_path, index=False)
    combined_summary.to_csv(combined_summary_path, index=False)
    LOGGER.info("Wrote combined outputs: %s and %s", combined_ts_path, combined_summary_path)

    pooled_community = "all_examined_communities"
    pooled_data = assign_cohorts_from_first_seen(pd.concat(all_activity, ignore_index=True))
    pooled_timeseries = calculate_sliding_timeseries(
        pooled_data,
        community=pooled_community,
        platform=args.platform,
        window_days=args.window_days,
        step_days=args.step_days,
    )
    pooled_summary = summarize_adplus_period(
        pooled_data,
        community=pooled_community,
        platform=args.platform,
    )
    pooled_ts_path = (
        args.output_dir / f"{args.platform}_{pooled_community}_toxicity_cohort_timeseries.csv"
    )
    pooled_summary_path = (
        args.output_dir / f"{args.platform}_{pooled_community}_toxicity_cohort_adplus_summary.csv"
    )
    pooled_timeseries.to_csv(pooled_ts_path, index=False)
    pooled_summary.to_csv(pooled_summary_path, index=False)
    LOGGER.info("Wrote pooled outputs: %s and %s", pooled_ts_path, pooled_summary_path)

    if not args.skip_figures:
        plot_timeseries(
            pooled_timeseries,
            args.figures_dir / f"{args.platform}_{pooled_community}_toxicity_cohort_timeseries.png",
            pooled_community,
            plot_step_days=args.plot_step_days,
            min_active_users_for_plot=args.min_active_users_for_plot,
            min_activity_count_for_plot=args.min_activity_count_for_plot,
        )
        plot_timeseries(
            pooled_timeseries,
            args.figures_dir
            / f"{args.platform}_{pooled_community}_toxicity_cohort_timeseries_with_ci.png",
            pooled_community,
            plot_step_days=args.plot_step_days,
            min_active_users_for_plot=args.min_active_users_for_plot,
            min_activity_count_for_plot=args.min_activity_count_for_plot,
        )
        plot_adplus_summary(
            pooled_summary,
            args.figures_dir / f"{args.platform}_{pooled_community}_toxicity_cohort_adplus_barplot.png",
            pooled_community,
        )


if __name__ == "__main__":
    main()
