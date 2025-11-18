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
    
    path = args.basic_dir / "voat" / "results" / f"voat_{args.community}_monthly_newcomer_analysis.csv"
    
    if not path.exists():
        logging.error(f"Input not found: {path}")
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
    
    fig, axes = plt.subplots(len(metrics) + 1, 1, figsize=(10, 12), sharex=True)
    
    # Plot behavioral
    for i, (base_metric, label) in enumerate(metrics):
        ax = axes[i]
        cols = [f"{base_metric}_newcomer", f"{base_metric}_existing"]
        if all(c in df.columns for c in cols):
            ax.plot(df["month_dt"], df[cols[0]], label="Newcomer")
            ax.plot(df["month_dt"], df[cols[1]], label="Existing")
            ax.set_title(label)
            ax.legend()
            
    # Plot Network Partition Metrics (Modularity/Assortativity)
    ax = axes[-1]
    if "modularity" in df.columns:
        ax.plot(df["month_dt"], df["modularity"], label="Modularity", color="green")
    if "assortativity" in df.columns:
        ax.plot(df["month_dt"], df["assortativity"], label="Assortativity", color="purple")
    ax.set_title("Network Partition (Newcomer vs Existing)")
    ax.legend()
    
    plt.tight_layout()
    
    output_dir = args.output_dir if args.output_dir else args.basic_dir.parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"{args.community}_monthly_newcomer_dynamics.png"
    plt.savefig(out_path)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()

