#!/usr/bin/env python3
"""Plot global comparison panels (Reddit vs Voat) for key metrics.

Plots time series for toxicity, sentiment, reputation, and network metrics.
Includes event markers.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Add scripts dir to path to import utils
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS, EVENT_LABELS, load_monthly_aggregates

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--compare-dir", type=Path, required=True)
    parser.add_argument("--networks-dir", type=Path, help="Unused")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()

def plot_metric(ax, df, metric, title, ylabel):
    sns.lineplot(data=df, x="month_dt", y=metric, hue="platform", ax=ax)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")
    
    # Add event lines
    for key, date in EVENTS.items():
        ax.axvline(date, color="r", linestyle="--", alpha=0.5)
        # Only label on top plots or handled globally?
        # ax.text(date, ax.get_ylim()[1], key, ha="center", va="bottom", color="r")

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    
    base_dir = args.compare_dir.parent
    
    try:
        reddit_df = load_monthly_aggregates(base_dir, "reddit", args.community)
        voat_df = load_monthly_aggregates(base_dir, "voat", args.community)
        combined = pd.concat([reddit_df, voat_df])
    except FileNotFoundError as e:
        logging.error(e)
        return

    metrics = [
        ("toxicity_mean", "Mean Toxicity", "Toxicity Score"),
        ("vader_mean", "Mean Sentiment (VADER)", "Compound Score"),
        ("reputation_mean", "Mean Reputation", "Reputation"),
        ("mean_clustering", "Clustering Coefficient", "Clustering"),
        ("mean_degree", "Mean Degree", "Degree"),
        ("active_users", "Active Users", "Count")
    ]
    
    # Filter metrics present in data
    available_metrics = [m for m in metrics if m[0] in combined.columns]
    
    n_metrics = len(available_metrics)
    n_cols = 2
    n_rows = (n_metrics + 1) // 2
    
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(12, 4 * n_rows), sharex=True)
    axes = axes.flatten()
    
    for i, (col, title, ylabel) in enumerate(available_metrics):
        plot_metric(axes[i], combined, col, title, ylabel)
        
    # Legend only on first plot
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=2)
    
    for ax in axes:
        ax.get_legend().remove()
        
    plt.tight_layout()
    plt.subplots_adjust(top=0.95)
    
    output_dir = args.output_dir if args.output_dir else args.compare_dir.parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"{args.community}_global_comparison_panels.png"
    plt.savefig(out_path, dpi=150)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()

