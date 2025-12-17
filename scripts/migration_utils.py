"""Shared utilities for migration and alternative pipeline analysis.

Defines key event dates, metrics, and helper functions for loading data.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Key Migration / Platform Events
# A: FPH Ban (2015-06)
# B: Pizzagate Ban (2016-11)
# C: GreatAwakening Ban (2018-09)
# D: The_Donald Ban (2020-06)
EVENTS = {
    "A": pd.Timestamp("2015-06-10"),
    "B": pd.Timestamp("2016-11-23"),
    "C": pd.Timestamp("2018-09-12"),
    "D": pd.Timestamp("2020-06-29"),
}

EVENT_LABELS = {
    "A": "FPH Ban",
    "B": "Pizzagate Ban",
    "C": "GA Ban",
    "D": "TD Ban",
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
    filename = f"{platform}_{community}_monthly_aggregates.csv"
    candidates = [
        base_dir / platform / "results" / filename,     # canonical basic layout
        base_dir / platform / filename,                 # alternative pipeline layout (flattened)
        Path("results/basic") / platform / "results" / filename,  # global basic fallback
    ]

    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise FileNotFoundError(f"Monthly aggregates not found in: {candidates}")

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


def newcomer_label_for_month(first_seen: pd.Timestamp, month_dt: pd.Timestamp) -> str:
    """Assign newcomer/existing label for a given month, based on first_seen and event periods.

    Rules:
      - pre-A months: everyone is existing
      - Month in [A, B): newcomer iff first_seen >= A
      - Month in [B, C): newcomer iff first_seen >= B
      - Month >= C: newcomer iff first_seen >= C
    """
    if month_dt < EVENTS["A"]:
        return "existing"
    if EVENTS["A"] <= month_dt < EVENTS["B"]:
        return "newcomer" if first_seen >= EVENTS["A"] else "existing"
    if EVENTS["B"] <= month_dt < EVENTS["C"]:
        return "newcomer" if first_seen >= EVENTS["B"] else "existing"
    return "newcomer" if first_seen >= EVENTS["C"] else "existing"
