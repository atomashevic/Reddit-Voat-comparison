#!/usr/bin/env python3
"""Plot 7-panel overview for a community with key metrics.

Panels (consistent with Figure 1 styling):
1. Mean Toxicity (Voat vs Reddit)
2. Mean Reputation (with 4.5 threshold)
3. Mean Degree
4. Active Users (Reddit, log scale)
5. Active Users (Voat)
6. Degree Assortativity
7. E-I Index (centered)

Event labels positioned at bottom-right of each panel (matching Figure 1).
"""

import argparse
from pathlib import Path
import sys
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Ensure repository root on path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS_CHRONO, EVENT_LABELS_CHRONO

# Style constants - consistent with plot_global_summary.py (Figure 1)
VOAT_COLOR = "#F46036"      # Coral/orange-red (same as Figure 1)
REDDIT_COLOR = "#1B998B"    # Teal/green
EVENT_COLOR = "#333333"
EVENT_LABEL_OFFSET_X = 14   # Horizontal offset for event labels (same as Figure 1)

# Short event labels
SHORT_EVENT_LABELS = {
    "A": "FPH",
    "B": "PG",
    "C": "GA",
    "D": "TD",
}


def add_panel_label(ax, label, fontsize=12):
    """Add bold panel label (1), (2), etc. in upper-left corner."""
    ax.text(-0.12, 1.08, f'({label})', transform=ax.transAxes,
            fontsize=fontsize, fontweight='bold', va='top', ha='left')


