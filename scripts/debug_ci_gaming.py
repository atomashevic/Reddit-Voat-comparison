#!/usr/bin/env python3
"""Dump intermediate values for the gaming time-series CI computation."""

from pathlib import Path

import pandas as pd

from reddit_voat_timeseries_panels import (
    _core_size_confidence_interval,
    load_reddit_core_metrics,
    load_voat_core_metrics,
)

CP_DIR = Path("results/core-periphery")
DATA_DIR = Path("data")
REPUTATION_DIR = Path("results/reputation")

COMMUNITY = "gaming"

reddit_df = load_reddit_core_metrics(COMMUNITY, CP_DIR)
voat_df = load_voat_core_metrics(COMMUNITY, CP_DIR, DATA_DIR)

# Merge reputation to align with plotting logic
rep_reddit = pd.read_csv(REPUTATION_DIR / "reddit" / "results" / f"reddit_{COMMUNITY}_cp_monthly_reputation.csv")
reddit_df = reddit_df.merge(rep_reddit[["month", "core_mean_rep_active"]], on="month", how="left")

print("Reddit core metrics (head):")
print(reddit_df.head())
print()

print("Voat core metrics (head):")
print(voat_df.head())
print()

for platform, df in (("reddit", reddit_df), ("voat", voat_df)):
    print(f"=== {platform.upper()} TOXICITY CI ===")
    sub = df.dropna(subset=["mean_toxicity_per_user"]).sort_values("month_dt").copy()
    count_col = next((c for c in ("member_count", "core_size_block") if c in sub.columns), None)
    print("Using count column:", count_col)
    ci = _core_size_confidence_interval(sub["mean_toxicity_per_user"], sub[count_col])
    dump = sub[["month", "mean_toxicity_per_user", count_col]].copy()
    dump["ci_lower"] = ci["ci_lower"]
    dump["ci_upper"] = ci["ci_upper"]
    print(dump.head(15))
    print()
