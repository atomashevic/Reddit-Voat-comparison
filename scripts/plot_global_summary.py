#!/usr/bin/env python3
"""Plot global aggregate summary (Voat) across all communities.

5 Panels:
1. E-I Index
2. Mean Toxicity
3. Q90 Toxicity (NEW)
4. Degree Assortativity
5. Event-Period Heatmap: Voat-Reddit Toxicity Difference by Period
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.dates as mdates
import numpy as np
import seaborn as sns

# Ensure repository root on path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS, EVENT_LABELS

# Style
VOAT_COLOR = "#800080"  # Purple
REDDIT_COLOR = "#ff7f0e"  # Orange
TOXICITY_COLOR = "#D62728"  # Red
EVENT_COLOR = "#333333"
EVENT_ALPHA = 0.15

# Custom event labels using short names
SHORT_EVENT_LABELS = {
    "A": "FPH",
    "B": "GA",
    "C": "TD",
    "D": "PG",
}


COMMUNITIES = ["funny", "gaming", "technology", "videos", "gifs", "pics"]


def load_reddit_toxicity(results_root: Path, start_date, end_date) -> pd.DataFrame:
    """Load and aggregate Reddit toxicity across all communities."""
    all_data = []
    for comm in COMMUNITIES:
        path = results_root / "reddit" / comm / f"reddit_{comm}_monthly_aggregates.csv"
        if path.exists():
            df = pd.read_csv(path)
            df["month_dt"] = pd.to_datetime(df["month"] + "-01")
            df = df[(df["month_dt"] >= start_date) & (df["month_dt"] <= end_date)]
            if "toxicity_mean" in df.columns and "active_users" in df.columns:
                all_data.append(df[["month_dt", "toxicity_mean", "active_users"]])
    
    if not all_data:
        return None
    
    full_df = pd.concat(all_data, ignore_index=True)
    # Weighted average by active users
    def weighted_avg(group):
        if group["active_users"].sum() > 0:
            return np.average(group["toxicity_mean"], weights=group["active_users"])
        return np.nan
    
    agg = full_df.groupby("month_dt", as_index=False).apply(weighted_avg, include_groups=False)
    agg.columns = ["month_dt", "toxicity_mean"]
    return agg.sort_values("month_dt")


def add_events_band(ax):
    """Add vertical bands for events with clear labels."""
    ylim = ax.get_ylim()
    y_pos = ylim[0] + (ylim[1] - ylim[0]) * 0.98
    for key, date in EVENTS.items():
        # Draw line
        ax.axvline(date, color=EVENT_COLOR, linestyle="--", alpha=0.4, linewidth=0.8, zorder=1)
        # Add label at top with background - use short labels
        label = SHORT_EVENT_LABELS.get(key, key)
        ax.text(date, y_pos, label, ha="center", va="top", fontsize=8, fontweight="bold",
                color=EVENT_COLOR, rotation=0, 
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", 
                         edgecolor="none", alpha=0.8))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", type=Path, required=True, help="Global aggregate CSV")
    parser.add_argument("--heatmap-file", type=Path, default=Path("results/global/event_period_toxicity_diff.csv"), help="Event period toxicity diff CSV")
    parser.add_argument("--output-dir", type=Path, default=Path("figures/global"))
    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"Input file not found: {args.input_file}")
        sys.exit(1)

    # Load main aggregate data
    df = pd.read_csv(args.input_file)
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    df = df.sort_values("month_dt")
    
    # Filter date range: September 2015 to December 2020
    start_date = pd.Timestamp("2015-09-01")
    end_date = pd.Timestamp("2020-12-31")
    df = df[(df["month_dt"] >= start_date) & (df["month_dt"] <= end_date)].copy()
    
    # Load event-period heatmap data
    heatmap_df = None
    heatmap_pivot = None
    if args.heatmap_file.exists():
        heatmap_df = pd.read_csv(args.heatmap_file)
        # Pivot for heatmap: communities as rows, periods as columns
        heatmap_pivot = heatmap_df.pivot(index="community", columns="period", values="toxicity_diff")
        # Order columns chronologically: A-D, D-B, B-C, C-end
        period_order = ["A-D", "D-B", "B-C", "C-end"]
        heatmap_pivot = heatmap_pivot[[col for col in period_order if col in heatmap_pivot.columns]]

    # Create figure with 4 panels (3 time series + 1 heatmap)
    fig = plt.figure(figsize=(12, 10))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.2], hspace=0.35, wspace=0.3)
    
    ax1 = fig.add_subplot(gs[0, 0])  # E-I Index
    ax2 = fig.add_subplot(gs[0, 1])  # Mean Toxicity
    ax3 = fig.add_subplot(gs[1, 0])  # Assortativity
    ax4 = fig.add_subplot(gs[1, 1])  # Event-Period Heatmap
    
    # Compute 3-month rolling means
    df_rolling = df.copy()
    for col in ["ei_index", "toxicity_mean_voat", "degree_assortativity_voat"]:
        if col in df_rolling.columns:
            df_rolling[f"{col}_roll"] = df_rolling[col].rolling(window=3, center=True, min_periods=1).mean()
    
    # 1. E-I Index
    if "ei_index" in df.columns:
        ax1.plot(df["month_dt"], df["ei_index"], color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax1.plot(df_rolling["month_dt"], df_rolling["ei_index_roll"], color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
        ax1.set_ylabel("E-I Index", fontweight="bold")
        ax1.set_title("E-I Index (Voat)")
        ax1.axhline(0, color="k", linestyle="-", linewidth=0.5, alpha=0.3)
        ax1.legend(loc="upper left", fontsize=8)
        add_events_band(ax1)
    
    # 2. Mean Toxicity (both Reddit and Voat)
    # Load Reddit toxicity from community files and aggregate
    reddit_tox = load_reddit_toxicity(args.input_file.parent.parent, start_date, end_date)
    
    if "toxicity_mean_voat" in df.columns:
        ax2.plot(df["month_dt"], df["toxicity_mean_voat"], color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax2.plot(df_rolling["month_dt"], df_rolling["toxicity_mean_voat_roll"], color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
    
    if reddit_tox is not None and not reddit_tox.empty:
        reddit_tox["tox_roll"] = reddit_tox["toxicity_mean"].rolling(window=3, center=True, min_periods=1).mean()
        ax2.plot(reddit_tox["month_dt"], reddit_tox["toxicity_mean"], color=REDDIT_COLOR, linewidth=1, alpha=0.3)
        ax2.plot(reddit_tox["month_dt"], reddit_tox["tox_roll"], color=REDDIT_COLOR, linewidth=2.5, label="Reddit (3-mo avg)")
    
    ax2.set_ylabel("Mean Toxicity", fontweight="bold")
    ax2.set_title("Mean Toxicity")
    ax2.legend(loc="upper left", fontsize=8)
    add_events_band(ax2)

    # 3. Degree Assortativity
    if "degree_assortativity_voat" in df.columns:
        ax3.plot(df["month_dt"], df["degree_assortativity_voat"], color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax3.plot(df_rolling["month_dt"], df_rolling["degree_assortativity_voat_roll"], color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
        ax3.set_ylabel("Assortativity", fontweight="bold")
        ax3.set_title("Degree Assortativity (Voat)")
        ax3.axhline(0, color="k", linestyle="-", linewidth=0.5, alpha=0.3)
        ax3.legend(loc="upper left", fontsize=8)
        add_events_band(ax3)
    
    # Format X axes for time series
    for ax in [ax1, ax2, ax3]:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.set_xlabel("Year")
    
    # 4. Event-Period Heatmap: Voat-Reddit Toxicity Difference
    if heatmap_df is not None and not heatmap_pivot.empty:
        # Create a visually appealing heatmap
        sns.heatmap(
            heatmap_pivot, 
            ax=ax4, 
            annot=True,
            annot_kws={"size": 11, "weight": "bold"},
            fmt=".2f", 
            cmap="coolwarm",
            center=0,
            cbar_kws={"label": "Toxicity Diff (Voat − Reddit)", "shrink": 0.9, "pad": 0.02},
            linewidths=2,
            linecolor="white",
            vmin=-0.05,
            vmax=0.18,
            square=True
        )
        ax4.set_title("Toxicity Difference by Event Period", 
                     fontweight="bold", fontsize=11, pad=12)
        ax4.set_xlabel("Event Period", fontweight="bold", fontsize=10)
        ax4.set_ylabel("Community", fontweight="bold", fontsize=10)
        
        # Period labels using event names: FPH, PG, GA, TD
        period_labels = ["FPH→PG", "PG→GA", "GA→TD", "TD→End"]
        ax4.set_xticklabels(period_labels, rotation=0, ha="center", fontsize=10, fontweight="bold")
        ax4.set_yticklabels(ax4.get_yticklabels(), rotation=0, fontsize=10)
        
    else:
        ax4.text(0.5, 0.5, "Heatmap data not available", 
                ha="center", va="center", transform=ax4.transAxes)
        ax4.set_title("Voat-Reddit Toxicity Difference by Event Period")
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / "voat_global_summary.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

