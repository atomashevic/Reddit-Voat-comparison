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
    df_local = df.reset_index(drop=True)
    sns.lineplot(data=df_local, x="month_dt", y=metric, hue="platform", ax=ax)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")
    
    # Add event lines
    for key, date in EVENTS.items():
        ax.axvline(date, color="r", linestyle="--", alpha=0.5)
        # Only label on top plots or handled globally?
        # ax.text(date, ax.get_ylim()[1], key, ha="center", va="bottom", color="r")
    return ax


def maybe_add_bootstrap_band(ax, bootstrap_df, metric):
    """Overlay bootstrap percentile band (5-95) and median if available."""
    if bootstrap_df is None or metric == "reputation_mean":
        return  # skip reputation bands
    subset = bootstrap_df[bootstrap_df["metric"] == metric]
    if subset.empty:
        return
    # reshape percentiles
    pivot = subset.pivot_table(index="month", columns="percentile", values="value")
    for col in pivot.columns:
        pivot[col] = pd.to_numeric(pivot[col], errors="coerce")
    pivot = pivot.reset_index()
    pivot["month_dt"] = pd.to_datetime(pivot["month"] + "-01")

    if {5, 95}.issubset(pivot.columns):
        ax.fill_between(pivot["month_dt"], pivot[5], pivot[95],
                        color="gray", alpha=0.2, label="Bootstrap 5-95% (reddit@Voat scale)")
    if 50 in pivot.columns:
        ax.plot(pivot["month_dt"], pivot[50], color="gray", linestyle="--", label="Bootstrap median")

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    
    base_dir = args.compare_dir.parent
    bootstrap_path = args.compare_dir / f"{args.community}_global_bootstrap_summary.csv"
    bootstrap_df = None
    if bootstrap_path.exists():
        bootstrap_df = pd.read_csv(bootstrap_path)
        bootstrap_df["month"] = bootstrap_df["month"].astype(str)
    else:
        logging.warning(f"Bootstrap summary not found (skipping bands): {bootstrap_path}")
    
    try:
        reddit_df = load_monthly_aggregates(base_dir, "reddit", args.community)
        voat_df = load_monthly_aggregates(base_dir, "voat", args.community)
        combined = pd.concat([reddit_df, voat_df])
    except FileNotFoundError as e:
        logging.error(e)
        return

    # Compute normalized clustering if available components exist
    for df in (reddit_df, voat_df):
        if "mean_clustering" in df.columns and "er_expected_clustering" in df.columns:
            df["normalized_clustering"] = df["mean_clustering"] / df["er_expected_clustering"]

    metrics = [
        ("toxicity_mean", "Mean Toxicity", "Toxicity Score"),
        ("vader_mean", "Mean Sentiment (VADER)", "Compound Score"),
        ("reputation_mean", "Mean Reputation", "Reputation"),
        ("normalized_clustering", "Normalized Clustering", "Clustering / ER expectation"),
        ("mean_degree", "Mean Degree", "Degree"),
        ("degree_assortativity", "Assortativity", "Degree assortativity"),
    ]
    
    # Filter metrics present in data
    # Active users on comparable scales: compute reputation-active (rep > 1) if available
    if "rep_active_users" in combined.columns:
        combined["active_reddit"] = combined.apply(lambda row: row["rep_active_users"] if row["platform"] == "reddit" else float("nan"), axis=1)
        combined["active_voat"] = combined.apply(lambda row: row["rep_active_users"] if row["platform"] == "voat" else float("nan"), axis=1)
        metrics.append(("active_reddit", "Active Users (rep>1) Reddit", "Count"))
        metrics.append(("active_voat", "Active Users (rep>1) Voat", "Count"))

    available_metrics = [m for m in metrics if m[0] in combined.columns]
    
    n_metrics = len(available_metrics)
    n_cols = 2
    n_rows = (n_metrics + 1) // 2
    
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(12, 4 * n_rows), sharex=True)
    axes = axes.flatten()
    
    handles_labels = None
    for i, (col, title, ylabel) in enumerate(available_metrics):
        ax = plot_metric(axes[i], combined, col, title, ylabel)
        maybe_add_bootstrap_band(ax, bootstrap_df, col)
        # capture legend handles from first axis
        if handles_labels is None:
            handles_labels = ax.get_legend_handles_labels()
        if ax.get_legend():
            ax.get_legend().remove()

    if handles_labels:
        handles, labels = handles_labels
        fig.legend(handles, labels, loc='upper center', ncol=2)
        
    plt.tight_layout()
    plt.subplots_adjust(top=0.95)
    
    output_dir = args.output_dir if args.output_dir else args.compare_dir.parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"{args.community}_global_comparison_panels.png"
    plt.savefig(out_path, dpi=150)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
