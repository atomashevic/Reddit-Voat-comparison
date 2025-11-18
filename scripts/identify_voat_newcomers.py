#!/usr/bin/env python3
"""Identify Voat newcomers based on first appearance relative to Event A.

Users whose first activity (post/comment) occurs on or after Event A (June 2015)
are labeled 'newcomer'. Users active before this date are 'existing'.
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
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    
    # Load Voat user metrics
    # We need to load the parquet file directly to get user_id and month
    # The pipeline script passes basic-dir as 'results/alternative' but the file is in 'results/alternative/voat/results'
    # We need to handle the path correctly.
    
    # Construct path: basic_dir / platform / results / ...
    # Note: run_alternative_pipeline passes --basic-dir "results/alternative"
    path = args.basic_dir / "voat" / "results" / f"voat_{args.community}_user_month_metrics.parquet"
    
    if not path.exists():
        logging.error(f"Voat metrics not found: {path}")
        return

    logging.info(f"Loading {path}...")
    df = pd.read_parquet(path, columns=["user_id", "month"])
    
    # Find first month per user
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    first_seen = df.groupby("user_id")["month_dt"].min().reset_index()
    
    # Label based on Event A
    event_a = EVENTS["A"] # June 2015
    
    # Newcomer = First seen >= Event A
    # Existing = First seen < Event A
    first_seen["label"] = first_seen["month_dt"].apply(
        lambda x: "newcomer" if x >= event_a else "existing"
    )
    
    counts = first_seen["label"].value_counts()
    logging.info(f"User labels:\n{counts}")
    
    output_dir = args.output_dir if args.output_dir else args.basic_dir / "voat" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"voat_{args.community}_newcomer_labels.csv"
    first_seen[["user_id", "label"]].to_csv(out_path, index=False)
    logging.info(f"Wrote labels to {out_path}")

if __name__ == "__main__":
    main()

