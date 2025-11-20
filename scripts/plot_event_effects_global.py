#!/usr/bin/env python3
"""Plot Event Effects (Jump analysis)."""

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
    parser.add_argument("--compare-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    
    filename = f"{args.community}_global_event_window_summary.csv"
    candidates = [
        args.compare_dir / filename,
        args.compare_dir.parent / "compare" / filename,
        args.compare_dir.parent / filename,
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        logging.error(f"Input not found. Tried: {candidates}")
        return
        
    df = pd.read_csv(path)
    
    # Plot Jumps (Post - Pre)
    # FacetGrid: Row=Metric, Col=Event?
    # Or just Barplot of Jump by Event/Platform per Metric
    
    metrics = df["metric"].unique()
    n_metrics = len(metrics)
    
    fig, axes = plt.subplots(n_metrics, 1, figsize=(8, 4 * n_metrics), sharex=True)
    if n_metrics == 1: axes = [axes]
    
    for ax, metric in zip(axes, metrics):
        subset = df[df["metric"] == metric]
        sns.barplot(data=subset, x="event", y="jump", hue="platform", ax=ax)
        ax.set_title(f"Change in {metric} (Post - Pre)")
        ax.axhline(0, color="black", linewidth=0.5)
        
    plt.tight_layout()
    
    output_dir = args.output_dir if args.output_dir else args.compare_dir.parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"{args.community}_global_event_effects.png"
    plt.savefig(out_path)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
