#!/usr/bin/env python3
"""Plot cumulative newcomer analysis (bar charts for 3 periods)."""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--basic-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    
    path = args.basic_dir / "voat" / "results" / f"voat_{args.community}_cumulative_newcomer_analysis.csv"
    if not path.exists():
        logging.error(f"Input not found: {path}")
        return
        
    df = pd.read_csv(path)
    
    # Plotting
    metrics = ["mean_toxicity", "mean_vader", "mean_reputation"]
    available = [m for m in metrics if m in df.columns]
    
    fig, axes = plt.subplots(1, len(available), figsize=(15, 5))
    if len(available) == 1: axes = [axes]
    
    for ax, metric in zip(axes, available):
        sns.barplot(data=df, x="period", y=metric, hue="group", ax=ax)
        ax.set_title(metric)
        
    plt.tight_layout()
    
    output_dir = args.output_dir if args.output_dir else args.basic_dir.parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"{args.community}_cumulative_newcomer_periods.png"
    plt.savefig(out_path)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()

