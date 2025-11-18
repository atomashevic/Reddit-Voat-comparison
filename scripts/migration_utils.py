"""Shared utilities for migration and alternative pipeline analysis.

Defines key event dates, metrics, and helper functions for loading data.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Key Migration Events
# A: FPH Ban (2015-06)
# B: GreatAwakening Ban (2018-09)
# C: The_Donald Ban (2020-06)
EVENTS = {
    "A": pd.Timestamp("2015-06-10"),
    "B": pd.Timestamp("2018-09-12"),
    "C": pd.Timestamp("2020-06-29"),
}

EVENT_LABELS = {
    "A": "FPH Ban",
    "B": "GA Ban",
    "C": "TD Ban",
}

# Standard Metrics
METRICS = [
    "toxicity_mean",
    "vader_mean",
    "textblob_mean",
    "subjectivity_mean",
    "reputation_mean",
    "mean_clustering",
    "mean_degree",
]

def load_monthly_aggregates(
    base_dir: Path, platform: str, community: str
) -> pd.DataFrame:
    """Load aggregated monthly metrics for a community."""
    path = base_dir / platform / "results" / f"{platform}_{community}_monthly_aggregates.csv"
    if not path.exists():
        # Fallback to basic results if alternative missing
        fallback = Path("results/basic") / platform / "results" / path.name
        if fallback.exists():
            path = fallback
        else:
            raise FileNotFoundError(f"Monthly aggregates not found: {path}")
    
    df = pd.read_csv(path)
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    df["platform"] = platform
    return df.sort_values("month_dt")

def get_event_window(
    df: pd.DataFrame, event_date: pd.Timestamp, window_months: int = 3
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Extract pre/post windows around an event."""
    start_date = event_date - pd.DateOffset(months=window_months)
    end_date = event_date + pd.DateOffset(months=window_months)
    
    window = df[(df["month_dt"] >= start_date) & (df["month_dt"] <= end_date)].copy()
    
    pre = window[window["month_dt"] < event_date]
    post = window[window["month_dt"] >= event_date]
    
    return pre, post

