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
                "mean_equal_user_probability": float(equal[valid].mean()) if valid.any() else np.nan,
                "mean_activity_weighted_probability": (
                    float(weighted[valid].mean()) if valid.any() else np.nan
                ),
                "mean_activity_minus_equal": float(diff[valid].mean()) if valid.any() else np.nan,
                "median_abs_difference": float(diff[valid].abs().median()) if valid.any() else np.nan,
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
    prepost_summary: pd.DataFrame,
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

    prepost_global = prepost_summary[
        (prepost_summary["community"] == "global") & (prepost_summary["cohort"] == "all")
    ].copy()
    prepost_global["event_order"] = prepost_global["event_key"].map(EVENT_ORDER)

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
        "- Noise/error: domain shift, coded Voat-specific language, calibration drift, and user/post aggregation choices.",
        "- Downstream estimand: longitudinal changes in mean ToxiGen probabilities, not manually observed toxicity prevalence.",
        "",
        "Evidence files:",
        f"- `{display_path(results_dir / 'toxicity_cohort_decomposition_summary.csv')}`",
        f"- `{display_path(results_dir / 'toxicity_weighting_comparison_summary.csv')}`",
        f"- `{display_path(results_dir / 'toxicity_weekly_event_window_summary.csv')}`",
        f"- `{display_path(results_dir / 'toxicity_weekly_prepost_change_summary.csv')}`",
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
        "- Weekly global all-user post-minus-pre changes by event:",
    ]
    for _, row in prepost_global.sort_values("event_order").iterrows():
        lines.append(
            "  - "
            f"{row['event_label']}: equal-user {format_float(row['post_minus_pre_equal_user'])}; "
            f"activity-weighted {format_float(row['post_minus_pre_activity_weighted'])}."
        )
    lines.extend(
        [
            "",
            "Reviewer-response framing:",
            "- R1-M3: report both equal-user and activity-weighted mean ToxiGen probabilities and state whether the two estimands align.",
            "- R1-M7: replace `toxicity doubled` with `mean ToxiGen classifier probability approximately doubled`.",
            "- R2-5 / PDF M7: cite Hartvigsen et al. (2022) for ToxiGen validation and explicitly acknowledge platform/domain-shift limits; no manual validation sample was added.",
            "- R2-7.1: use the monthly newcomer-vs-existing decomposition as the cohort toxicity evidence.",
            "- R2-7.2: use the weekly event-window table/figure as the short-term post-ban evidence.",
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
        default=REPO_ROOT / "results" / "toxicity" / "compare" / "results",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=REPO_ROOT / "results" / "toxicity" / "compare" / "figures",
    )
    parser.add_argument("--window-weeks", type=int, default=8)
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
        LOGGER.info(
            "%s: %s raw rows, %s first-seen users",
            community,
            f"{len(raw):,}",
            f"{len(first_seen):,}",
        )

    monthly_users = pd.concat(monthly_rows, ignore_index=True)
    weekly_users = pd.concat([df for df in weekly_rows if not df.empty], ignore_index=True)

    monthly_summary = monthly_cohort_decomposition(monthly_users)
    weekly_summary = weekly_event_window_summary(weekly_users)
    weighting_summary = weighting_comparison_summary(monthly_summary)
    prepost_summary = weekly_prepost_change_summary(weekly_summary)

    monthly_path = args.output_dir / "toxicity_cohort_decomposition_summary.csv"
    weighting_path = args.output_dir / "toxicity_weighting_comparison_summary.csv"
    weekly_path = args.output_dir / "toxicity_weekly_event_window_summary.csv"
    prepost_path = args.output_dir / "toxicity_weekly_prepost_change_summary.csv"
    note_path = args.output_dir / "toxicity_review_response.md"

    monthly_summary.to_csv(monthly_path, index=False)
    weighting_summary.to_csv(weighting_path, index=False)
    weekly_summary.to_csv(weekly_path, index=False)
    prepost_summary.to_csv(prepost_path, index=False)

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
        prepost_summary=prepost_summary,
        results_dir=args.output_dir,
        figures_dir=args.figures_dir,
    )
    LOGGER.info("Wrote toxicity robustness outputs under %s", args.output_dir)


if __name__ == "__main__":
    main()
