#!/usr/bin/env python3
"""Compute event-period based toxicity differences for global heatmap.

Computes mean toxicity (entire user base) for Reddit and Voat per community per event period,
then calculates Voat - Reddit difference.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np

# Ensure repository root on path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS

# Communities to analyze
COMMUNITIES = ["funny", "gaming", "technology", "videos", "gifs", "pics"]

# Event periods (in chronological order)
EVENT_PERIODS = {
    "A-D": (EVENTS["A"], EVENTS["D"]),      # FPH to Pizzagate
    "D-B": (EVENTS["D"], EVENTS["B"]),      # Pizzagate to GA
    "B-C": (EVENTS["B"], EVENTS["C"]),      # GA to TD
    "C-end": (EVENTS["C"], pd.Timestamp("2020-12-31")),  # TD to end
}


def load_community_toxicity(results_root: Path, platform: str, community: str) -> pd.DataFrame:
    """Load monthly toxicity data for a community."""
    path = results_root / platform / community / f"{platform}_{community}_monthly_aggregates.csv"
    if not path.exists():
        print(f"Warning: {path} not found")
        return pd.DataFrame()
    
    df = pd.read_csv(path)
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    df["platform"] = platform
    df["community"] = community
    return df[["month_dt", "platform", "community", "toxicity_mean"]].copy()


def assign_period(month_dt: pd.Timestamp) -> str:
    """Assign a month to an event period."""
    for period_name, (start, end) in EVENT_PERIODS.items():
        if start <= month_dt < end:
            return period_name
    return None


def compute_period_differences(results_root: Path) -> pd.DataFrame:
    """Compute toxicity differences by event period and community."""
    all_data = []
    
    for community in COMMUNITIES:
        reddit_df = load_community_toxicity(results_root, "reddit", community)
        voat_df = load_community_toxicity(results_root, "voat", community)
        
        if reddit_df.empty or voat_df.empty:
            continue
        
        combined = pd.concat([reddit_df, voat_df], ignore_index=True)
        all_data.append(combined)
    
    if not all_data:
        print("Error: No data loaded")
        return pd.DataFrame()
    
    full_df = pd.concat(all_data, ignore_index=True)
    
    # Assign periods
    full_df["period"] = full_df["month_dt"].apply(assign_period)
    full_df = full_df[full_df["period"].notna()].copy()
    
    # Compute mean toxicity per platform per community per period
    period_means = full_df.groupby(["community", "platform", "period"])["toxicity_mean"].mean().reset_index()
    
    # Pivot to get Reddit and Voat side by side
    wide = period_means.pivot_table(
        index=["community", "period"],
        columns="platform",
        values="toxicity_mean"
    ).reset_index()
    
    # Compute difference: Voat - Reddit
    wide["toxicity_diff"] = wide["voat"] - wide["reddit"]
    
    return wide[["community", "period", "toxicity_diff"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", type=Path, default=Path("results"))
    parser.add_argument("--output-file", type=Path, default=Path("results/global/event_period_toxicity_diff.csv"))
    args = parser.parse_args()
    
    df = compute_period_differences(args.results_root)
    
    if df.empty:
        print("Error: No results to save")
        sys.exit(1)
    
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output_file, index=False)
    print(f"Wrote {args.output_file}")
    print(f"Shape: {df.shape}")
    print(df.head(10))


if __name__ == "__main__":
    main()


