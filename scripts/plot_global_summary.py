#!/usr/bin/env python3
"""Plot global aggregate summary (Voat) across all communities.

3 Panels:
1. E-I Index (with Toxicity overlay)
2. Degree Assortativity
3. Mean Degree
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.dates as mdates

# Ensure repository root on path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS, EVENT_LABELS

# Style
VOAT_COLOR = "#800080"  # Purple
TOXICITY_COLOR = "#D62728"  # Red
EVENT_COLOR = "#333333"
EVENT_ALPHA = 0.15


def add_events_band(ax):
    """Add vertical bands for events."""
    ylim = ax.get_ylim()
    for key, date in EVENTS.items():
        # Draw line
        ax.axvline(date, color=EVENT_COLOR, linestyle="--", alpha=0.3, linewidth=1)
        # Add label at top
        label = EVENT_LABELS.get(key, key)
        ax.text(date, ylim[1], label, ha="center", va="bottom", fontsize=8, color=EVENT_COLOR, rotation=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", type=Path, required=True, help="Global aggregate CSV")
    parser.add_argument("--output-dir", type=Path, default=Path("figures/global"))
    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"Input file not found: {args.input_file}")
        sys.exit(1)

    df = pd.read_csv(args.input_file)
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    df = df.sort_values("month_dt")

    fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
    
    # 1. E-I Index
    ax1 = axes[0]
    if "ei_index" in df.columns:
        ax1.plot(df["month_dt"], df["ei_index"], color=VOAT_COLOR, linewidth=2, label="E-I Index")
        ax1.set_ylabel("E-I Index", color=VOAT_COLOR, fontweight="bold")
        ax1.tick_params(axis="y", labelcolor=VOAT_COLOR)
    
    ax1.set_title("E-I Index (Voat Aggregate)\nLower = Inward, Higher = Outward Mixing")
    
    # Toxicity Overlay
    if "toxicity_mean_voat" in df.columns:
        ax1b = ax1.twinx()
        ax1b.plot(df["month_dt"], df["toxicity_mean_voat"], color=TOXICITY_COLOR, linestyle="--", linewidth=1, alpha=0.8, label="Toxicity")
        ax1b.set_ylabel("Mean Toxicity", color=TOXICITY_COLOR)
        ax1b.tick_params(axis="y", labelcolor=TOXICITY_COLOR)
        
        # Combined legend?
        # lines, labels = ax1.get_legend_handles_labels()
        # lines2, labels2 = ax1b.get_legend_handles_labels()
        # ax1.legend(lines + lines2, labels + labels2, loc="upper left")

    add_events_band(ax1)

    # 2. Assortativity
    ax2 = axes[1]
    if "degree_assortativity_voat" in df.columns:
        ax2.plot(df["month_dt"], df["degree_assortativity_voat"], color=VOAT_COLOR, linewidth=2)
    ax2.set_ylabel("Assortativity", color=VOAT_COLOR, fontweight="bold")
    ax2.set_title("Degree Assortativity (Hub-Hub Mixing)")
    ax2.axhline(0, color="k", linestyle="-", linewidth=0.5, alpha=0.3)
    add_events_band(ax2)

    # 3. Mean Degree
    ax3 = axes[2]
    if "mean_degree_voat" in df.columns:
        ax3.plot(df["month_dt"], df["mean_degree_voat"], color=VOAT_COLOR, linewidth=2)
    ax3.set_ylabel("Mean Degree", color=VOAT_COLOR, fontweight="bold")
    ax3.set_title("Mean Degree (Cohesion/Intensity)")
    add_events_band(ax3)
    
    # Format X axis
    ax3.set_xlabel("Month")
    ax3.xaxis.set_major_locator(mdates.YearLocator())
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    plt.tight_layout()
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / "voat_global_summary.png"
    plt.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

