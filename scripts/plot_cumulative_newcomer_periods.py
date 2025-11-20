#!/usr/bin/env python3
"""Plot cumulative newcomer analysis (bar charts for 3 periods)."""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Allow importing shared utils when run as script
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--basic-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    
    # Load user-month metrics and labels to compute means + CIs
    metrics_file = None
    labels_file = None
    metrics_name = f"voat_{args.community}_user_month_metrics.parquet"
    labels_name = f"voat_{args.community}_newcomer_labels.csv"
    metric_candidates = [
        args.basic_dir / args.community / "voat" / metrics_name,
        args.basic_dir / args.community / "voat" / "results" / metrics_name,
        args.basic_dir / "voat" / "results" / metrics_name,
        args.basic_dir / "voat" / metrics_name,
        Path("results/basic") / "voat" / "results" / metrics_name,
    ]
    label_candidates = [
        args.basic_dir / args.community / "voat" / labels_name,
        args.basic_dir / args.community / "voat" / "results" / labels_name,
        args.basic_dir / "voat" / "results" / labels_name,
        args.basic_dir / "voat" / labels_name,
    ]
    metrics_file = next((p for p in metric_candidates if p.exists()), None)
    labels_file = next((p for p in label_candidates if p.exists()), None)

    if metrics_file is None or labels_file is None:
        logging.error(f"Input not found. Tried metrics: {metric_candidates}, labels: {label_candidates}")
        return

    df = pd.read_parquet(metrics_file)
    labels = pd.read_csv(labels_file)
    df["user_id"] = df["user_id"].astype(str)
    labels["user_id"] = labels["user_id"].astype(str)
    merged = df.merge(labels, on="user_id", how="inner")
    merged["month_dt"] = pd.to_datetime(merged["month"] + "-01")

    periods = [
        ("A-B", EVENTS["A"], EVENTS["B"]),
        ("B-C", EVENTS["B"], EVENTS["C"]),
        ("C-End", EVENTS["C"], pd.Timestamp("2021-01-01")),
    ]

    metrics = ["mean_toxicity", "mean_vader", "mean_reputation", "assortativity"]
    available = [m for m in metrics if m in merged.columns]

    records = []
    for name, start, end in periods:
        window = merged[(merged["month_dt"] >= start) & (merged["month_dt"] < end)]
        if window.empty:
            continue
        for group, sub in window.groupby("label"):
            for metric in available:
                values = pd.to_numeric(sub[metric], errors="coerce").dropna()
                if values.empty:
                    continue
                mean = values.mean()
                sem = values.sem()
                ci = 1.96 * sem if pd.notna(sem) else float("nan")
                records.append({
                    "period": name,
                    "group": group,
                    "metric": metric,
                    "mean": mean,
                    "ci": ci,
                })

    if not records:
        logging.error("No data available for cumulative plots")
        return

    plot_df = pd.DataFrame(records)
    unique_metrics = plot_df["metric"].unique()

    fig, axes = plt.subplots(1, len(unique_metrics), figsize=(5 * len(unique_metrics), 5))
    if len(unique_metrics) == 1:
        axes = [axes]

    period_order = ["A-B", "B-C", "C-End"]
    group_order = ["newcomer", "existing"]

    for ax, metric in zip(axes, unique_metrics):
        subset = plot_df[plot_df["metric"] == metric]
        width = 0.35
        x = range(len(period_order))
        for i, group in enumerate(group_order):
            grp = subset[subset["group"] == group].set_index("period")
            means = [grp.loc[p, "mean"] if p in grp.index else float("nan") for p in period_order]
            cis = [grp.loc[p, "ci"] if p in grp.index else float("nan") for p in period_order]
            positions = [xi + (i - 0.5) * width for xi in x]
            ax.bar(positions, means, width=width, label=group)
            ax.errorbar(positions, means, yerr=cis, fmt="none", ecolor="black", capsize=3, linewidth=1)

        ax.set_xticks(list(x))
        ax.set_xticklabels(period_order)
        ax.set_title(metric)
        ax.legend()

    plt.tight_layout()

    output_dir = args.output_dir if args.output_dir else args.basic_dir.parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / f"{args.community}_cumulative_newcomer_periods.png"
    plt.savefig(out_path)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
