#!/usr/bin/env python3
"""Compute q75 (75th percentile) toxicity time series from user-level data.

Computes monthly 75th percentile toxicity across all users for each platform,
aggregated across all communities.
"""

import argparse
import gc
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import numpy as np

# Set thread limits to prevent oversubscription
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("ARROW_NUM_THREADS", "1")

# Communities to analyze
COMMUNITIES = ["funny", "gaming", "technology", "videos", "gifs", "pics"]


def compute_monthly_q75(parquet_path: Path) -> pd.DataFrame:
    """Compute monthly 75th percentile toxicity from user-level parquet file."""
    if not parquet_path.exists():
        logging.warning(f"File not found: {parquet_path}")
        return pd.DataFrame()
    
    # Read only needed columns
    table = pq.read_table(parquet_path, columns=["month", "mean_toxicity"], use_threads=False)
    df = table.to_pandas()
    del table
    gc.collect()
    
    # Drop NaN toxicity values
    df = df.dropna(subset=["mean_toxicity"])
    
    if df.empty:
        return pd.DataFrame()
    
    # Compute 75th percentile per month
    q75 = df.groupby("month")["mean_toxicity"].quantile(0.75).reset_index()
    q75.columns = ["month", "toxicity_q75"]
    
    del df
    gc.collect()
    
    return q75


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", type=Path, default=Path("results"))
    parser.add_argument("--output-file", type=Path, default=Path("results/global/q90_toxicity.csv"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    
    all_reddit = []
    all_voat = []
    
    for community in COMMUNITIES:
        logging.info(f"Processing {community}...")
        
        # Reddit
        reddit_path = args.results_root / "reddit" / community / f"reddit_{community}_user_month_metrics.parquet"
        reddit_q75 = compute_monthly_q75(reddit_path)
        if not reddit_q75.empty:
            reddit_q75["community"] = community
            reddit_q75["platform"] = "reddit"
            all_reddit.append(reddit_q75)
        
        # Voat
        voat_path = args.results_root / "voat" / community / f"voat_{community}_user_month_metrics.parquet"
        voat_q75 = compute_monthly_q75(voat_path)
        if not voat_q75.empty:
            voat_q75["community"] = community
            voat_q75["platform"] = "voat"
            all_voat.append(voat_q75)
    
    if not all_reddit and not all_voat:
        logging.error("No data loaded")
        sys.exit(1)
    
    # Combine all communities
    all_data = []
    if all_reddit:
        all_data.extend(all_reddit)
    if all_voat:
        all_data.extend(all_voat)
    
    full_df = pd.concat(all_data, ignore_index=True)
    
    # Aggregate across communities: simple average of q75 per platform per month
    # (weighted average would require user counts which we don't have easily here)
    global_q75 = full_df.groupby(["platform", "month"])["toxicity_q75"].mean().reset_index()
    
    # Pivot to wide format
    wide = global_q75.pivot(index="month", columns="platform", values="toxicity_q75").reset_index()
    wide.columns.name = None
    
    # Ensure month is string
    wide["month"] = wide["month"].astype(str)
    
    # Sort by month
    wide = wide.sort_values("month")
    
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(args.output_file, index=False)
    logging.info(f"Wrote {args.output_file}")
    logging.info(f"Shape: {wide.shape}")
    print(wide.head(10))


if __name__ == "__main__":
    main()

