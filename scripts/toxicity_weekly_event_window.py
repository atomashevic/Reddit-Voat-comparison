#!/usr/bin/env python3
"""Weekly toxicity windows around Reddit ban events.

Computes short-term toxicity dynamics in weekly bins from four weeks before to
four weeks after each event. The analysis compares existing users with users
whose first observed Voat activity falls after the focal event.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from migration_utils import EVENTS_CHRONO, EVENT_LABELS_CHRONO

LOGGER = logging.getLogger(__name__)

COMMUNITIES = ["funny", "gaming", "gifs", "pics", "technology", "videos"]
EVENT_ORDER = ["A", "B", "C", "D"]
WEEK_OFFSETS = list(range(-4, 5))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--communities", nargs="*", default=COMMUNITIES)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/basic/compare"),
        help="Output directory with results/ and figures/ subdirectories.",
    )
    parser.add_argument("--skip-figures", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def event_end(event_key: str) -> pd.Timestamp:
    idx = EVENT_ORDER.index(event_key)
    if idx + 1 < len(EVENT_ORDER):
        return EVENTS_CHRONO[EVENT_ORDER[idx + 1]]
    return pd.Timestamp.max


def normalize_publish_dates(publish_date: pd.Series) -> pd.Series:
    """Convert epoch seconds or milliseconds to datetimes."""
    numeric = pd.to_numeric(publish_date, errors="coerce")
    numeric = numeric.mask(numeric > 100000000000, numeric / 1000)
    return pd.to_datetime(numeric, unit="s", errors="coerce")


def load_community(data_dir: Path, community: str) -> pd.DataFrame:
    path = data_dir / f"voat_{community}_madoc.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing Voat data parquet: {path}")

    df = pd.read_parquet(
        path,
        columns=["user_id", "publish_date", "toxicity_toxigen"],
    )
    df = df.dropna(subset=["user_id", "publish_date"]).copy()
    df["community"] = community
    df["user_id"] = df["user_id"].astype(str)
    df["published_at"] = normalize_publish_dates(df["publish_date"])
    df = df.dropna(subset=["published_at"])
    return df


def attach_global_first_seen(data: pd.DataFrame) -> pd.DataFrame:
    first_seen = data.groupby("user_id")["published_at"].min().rename("first_seen")
    return data.join(first_seen, on="user_id")


def assign_event_cohort(first_seen: pd.Series, event_key: str) -> pd.Series:
    event_date = EVENTS_CHRONO[event_key]
    next_event = event_end(event_key)
    return np.where(
        first_seen < event_date,
        "existing",
        np.where(first_seen < next_event, "event_arrival", "future_arrival"),
    )


def summarize_group(group: pd.DataFrame) -> pd.Series:
    user_means = group.groupby("user_id")["toxicity_toxigen"].mean()
    return pd.Series(
        {
            "n_users": int(group["user_id"].nunique()),
            "n_posts": int(len(group)),
            "toxicity_user_mean": float(user_means.mean()) if not user_means.empty else np.nan,
            "toxicity_activity_mean": float(group["toxicity_toxigen"].mean()),
        }
    )


def compute_weekly_windows(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    scored = data.dropna(subset=["toxicity_toxigen"]).copy()
    for event_key in EVENT_ORDER:
        event_date = EVENTS_CHRONO[event_key]
        window_start = event_date + pd.Timedelta(weeks=min(WEEK_OFFSETS))
        window_end = event_date + pd.Timedelta(weeks=max(WEEK_OFFSETS) + 1)

        window = scored[
            (scored["published_at"] >= window_start)
            & (scored["published_at"] < window_end)
        ].copy()
        if window.empty:
            continue

        days_since = (window["published_at"] - event_date).dt.days
        window["relative_week"] = np.floor(days_since / 7).astype(int)
        window = window[window["relative_week"].isin(WEEK_OFFSETS)].copy()
        window["event"] = event_key
        window["event_label"] = EVENT_LABELS_CHRONO[event_key]
        window["cohort_group"] = assign_event_cohort(window["first_seen"], event_key)
        window = window[window["cohort_group"].isin(["existing", "event_arrival"])].copy()

        group_cols = ["community", "event", "event_label", "relative_week", "cohort_group"]
        community_summary = (
            window.groupby(group_cols)
            .apply(summarize_group, include_groups=False)
            .reset_index()
        )

        global_summary = (
            window.groupby(["event", "event_label", "relative_week", "cohort_group"])
            .apply(summarize_group, include_groups=False)
            .reset_index()
        )
        global_summary.insert(0, "community", "global")
        rows.extend([community_summary, global_summary])

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def summarize_prepost(weekly: pd.DataFrame) -> pd.DataFrame:
    global_weekly = weekly[weekly["community"] == "global"].copy()
    rows = []
    for (event, label, cohort), group in global_weekly.groupby(
        ["event", "event_label", "cohort_group"]
    ):
        pre = group[group["relative_week"].between(-4, -1)]
        post = group[group["relative_week"].between(0, 4)]
        rows.append(
            {
                "event": event,
                "event_label": label,
                "cohort_group": cohort,
                "pre_n_users_mean": pre["n_users"].mean(),
                "post_n_users_mean": post["n_users"].mean(),
                "pre_n_posts_mean": pre["n_posts"].mean(),
                "post_n_posts_mean": post["n_posts"].mean(),
                "pre_user_toxicity_mean": pre["toxicity_user_mean"].mean(),
                "post_user_toxicity_mean": post["toxicity_user_mean"].mean(),
                "delta_user_toxicity": (
                    post["toxicity_user_mean"].mean() - pre["toxicity_user_mean"].mean()
                ),
                "pre_activity_toxicity_mean": pre["toxicity_activity_mean"].mean(),
                "post_activity_toxicity_mean": post["toxicity_activity_mean"].mean(),
                "delta_activity_toxicity": (
                    post["toxicity_activity_mean"].mean() - pre["toxicity_activity_mean"].mean()
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["event", "cohort_group"])


def plot_global_weekly(weekly: pd.DataFrame, output_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        LOGGER.warning("matplotlib unavailable; skipping figure")
        return

    plot_df = weekly[weekly["community"] == "global"].copy()
    if plot_df.empty:
        return

    colors = {"existing": "#2c7fb8", "event_arrival": "#d95f0e"}
    labels = {"existing": "Existing users", "event_arrival": "Event-window arrivals"}
    fig, axes = plt.subplots(3, 4, figsize=(14, 8), sharex=True, sharey="row")
    metrics = [
        ("toxicity_user_mean", "User-weighted mean toxicity"),
        ("toxicity_activity_mean", "Activity-weighted mean toxicity"),
        ("n_posts", "Weekly posts"),
    ]

    for col, event_key in enumerate(EVENT_ORDER):
        event_df = plot_df[plot_df["event"] == event_key]
        for row, (metric, ylabel) in enumerate(metrics):
            ax = axes[row, col]
            for cohort_group in ["existing", "event_arrival"]:
                sub = event_df[event_df["cohort_group"] == cohort_group].sort_values(
                    "relative_week"
                )
                if sub.empty:
                    continue
                ax.plot(
                    sub["relative_week"],
                    sub[metric],
                    marker="o",
                    linewidth=1.8,
                    color=colors[cohort_group],
                    label=labels[cohort_group],
                )
            ax.axvline(0, color="black", linewidth=1, linestyle="--", alpha=0.65)
            ax.grid(alpha=0.25)
            ax.set_title(EVENT_LABELS_CHRONO[event_key] if row == 0 else "")
            if col == 0:
                ax.set_ylabel(ylabel)
            if row == len(metrics) - 1:
                ax.set_xlabel("Weeks from event")
                ax.set_yscale("log")
            ax.set_xticks(WEEK_OFFSETS)

    handles, legend_labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", ncol=2, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    all_data = []
    for community in args.communities:
        LOGGER.info("Loading %s", community)
        all_data.append(load_community(args.data_dir, community))

    data = attach_global_first_seen(pd.concat(all_data, ignore_index=True))
    weekly = compute_weekly_windows(data)
    prepost = summarize_prepost(weekly)

    results_dir = args.output_dir / "results"
    figures_dir = args.output_dir / "figures"
    results_dir.mkdir(parents=True, exist_ok=True)
    weekly.to_csv(results_dir / "toxicity_weekly_event_window_by_cohort.csv", index=False)
    prepost.to_csv(results_dir / "toxicity_weekly_event_window_prepost_summary.csv", index=False)

    if not args.skip_figures:
        plot_global_weekly(
            weekly,
            figures_dir / "toxicity_weekly_event_window_by_cohort.png",
        )

    LOGGER.info("Wrote weekly toxicity event-window outputs to %s", args.output_dir)


if __name__ == "__main__":
    main()
