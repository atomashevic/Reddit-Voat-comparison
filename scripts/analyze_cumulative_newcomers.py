#!/usr/bin/env python3
"""Analyze cumulative newcomer dynamics over three periods:
1. A -> B (2015-06 to 2018-09)
2. B -> C (2018-09 to 2020-06)
3. C -> End (2020-06 to 2020-12)

Computes aggregated metrics for Newcomers vs Existing users in each period.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Add scripts dir to path to import utils
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--basic-dir", type=Path, required=True)
    parser.add_argument("--networks-dir", type=Path, help="Unused but kept for compat")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    
    # Load monthly newcomer analysis (intermediate result)
    # Or re-aggregate from user metrics? Re-aggregating is better for cumulative means.
    
    metrics_path = args.basic_dir / "voat" / "results" / f"voat_{args.community}_user_month_metrics.parquet"
    labels_path = args.basic_dir / "voat" / "results" / f"voat_{args.community}_newcomer_labels.csv"
    
    if not labels_path.exists() and args.output_dir:
         labels_path = args.output_dir / f"voat_{args.community}_newcomer_labels.csv"

    if not metrics_path.exists() or not labels_path.exists():
        logging.error("Missing input files")
        return

    metrics = pd.read_parquet(metrics_path)
    labels_df = pd.read_csv(labels_path)
    
    metrics["user_id"] = metrics["user_id"].astype(str)
    labels_df["user_id"] = labels_df["user_id"].astype(str)
    
    merged = metrics.merge(labels_df, on="user_id", how="inner")
    merged["month_dt"] = pd.to_datetime(merged["month"] + "-01")
    
    # Define Periods
    periods = [
        ("A-B", EVENTS["A"], EVENTS["B"]),
        ("B-C", EVENTS["B"], EVENTS["C"]),
        ("C-End", EVENTS["C"], pd.Timestamp("2021-01-01"))
    ]
    
    results = []
    
    for name, start, end in periods:
        subset = merged[(merged["month_dt"] >= start) & (merged["month_dt"] < end)]
        
        if subset.empty:
            continue
            
        # Group by Label
        agg = subset.groupby("label").agg({
            "mean_toxicity": "mean",
            "mean_vader": "mean",
            "mean_textblob": "mean",
            "mean_subjectivity": "mean",
            "mean_reputation": "mean",
            "user_id": "nunique" # Unique users active in period
        })
        
        for label in ["newcomer", "existing"]:
            if label in agg.index:
                row = agg.loc[label].to_dict()
                row["period"] = name
                row["group"] = label
                results.append(row)
            else:
                # Fill gaps
                results.append({
                    "period": name, "group": label, "user_id": 0,
                    "mean_toxicity": float("nan")
                })
                
    df = pd.DataFrame(results)
    
    output_dir = args.output_dir if args.output_dir else args.basic_dir / "voat" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"voat_{args.community}_cumulative_newcomer_analysis.csv"
    df.to_csv(out_path, index=False)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()

