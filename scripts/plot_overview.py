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


def add_events(ax):
    for key, ts in EVENTS.items():
        ax.axvline(ts, color="k", linestyle="--", alpha=0.4, linewidth=1)
        label = EVENT_LABELS.get(key, key)
        ax.text(ts, ax.get_ylim()[1], label, ha="center", va="bottom", fontsize=8, color="k")


def maybe_band(ax, df, col_base):
    lower = f"{col_base}_p5"
    upper = f"{col_base}_p95"
    if lower in df.columns and upper in df.columns:
        ax.fill_between(df["month_dt"], df[lower], df[upper], color="gray", alpha=0.15, label="Bootstrap 5-95%")


def plot_lines(ax, df, columns, title, ylabel=None):
    for label, col in columns:
        if col not in df.columns:
            continue
        ax.plot(df["month_dt"], df[col], label=label)
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
    args = parser.parse_args()

    monthly = pd.read_csv(args.monthly_file)
    monthly["month_dt"] = pd.to_datetime(monthly["month"] + "-01")

    fig, axes = plt.subplots(4, 2, figsize=(14, 16), sharex=True)
    axes = axes.flatten()

    # 1. Mean toxicity with bands
    plot_lines(
        axes[0],
        monthly,
        [
            ("Toxicity Reddit", "toxicity_mean_reddit"),
            ("Toxicity Voat", "toxicity_mean_voat"),
        ],
        "Mean Toxicity",
    )
    maybe_band(axes[0], monthly, "toxicity_mean")

    # 2. Mean sentiment (VADER) with bands
    plot_lines(
        axes[1],
        monthly,
        [
            ("Sentiment Reddit", "vader_mean_reddit"),
            ("Sentiment Voat", "vader_mean_voat"),
        ],
        "Mean Sentiment (VADER)",
    )
    maybe_band(axes[1], monthly, "vader_mean")

    # 3. Mean reputation
    plot_lines(
        axes[2],
        monthly,
        [
            ("Reputation Reddit", "reputation_mean_reddit"),
            ("Reputation Voat", "reputation_mean_voat"),
        ],
        "Mean Reputation",
    )

    # 4. Mean degree
    plot_lines(
        axes[3],
        monthly,
        [
            ("Degree Reddit", "mean_degree_reddit"),
            ("Degree Voat", "mean_degree_voat"),
        ],
        "Mean Degree",
    )

    # 5. Active users (Reddit)
    plot_lines(
        axes[4],
        monthly,
        [("Active Users Reddit", "rep_active_users_reddit")],
        "Active Users (Reputation-active) Reddit",
    )

    # 6. Active users (Voat)
    plot_lines(
        axes[5],
        monthly,
        [("Active Users Voat", "rep_active_users_voat")],
        "Active Users (Reputation-active) Voat",
    )

    # 7. Degree assortativity
    plot_lines(
        axes[6],
        monthly,
        [
            ("Assortativity Reddit", "degree_assortativity_reddit"),
            ("Assortativity Voat", "degree_assortativity_voat"),
        ],
        "Degree Assortativity",
    )

    # 8. Clustering Coefficient (Replacing E-I)
    plot_lines(
        axes[7],
        monthly,
        [
            ("Clustering Reddit", "mean_clustering_reddit"),
            ("Clustering Voat", "mean_clustering_voat"),
        ],
        "Mean Clustering Coefficient",
    )

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