def add_events(ax, label_above=True):
    """Add vertical event lines with labels at bottom-right (matching Figure 1)."""
    ylim = ax.get_ylim()
    # Extend y-axis downward to make room for labels
    y_range = ylim[1] - ylim[0]
    new_ylim = (ylim[0] - 0.15 * y_range, ylim[1])
    ax.set_ylim(new_ylim)

    for key, ts in EVENTS_CHRONO.items():
        # Thicker, more visible lines
        ax.axvline(ts, color=EVENT_COLOR, linestyle="--",
                   alpha=0.6, linewidth=1.5, zorder=1)

        # Label at BOTTOM, to the RIGHT of vertical line (matching Figure 1)
        if label_above:
            label = SHORT_EVENT_LABELS.get(key, key)
            ax.annotate(label, xy=(ts, new_ylim[0]), xytext=(EVENT_LABEL_OFFSET_X, 2),
                       textcoords='offset points', ha='left', va='bottom',
                       fontsize=9, fontweight='bold', color=EVENT_COLOR,
                       annotation_clip=False)


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

    # Create 4x4 grid for 7 panels (text panel removed)
    # Rows 0-2: 2 panels each, Row 3: 1 panel centered
    fig = plt.figure(figsize=(14, 16), constrained_layout=True)
    gs = fig.add_gridspec(4, 4, height_ratios=[1, 1, 1, 1], hspace=0.1, wspace=0.1)

    axes = [
        fig.add_subplot(gs[0, 0:2]),  # Panel 1
        fig.add_subplot(gs[0, 2:4]),  # Panel 2
        fig.add_subplot(gs[1, 0:2]),  # Panel 3
        fig.add_subplot(gs[1, 2:4]),  # Panel 4
        fig.add_subplot(gs[2, 0:2]),  # Panel 5
        fig.add_subplot(gs[2, 2:4]),  # Panel 6
        fig.add_subplot(gs[3, 1:3]),  # Panel 7 (centered)
    ]

    # =========================================================================
    # Panel 1: Mean Toxicity (Voat vs Reddit)
    # =========================================================================
    plot_lines(
        axes[0],
        monthly,
        [
            ("Reddit", "toxicity_mean_reddit"),
            ("Voat", "toxicity_mean_voat"),
        ],
        "Mean Toxicity (Voat vs Reddit)",
    )
    maybe_band(axes[0], monthly, "toxicity_mean")

    # =========================================================================
    # Panel 2: Mean Reputation (with 4.5 sustainability threshold)
    # =========================================================================
    plot_lines(
        axes[1],
        monthly,
        [
            ("Reddit", "reputation_mean_reddit"),
            ("Voat", "reputation_mean_voat"),
        ],
        "Mean Reputation",
    )
    # Add 4.5 sustainability threshold line
    axes[1].axhline(4.5, color='#D62728', linestyle='--', linewidth=1.5,
                    alpha=0.7, label='Threshold (4.5)', zorder=2)

    # =========================================================================
    # Panel 3: Mean Degree
    # =========================================================================
    plot_lines(
        axes[2],
        monthly,
        [
            ("Reddit", "mean_degree_reddit"),
            ("Voat", "mean_degree_voat"),
        ],
        "Mean Degree",
    )

    # =========================================================================
    # Panel 4: Active Users (Reddit) - log scale
    # =========================================================================
    if "active_users_reddit" in monthly.columns:
        raw_data = monthly["active_users_reddit"]
        rolling_data = raw_data.rolling(window=3, center=True, min_periods=1).mean()
        axes[3].plot(monthly["month_dt"], raw_data, color=REDDIT_COLOR, linewidth=1, alpha=0.3)
        axes[3].plot(monthly["month_dt"], rolling_data, color=REDDIT_COLOR, linewidth=2.5, label="Reddit (3-mo avg)")
        axes[3].set_yscale("log")
    axes[3].set_title("Active Users (Reddit)")
    axes[3].legend(loc="upper right", fontsize=8)
    add_events(axes[3])

    # =========================================================================
    # Panel 5: Active Users (Voat)
    # =========================================================================
    if "active_users_voat" in monthly.columns:
        raw_data = monthly["active_users_voat"]
        rolling_data = raw_data.rolling(window=3, center=True, min_periods=1).mean()
        axes[4].plot(monthly["month_dt"], raw_data, color=VOAT_COLOR, linewidth=1, alpha=0.3)
        axes[4].plot(monthly["month_dt"], rolling_data, color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
    axes[4].set_title("Active Users (Voat)")
    axes[4].legend(loc="upper right", fontsize=8)
    add_events(axes[4])

    # =========================================================================
    # Panel 6: Degree Assortativity
    # =========================================================================
    plot_lines(
        axes[5],
        monthly,
        [
            ("Reddit", "degree_assortativity_reddit"),
            ("Voat", "degree_assortativity_voat"),
        ],
        "Degree Assortativity",
    )
    axes[5].axhline(0, color="k", linestyle="-", linewidth=0.5, alpha=0.3)

    # =========================================================================
    # Panel 7: E-I Index (Voat only)
    # =========================================================================
    if "ei_index" in monthly.columns:
        raw_data = monthly["ei_index"]
        rolling_data = raw_data.rolling(window=3, center=True, min_periods=1).mean()
        axes[6].plot(monthly["month_dt"], raw_data, color=VOAT_COLOR, linewidth=1, alpha=0.3)
        axes[6].plot(monthly["month_dt"], rolling_data, color=VOAT_COLOR, linewidth=2.5, label="Voat E-I (3-mo avg)")
    axes[6].set_title("E-I Index (Voat)")
    axes[6].axhline(0, color="k", linestyle="-", linewidth=0.5, alpha=0.3)
    axes[6].legend(loc="upper right", fontsize=8)
    add_events(axes[6])

    # =========================================================================
    # Add panel labels (1)-(7)
    # =========================================================================
    for i, ax in enumerate(axes):
        add_panel_label(ax, i + 1)

    # =========================================================================
    # Legends and formatting
    # =========================================================================
    for ax in axes:
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc="best", fontsize=8, frameon=True,
                     facecolor='white', edgecolor='none', framealpha=0.8)

    # X-labels on bottom row panels
    axes[6].set_xlabel("Month")

    # =========================================================================
    # Save - publication quality (300 DPI + PDF)
    # =========================================================================
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # PNG at 300 DPI
    out_path = args.output_dir / f"{args.community}_overview.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight",
                facecolor='white', edgecolor='none')
    print(f"Wrote {out_path}")

    # PDF for vector quality
    out_path_pdf = args.output_dir / f"{args.community}_overview.pdf"
    plt.savefig(out_path_pdf, bbox_inches="tight",
                facecolor='white', edgecolor='none')
    print(f"Wrote {out_path_pdf}")


if __name__ == "__main__":
    main()
