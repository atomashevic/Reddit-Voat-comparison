#!/usr/bin/env python3
"""Plot single 8-panel overview for a community with key metrics."""

import argparse
from pathlib import Path
import sys
import pandas as pd
import matplotlib.pyplot as plt

# Ensure repository root on path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS, EVENT_LABELS

# Style constants (consistent with plot_global_summary.py)
VOAT_COLOR = "#800080"   # Purple
REDDIT_COLOR = "#ff7f0e" # Orange


def add_events(ax):
    """Add vertical event lines with clear labels."""
    ylim = ax.get_ylim()
    y_pos = ylim[0] + (ylim[1] - ylim[0]) * 0.98  # 98% up from bottom
    for key, ts in EVENTS.items():
        ax.axvline(ts, color="gray", linestyle="--", alpha=0.5, linewidth=0.8, zorder=1)
        label = EVENT_LABELS.get(key, key)
        ax.text(ts, y_pos, label, ha="center", va="top", fontsize=7, 
                color="gray", rotation=0, bbox=dict(boxstyle="round,pad=0.3", 
                facecolor="white", edgecolor="none", alpha=0.7))


def maybe_band(ax, df, col_base):
    lower = f"{col_base}_p5"
    upper = f"{col_base}_p95"
    if lower in df.columns and upper in df.columns:
        ax.fill_between(df["month_dt"], df[lower], df[upper], color="gray", alpha=0.15, label="Bootstrap 5-95%")


def plot_lines(ax, df, columns, title, ylabel=None):
    """Plot lines with 3-month rolling mean and lighter raw curve behind.
    
    columns: list of (label, col_name) tuples. If label contains "Reddit", uses
             REDDIT_COLOR; if "Voat", uses VOAT_COLOR.
    """
    for label, col in columns:
        if col not in df.columns:
            continue
        
        # Determine color based on label
        if "reddit" in label.lower():
            color = REDDIT_COLOR
        else:
            color = VOAT_COLOR
        
        # Compute 3-month centered rolling mean
        raw_data = df[col]
        rolling_data = raw_data.rolling(window=3, center=True, min_periods=1).mean()
        
        # Plot raw data (lighter, behind)
        ax.plot(df["month_dt"], raw_data, color=color, linewidth=1, alpha=0.3)
        # Plot rolling mean (thicker, in front)
        ax.plot(df["month_dt"], rolling_data, color=color, linewidth=2.5, label=f"{label} (3-mo avg)")
    
    ax.set_title(title)
    if ylabel:
        ax.set_ylabel(ylabel)
    add_events(ax)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--monthly-file", type=Path, required=True, help="Merged monthly metrics CSV")
    parser.add_argument("--partition-file", type=Path, help="Deprecated/Ignored", required=False)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-date", default="2015-09-01", help="Start date for plots (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2020-12-31", help="End date for plots (YYYY-MM-DD)")
    args = parser.parse_args()

    monthly = pd.read_csv(args.monthly_file)
    monthly["month_dt"] = pd.to_datetime(monthly["month"] + "-01")
    
    # Filter date range (default: September 2015 to December 2020)
    start_dt = pd.to_datetime(args.start_date)
    end_dt = pd.to_datetime(args.end_date)
    monthly = monthly[(monthly["month_dt"] >= start_dt) & (monthly["month_dt"] <= end_dt)].copy()

    fig, axes = plt.subplots(4, 2, figsize=(14, 16), sharex=True)
    axes = axes.flatten()

    # 1. Mean toxicity with bands
    plot_lines(
        axes[0],
        monthly,
        [
            ("Reddit", "toxicity_mean_reddit"),
            ("Voat", "toxicity_mean_voat"),
        ],
        "Mean Toxicity",
    )
    maybe_band(axes[0], monthly, "toxicity_mean")

    # 2. Mean sentiment (VADER) with bands
    plot_lines(
        axes[1],
        monthly,
        [
            ("Reddit", "vader_mean_reddit"),
            ("Voat", "vader_mean_voat"),
        ],
        "Mean Sentiment (VADER)",
    )
    maybe_band(axes[1], monthly, "vader_mean")

    # 3. Mean reputation
    plot_lines(
        axes[2],
        monthly,
        [
            ("Reddit", "reputation_mean_reddit"),
            ("Voat", "reputation_mean_voat"),
        ],
        "Mean Reputation",
    )

    # 4. Mean degree
    plot_lines(
        axes[3],
        monthly,
        [
            ("Reddit", "mean_degree_reddit"),
            ("Voat", "mean_degree_voat"),
        ],
        "Mean Degree",
    )

    # 5. Active users (Reddit) - use log scale due to scale difference
    if "active_users_reddit" in monthly.columns:
        raw_data = monthly["active_users_reddit"]
        rolling_data = raw_data.rolling(window=3, center=True, min_periods=1).mean()
        axes[4].plot(monthly["month_dt"], raw_data, color=REDDIT_COLOR, linewidth=1, alpha=0.3)
        axes[4].plot(monthly["month_dt"], rolling_data, color=REDDIT_COLOR, linewidth=2.5, label="Reddit (3-mo avg)")
        axes[4].set_yscale("log")
    axes[4].set_title("Active Users (Reddit)")
    axes[4].legend(loc="upper right")
    add_events(axes[4])

    # 6. Active users (Voat)
    if "active_users_voat" in monthly.columns:
        raw_data = monthly["active_users_voat"]
        rolling_data = raw_data.rolling(window=3, center=True, min_periods=1).mean()
        axes[5].plot(monthly["month_dt"], raw_data, color=VOAT_COLOR, linewidth=1, alpha=0.3)
        axes[5].plot(monthly["month_dt"], rolling_data, color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
    axes[5].set_title("Active Users (Voat)")
    axes[5].legend(loc="upper right")
    add_events(axes[5])

    # 7. Degree assortativity
    plot_lines(
        axes[6],
        monthly,
        [
            ("Reddit", "degree_assortativity_reddit"),
            ("Voat", "degree_assortativity_voat"),
        ],
        "Degree Assortativity",
    )

    # 8. E-I Index (Voat only - newcomer/existing mixing)
    if "ei_index" in monthly.columns:
        raw_data = monthly["ei_index"]
        rolling_data = raw_data.rolling(window=3, center=True, min_periods=1).mean()
        axes[7].plot(monthly["month_dt"], raw_data, color=VOAT_COLOR, linewidth=1, alpha=0.3)
        axes[7].plot(monthly["month_dt"], rolling_data, color=VOAT_COLOR, linewidth=2.5, label="Voat E-I (3-mo avg)")
    axes[7].set_title("E-I Index (Voat)\nLower = Inward, Higher = Outward")
    axes[7].axhline(0, color="k", linestyle="-", linewidth=0.5, alpha=0.3)
    axes[7].legend(loc="upper right")
    add_events(axes[7])

    # Legends
    for ax in axes:
        if ax.get_legend_handles_labels()[0]:
            ax.legend()

    for ax in axes[-2:]:
        ax.set_xlabel("Month")

    plt.tight_layout()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"{args.community}_overview.png"
    plt.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
