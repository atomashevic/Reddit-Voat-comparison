#!/usr/bin/env python3
"""Reddit and Voat time series panel script with split visualization.

This script creates time series panels showing:
- Before first event: solid orange line (Reddit only)
- After first event: dashed lines (orange for Reddit, purple for Voat)
- Only CORE DATA is used
- Three panels: toxicity, reputation, VADER sentiment

Example::

    python scripts/reddit_voat_timeseries_panels.py \
        --community technology \
        --outdir results/timeseries/technology
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from matplotlib.dates import MonthLocator
import pyarrow.parquet as pq

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Configure matplotlib
plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#333333",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "bold",
        "axes.grid": False,
        "legend.frameon": False,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "lines.linewidth": 1.6,
    }
)


def _load_key_events(notes_path: str = "notes/notes.md") -> List[Dict[str, object]]:
    """Load exactly three key events (D, E, G) and relabel to A, B, C.

    Events:
      A: /r/fatpeoplehate (D)
      B: /r/pizzagate (E)
      C: /r/GreatAwakening (G)
    """
    try:
        with open(notes_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        logger.warning(f"Could not load notes file: {e}")
        return []

    # Target three events (map D,E,G -> A,B,C)
    targets = [
        ("A", "/r/fatpeoplehate"),
        ("B", "/r/pizzagate"),
        ("C", "/r/GreatAwakening"),
    ]

    # allow ASCII hyphen, non-breaking hyphen, en dash, em dash, minus
    sep = r"[-‑‒–-−]"
    date_line = re.compile(rf"^\s*[-*]?\s*(\d{{4}}){sep}(\d{{2}})(?:{sep}(\d{{2}}))?:.*$", re.MULTILINE)

    found: List[Dict[str, object]] = []
    for out_label, subreddit in targets:
        picked = None
        for m in date_line.finditer(text):
            line = m.group(0)
            if subreddit in line:
                year, month, day = m.groups()
                day = day or "01"
                try:
                    dt = pd.to_datetime(f"{year}-{month}-{day}")
                    month_str = f"{year}-{month}"
                    picked = {
                        "label": out_label,
                        "month_str": month_str,
                        "month_dt": dt,
                        "desc": f"{year}-{month}-{day}: {subreddit}",
                    }
                    break
                except Exception:
                    continue
        if picked is not None:
            found.append(picked)

    return sorted(found, key=lambda x: x.get("month_dt", pd.Timestamp.max))[:3]


def _core_size_confidence_interval(
    values: pd.Series,
    member_counts: pd.Series,
    *,
    z_score: float = 1.96,
    min_members: int = 25,
) -> pd.DataFrame:
    """Return ci_lower and ci_upper confidence bands based on core member counts."""
    ci = pd.DataFrame(index=values.index, data={"ci_lower": np.nan, "ci_upper": np.nan})
    if values.empty or member_counts.empty:
        return ci
    
    aligned = (
        pd.concat({"value": values, "count": member_counts}, axis=1)
        .dropna(subset=["value", "count"])
        .sort_index()
    )
    if aligned.empty:
        return ci

    large_counts = aligned[aligned["count"] >= min_members]

    rolling_std = aligned["value"].rolling(window=3, min_periods=2).std(ddof=0)
    fallback_std = large_counts["value"].std(ddof=0) if not large_counts.empty else aligned["value"].std(ddof=0)
    if pd.isna(fallback_std):
        fallback_std = 0.0

    series_std = rolling_std.fillna(fallback_std)
    if fallback_std > 0:
        series_std = series_std.replace(0.0, fallback_std)
    else:
        series_std = series_std.fillna(0.0)

    stderr = series_std / np.sqrt(aligned["count"].clip(lower=1))
    half_width = z_score * stderr

    ci.loc[aligned.index, "ci_lower"] = (aligned["value"] - half_width).astype(float)
    ci.loc[aligned.index, "ci_upper"] = (aligned["value"] + half_width).astype(float)
    return ci


def load_reddit_core_metrics(community: str, cp_dir: str) -> pd.DataFrame:
    """Load Reddit core-periphery metrics for the community."""
    metrics_path = Path(cp_dir) / "reddit" / "results" / f"reddit_{community}_cp_monthly_group_metrics.csv"
    
    if not metrics_path.exists():
        raise FileNotFoundError(f"Reddit metrics file not found: {metrics_path}")
    
    df = pd.read_csv(metrics_path)
    
    # Filter for core data only
    core_df = df[df["group"] == "core"].copy()
    core_df["month_dt"] = pd.to_datetime(core_df["month"] + "-01", errors="coerce")
    
    return core_df


def _compute_core_monthly_metrics_from_labels(
    platform: str,
    community: str,
    cp_dir: str,
    data_dir: str,
) -> pd.DataFrame:
    """Compute per-month core metrics (toxicity, vader, textblob, subjectivity) from labels + interactions."""
    labels_path = Path(cp_dir) / platform / "results" / f"{platform}_{community}_cp_labels.csv"
    if not labels_path.exists():
        raise FileNotFoundError(f"Missing labels CSV: {labels_path}")
    labels = pd.read_csv(labels_path)
    labels = labels.rename(columns={"window": "month", "node_id": "user_id"})[["month", "user_id", "label"]]
    labels["label"] = labels["label"].astype(int)

    parquet_path = Path(data_dir) / f"{platform}_{community}_madoc.parquet"
    if not parquet_path.exists():
        # try case-insensitive search
        raise FileNotFoundError(f"Missing Parquet: {parquet_path}")
    table = pq.read_table(str(parquet_path), columns=[
        "publish_date",
        "user_id",
        "interaction_type",
        "sentiment_vader",
        "sentiment_textblob",
        "subjectivity_textblob",
        "toxicity_toxigen",
    ])
    df = table.to_pandas()
    df.columns = [c.lower() for c in df.columns]
    itype = df["interaction_type"].astype(str).str.lower()
    df = df[itype.isin(["post", "comment"])].copy()
    series = pd.to_numeric(df["publish_date"], errors="coerce")
    unit = "ms" if series.dropna().median() > 1e11 else "s"
    dates = pd.to_datetime(series, unit=unit, errors="coerce", utc=True)
    df = df.assign(month=dates.dt.strftime("%Y-%m"))
    df = df[df["month"].notna()].copy()

    # Join labels
    j = df.merge(labels, on=["month", "user_id"], how="inner")
    # Keep core only (label 0)
    j = j[j["label"].astype(int) == 0].copy()
    # Coerce to numeric
    for col in ["toxicity_toxigen", "sentiment_vader", "sentiment_textblob", "subjectivity_textblob"]:
        j[col] = pd.to_numeric(j[col], errors="coerce")
    # Per user per month means
    user_month = (
        j.groupby(["month", "user_id"], as_index=False)
        .agg(
            mean_toxicity=("toxicity_toxigen", "mean"),
            mean_vader=("sentiment_vader", "mean"),
            mean_tb=("sentiment_textblob", "mean"),
            mean_subj=("subjectivity_textblob", "mean"),
        )
    )
    # Aggregate across users (core only) with dispersion estimates
    group_metrics = (
        user_month.groupby(["month"], as_index=False)
        .agg(
            mean_toxicity_per_user=("mean_toxicity", "mean"),
            std_toxicity_per_user=("mean_toxicity", "std"),
            mean_sentiment_vader_per_user=("mean_vader", "mean"),
            std_sentiment_vader_per_user=("mean_vader", "std"),
            mean_sentiment_textblob_per_user=("mean_tb", "mean"),
            std_sentiment_textblob_per_user=("mean_tb", "std"),
            mean_subjectivity_textblob_per_user=("mean_subj", "mean"),
            std_subjectivity_textblob_per_user=("mean_subj", "std"),
            member_count=("user_id", "nunique"),
        )
    )
    group_metrics["group"] = "core"
    group_metrics["member_count"] = group_metrics["member_count"].astype("Int64")
    group_metrics["core_size_block"] = group_metrics["member_count"]

    # Standard errors for per-user means
    member_counts = group_metrics["member_count"].astype(float)
    member_sqrt = np.sqrt(member_counts.clip(lower=1.0))
    std_se_pairs = [
        ("std_toxicity_per_user", "se_toxicity_per_user"),
        ("std_sentiment_vader_per_user", "se_sentiment_vader_per_user"),
        ("std_sentiment_textblob_per_user", "se_sentiment_textblob_per_user"),
        ("std_subjectivity_textblob_per_user", "se_subjectivity_textblob_per_user"),
    ]
    for std_col, se_col in std_se_pairs:
        if std_col in group_metrics.columns:
            std_values = group_metrics[std_col].astype(float)
            se_values = std_values / member_sqrt
            se_values = se_values.where(member_counts >= 2, np.nan)
            group_metrics[se_col] = se_values

    group_metrics["month_dt"] = pd.to_datetime(group_metrics["month"] + "-01", errors="coerce")
    return group_metrics


def load_voat_core_metrics(community: str, cp_dir: str, data_dir: str) -> pd.DataFrame:
    """Load Voat core-periphery metrics for the community."""
    # Check if Voat has monthly group metrics
    metrics_path = Path(cp_dir) / "voat" / "results" / f"voat_{community}_cp_monthly_group_metrics.csv"
    if metrics_path.exists():
        logger.info(
            "Voat monthly group metrics found; recomputing per-user core statistics for confidence intervals"
        )
    else:
        logger.info("Voat monthly group metrics missing; computing core metrics from labels + Parquet")

    return _compute_core_monthly_metrics_from_labels("voat", community, cp_dir, data_dir)


def load_core_reputation(platform: str, community: str, reputation_dir: str) -> pd.DataFrame:
    """Load monthly CP reputation and return core-only series as DataFrame with core_mean_rep column."""
    rep_path = Path(reputation_dir) / platform / "results" / f"{platform}_{community}_cp_monthly_reputation.csv"
    if not rep_path.exists():
        # Also check nested per-community layout
        alt = Path(reputation_dir) / community / platform / "results" / f"{platform}_{community}_cp_monthly_reputation.csv"
        if alt.exists():
            rep_path = alt
    if not rep_path.exists():
        raise FileNotFoundError(f"Missing monthly reputation CSV: {rep_path}")
    df = pd.read_csv(rep_path)
    cols = set(df.columns)
    core_col = None
    if "core_mean_rep_active" in cols:
        core_col = "core_mean_rep_active"
    elif "core_mean_rep" in cols:
        core_col = "core_mean_rep"
    else:
        # Fallback to median if means missing
        core_col = "core_median_rep_active" if "core_median_rep_active" in cols else "core_median_rep"
    out = df[["month", core_col]].rename(columns={core_col: "core_mean_rep"}).copy()
    out["month_dt"] = pd.to_datetime(out["month"] + "-01", errors="coerce")
    # Add SE column (set to NaN for now, as raw data not available)
    out["se_core_mean_rep"] = pd.NA
    return out


## removed: core size panel helper (not used)


def create_timeseries_panels(
    reddit_core_df: pd.DataFrame,
    voat_core_df: pd.DataFrame,
    events: List[Dict[str, object]],
    community: str,
    out_path: Path,
) -> None:
    """Create time series panels with split visualization using only CORE data."""
    
    # Find the first event date
    first_event_dt = None
    if events:
        first_event_dt = events[0]["month_dt"]
    
    # Define metrics to plot (core-only): toxicity, reputation, VADER
    metrics = [
        ("mean_toxicity_per_user", "Toxicity"),
        ("core_mean_rep", "Reputation"),
        ("mean_sentiment_vader_per_user", "VADER Sentiment"),
    ]
    count_candidates = ("member_count", "core_size_block")
    voat_se_candidates = {
        "mean_toxicity_per_user": ["se_toxicity_per_user", "std_toxicity_per_user"],
        "mean_sentiment_vader_per_user": ["se_sentiment_vader_per_user", "std_sentiment_vader_per_user"],
        "mean_sentiment_textblob_per_user": ["se_sentiment_textblob_per_user", "std_sentiment_textblob_per_user"],
        "mean_subjectivity_textblob_per_user": ["se_subjectivity_textblob_per_user", "std_subjectivity_textblob_per_user"],
        "core_mean_rep": ["se_core_mean_rep", "std_core_mean_rep"],
    }

    # Create figure with 3 subplots
    n_panels = len(metrics)
    fig, axes = plt.subplots(n_panels, 1, figsize=(12, 3.2 * n_panels + 1), sharex=True, constrained_layout=True)
    
    reddit_orange = "#FF4500"  # Reddit brand orange
    voat_purple = "#800080"
    line_width = 2.8

    # Ensure axes is iterable
    if n_panels == 1:
        axes = [axes]

    for i, (core_col, title) in enumerate(metrics):
        ax = axes[i]

        # Plot Reddit core data: dashed entire series, then overlay solid before first event
        if core_col in reddit_core_df.columns:
            reddit_core_data = (
                reddit_core_df.dropna(subset=[core_col])
                .sort_values("month_dt")
            )
            if not reddit_core_data.empty:
                counts_col = next((c for c in count_candidates if c in reddit_core_data.columns), None)
                reddit_ci = None
                if counts_col:
                    reddit_ci = _core_size_confidence_interval(
                        reddit_core_data[core_col],
                        reddit_core_data[counts_col],
                    )

                if first_event_dt is not None:
                    before_event = reddit_core_data[reddit_core_data["month_dt"] < first_event_dt]
                    after_event = reddit_core_data[reddit_core_data["month_dt"] >= first_event_dt]
                else:
                    before_event = reddit_core_data
                    after_event = pd.DataFrame()

                if not before_event.empty:
                    ax.plot(
                        before_event["month_dt"],
                        before_event[core_col],
                        color=reddit_orange,
                        linewidth=line_width,
                        linestyle="-",
                        alpha=0.95,
                        label="Reddit Core (pre-event)" if first_event_dt is not None else "Reddit Core",
                    )
                if not after_event.empty:
                    ax.plot(
                        after_event["month_dt"],
                        after_event[core_col],
                        color=reddit_orange,
                        linewidth=line_width,
                        linestyle="--",
                        alpha=0.9,
                        label="Reddit Core (post-event)",
                    )

                if reddit_ci is not None:
                    mask = reddit_ci["ci_lower"].notna() & reddit_ci["ci_upper"].notna()
                    if mask.any():
                        fill_df = reddit_core_data.loc[mask].copy()
                        ax.fill_between(
                            fill_df["month_dt"],
                            reddit_ci.loc[mask, "ci_lower"],
                            reddit_ci.loc[mask, "ci_upper"],
                            color=reddit_orange,
                            alpha=0.16,
                            linewidth=0,
                        )

        # Plot Voat core data (dashed purple line after first event)
        if core_col in voat_core_df.columns and not voat_core_df.empty:
            voat_core_data = (
                voat_core_df.dropna(subset=[core_col])
                .sort_values("month_dt")
            )
            if not voat_core_data.empty:
                if first_event_dt is not None:
                    voat_subset = voat_core_data[voat_core_data["month_dt"] >= first_event_dt]
                else:
                    voat_subset = voat_core_data

                if not voat_subset.empty:
                    ax.plot(
                        voat_subset["month_dt"],
                        voat_subset[core_col],
                        color=voat_purple,
                        linewidth=line_width,
                        linestyle="--",
                        label="Voat Core",
                        alpha=0.8,
                    )
                    se_col = next(
                        (c for c in voat_se_candidates.get(core_col, []) if c in voat_subset.columns),
                        None,
                    )
                    if se_col and voat_subset[se_col].notna().any():
                        se_series = voat_subset[se_col].astype(float)
                        if se_col.startswith("std_"):
                            counts_col = next((c for c in count_candidates if c in voat_subset.columns), None)
                            if counts_col:
                                se_series = se_series / np.sqrt(voat_subset[counts_col].astype(float).clip(lower=1.0))
                            else:
                                se_series = None
                        if se_series is not None:
                            lower = voat_subset[core_col].astype(float) - 1.96 * se_series
                            upper = voat_subset[core_col].astype(float) + 1.96 * se_series
                            mask = pd.notna(lower) & pd.notna(upper)
                            if mask.any():
                                ax.fill_between(
                                    voat_subset.loc[mask, "month_dt"],
                                    lower[mask],
                                    upper[mask],
                                    color=voat_purple,
                                    alpha=0.16,
                                    linewidth=0,
                                )
                                continue

                    # Fallback to helper-based CI if no standard error available
                    counts_col = next((c for c in count_candidates if c in voat_subset.columns), None)
                    if counts_col:
                        voat_ci = _core_size_confidence_interval(
                            voat_subset[core_col],
                            voat_subset[counts_col],
                        )
                        mask = voat_ci["ci_lower"].notna() & voat_ci["ci_upper"].notna()
                        if mask.any():
                            fill_df = voat_subset.loc[mask].copy()
                            ax.fill_between(
                                fill_df["month_dt"],
                                voat_ci.loc[mask, "ci_lower"],
                                voat_ci.loc[mask, "ci_upper"],
                                color=voat_purple,
                                alpha=0.16,
                                linewidth=0,
                            )

        # Add vertical lines for events (only three)
        ymin, ymax = ax.get_ylim()
        label_y = ymax - 0.05 * (ymax - ymin) if np.isfinite(ymax) else ymax
        for event in events[:3]:
            event_dt = event.get("month_dt")
            if event_dt is not None:
                ax.axvline(
                    event_dt,
                    ls="--",
                    lw=1,
                    color="k",
                    alpha=0.6,
                    zorder=5,
                )
                ax.text(
                    event_dt,
                    label_y,
                    event["label"],
                    fontsize=8,
                    ha="center",
                    va="top",
                    rotation=90,
                    zorder=6,
                )

        # Formatting
        ax.set_title(title, loc="left", pad=8)
        ax.set_ylabel(title)
        # Remove grid lines
        ax.grid(False)
        ax.legend(loc="upper left")
        
        # Set x-axis formatting
        ax.xaxis.set_major_locator(MonthLocator(interval=6))
        ax.tick_params(axis="x", rotation=45)
    
    # Set x-label on bottom subplot
    axes[-1].set_xlabel("Month")
    
    # Overall title
    fig.suptitle(f"{community.title()} – Core time series (Reddit vs Voat)", fontsize=14, y=0.98)
    
    # Save figure
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved time series panels to {out_path}")


def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--community",
        required=True,
        help="Community name (e.g., technology, funny, gaming)"
    )
    parser.add_argument(
        "--outdir",
        required=True,
        help="Output directory for results and figures"
    )
    parser.add_argument(
        "--cp-dir",
        default="results/core-periphery",
        help="Directory containing core-periphery results"
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing interaction Parquet files (reddit_/voat_ *.parquet)"
    )
    parser.add_argument(
        "--reputation-dir",
        default="results/reputation",
        help="Directory containing monthly CP reputation CSVs"
    )
    parser.add_argument(
        "--notes-path",
        default="notes/notes.md",
        help="Path to notes file containing key events"
    )
    
    args = parser.parse_args()
    
    # Create output directory
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Load key events
    logger.info("Loading key events...")
    events = _load_key_events(args.notes_path)
    logger.info(f"Loaded {len(events)} key events")
    
    # Load Reddit core metrics
    logger.info(f"Loading Reddit core metrics for {args.community}...")
    try:
        reddit_core_df = load_reddit_core_metrics(args.community, args.cp_dir)
        logger.info(f"Loaded {len(reddit_core_df)} Reddit core records")
    except FileNotFoundError as e:
        logger.error(f"Could not load Reddit core metrics: {e}")
        return
    
    # Load Voat core metrics
    logger.info(f"Loading Voat core metrics for {args.community}...")
    try:
        voat_core_df = load_voat_core_metrics(args.community, args.cp_dir, args.data_dir)
        logger.info(f"Loaded {len(voat_core_df)} Voat core records")
    except FileNotFoundError as e:
        logger.warning(f"Could not load Voat core metrics: {e}")
        voat_core_df = pd.DataFrame()  # Empty dataframe
    
    # Load monthly CP reputation and merge into core dataframes
    try:
        rep_reddit = load_core_reputation("reddit", args.community, args.reputation_dir)
        reddit_core_df = reddit_core_df.merge(rep_reddit[["month", "core_mean_rep"]], on="month", how="left")
    except Exception as e:
        logger.warning("Reddit reputation not available: %s", e)
        reddit_core_df["core_mean_rep"] = pd.NA
    try:
        rep_voat = load_core_reputation("voat", args.community, args.reputation_dir)
        voat_core_df = voat_core_df.merge(rep_voat[["month", "core_mean_rep"]], on="month", how="left")
    except Exception as e:
        logger.warning("Voat reputation not available: %s", e)
        if not voat_core_df.empty:
            voat_core_df["core_mean_rep"] = pd.NA

    # core size panel removed
    
    # Create time series panels
    logger.info("Creating time series panels...")
    out_path = out_dir / f"{args.community}_timeseries_panels.png"
    
    create_timeseries_panels(
        reddit_core_df=reddit_core_df,
        voat_core_df=voat_core_df,
        events=events,
        community=args.community,
        out_path=out_path
    )
    
    logger.info(f"Analysis complete. Results saved to {out_dir}")


if __name__ == "__main__":
    main()
