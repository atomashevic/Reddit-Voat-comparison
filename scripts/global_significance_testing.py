#!/usr/bin/env python3
"""Perform statistical significance testing on Global Metrics.

Compares Reddit vs Voat monthly time series using:
1. Mann-Whitney U test (global distribution difference)
2. T-test (mean difference)
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from scipy import stats

# Add scripts dir to path to import utils
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import METRICS, load_monthly_aggregates

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--compare-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    
    base_dir = args.compare_dir.parent
    
    try:
        reddit_df = load_monthly_aggregates(base_dir, "reddit", args.community)
        voat_df = load_monthly_aggregates(base_dir, "voat", args.community)
    except FileNotFoundError as e:
        logging.error(e)
        return

    # Align dates? Or just compare distributions?
    # For global comparison, we usually compare the overlapping period or the whole period
    # distribution to see if they differ systematically.
    
    results = []
    
    for metric in METRICS:
        if metric not in reddit_df.columns or metric not in voat_df.columns:
            continue
            
        r_vals = reddit_df[metric].dropna()
        v_vals = voat_df[metric].dropna()
        
        if len(r_vals) < 3 or len(v_vals) < 3:
            continue
            
        # Mann-Whitney U
        try:
            u_stat, u_p = stats.mannwhitneyu(r_vals, v_vals, alternative='two-sided')
        except Exception:
            u_stat, u_p = float('nan'), float('nan')
            
        # T-test
        try:
            t_stat, t_p = stats.ttest_ind(r_vals, v_vals, equal_var=False)
        except Exception:
            t_stat, t_p = float('nan'), float('nan')
            
        results.append({
            "community": args.community,
            "metric": metric,
            "reddit_n": len(r_vals),
            "voat_n": len(v_vals),
            "reddit_mean": r_vals.mean(),
            "voat_mean": v_vals.mean(),
            "mw_stat": u_stat,
            "mw_p": u_p,
            "ttest_stat": t_stat,
            "ttest_p": t_p,
            "significant": u_p < 0.05
        })
        
    df = pd.DataFrame(results)
    
    output_dir = args.output_dir if args.output_dir else args.compare_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"{args.community}_global_significance_summary.csv"
    df.to_csv(out_path, index=False)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()

