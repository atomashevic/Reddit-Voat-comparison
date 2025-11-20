#!/usr/bin/env python3
"""Plot Voat Newcomer Dynamics (Newcomer vs Existing).

Visualizes monthly evolution of behavior and network metrics for the two groups.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

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

    filename = f"voat_{args.community}_monthly_newcomer_analysis.csv"
    candidates = [
        args.basic_dir / args.community / "voat" / filename,              # alt layout
        args.basic_dir / args.community / "voat" / "results" / filename,  # alt with results/
        args.basic_dir / "voat" / "results" / filename,                  # canonical basic
        args.basic_dir / "voat" / filename,                              # flattened alt
        Path("results/basic") / "voat" / "results" / filename,           # basic fallback
    ]

    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        logging.error(f"Input not found. Tried: {candidates}")
        return
        
    df = pd.read_csv(path)
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    
    # Unpivot behavioral metrics for hue plotting
    # Columns are like mean_toxicity_newcomer, mean_toxicity_existing
    
    metrics = [
        ("mean_toxicity", "Toxicity"),
        ("mean_vader", "Sentiment"),
        ("mean_reputation", "Reputation")
    ]
    
    fig, axes = plt.subplots(len(metrics) + 2, 1, figsize=(10, 14), sharex=True)
    
    # Plot behavioral
    for i, (base_metric, label) in enumerate(metrics):
        ax = axes[i]
        cols = [f"{base_metric}_newcomer", f"{base_metric}_existing"]
        if all(c in df.columns for c in cols):
            ax.plot(df["month_dt"], df[cols[0]], label="Newcomer")
            ax.plot(df["month_dt"], df[cols[1]], label="Existing")
            ax.set_title(label)
            ax.legend()
            # Shade migration periods for clarity
            event_dates = list(EVENTS.values())
            periods = [
                (None, event_dates[0], "Pre-A"),
                (event_dates[0], event_dates[1], "A-B"),
                (event_dates[1], event_dates[2], "B-C"),
                (event_dates[2], df["month_dt"].max(), "C-End"),
            ]
            for start, end, label_period in periods:
                if start is None:
                    start = df["month_dt"].min()
                if end is None:
                    end = df["month_dt"].max()
                ax.axvspan(start, end, alpha=0.05, color="gray")
                ax.text((start + (end - start) / 2), ax.get_ylim()[1],
                        label_period, ha="center", va="top", fontsize=8, color="gray")
            
    # Plot group sizes over time
    size_ax = axes[-2]
    if "user_id_newcomer" in df.columns and "user_id_existing" in df.columns:
        size_ax.plot(df["month_dt"], df["user_id_newcomer"], label="Newcomer count", color="teal")
        size_ax.plot(df["month_dt"], df["user_id_existing"], label="Existing count", color="gray")
        size_ax.set_title("Group Sizes")
        size_ax.legend()

    # Plot Network Partition Metric (Assortativity/EI)
    ax = axes[-1]
    if "assortativity" in df.columns:
        ax.plot(df["month_dt"], df["assortativity"], label="Assortativity", color="purple")
    if "ei_index" in df.columns:
        ax.plot(df["month_dt"], df["ei_index"], label="E-I Index", color="orange")
    ax.set_title("Network Partition (Assortativity)")
    ax.legend()
    
    plt.tight_layout()
    
    output_dir = args.output_dir if args.output_dir else args.basic_dir.parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"{args.community}_monthly_newcomer_dynamics.png"
    plt.savefig(out_path)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
