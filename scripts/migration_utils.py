"""Shared utilities for migration and alternative pipeline analysis.

Defines key event dates, metrics, and helper functions for loading data.
"""

from pathlib import Path
from typing import Tuple

import pandas as pd

# Key Migration / Platform Events
#
# IMPORTANT: There are two competing "letter" conventions in this repo:
#
# - Legacy (analysis) letters: used by most regression/regime/E-I scripts.
#     A = FPH ban        (2015-06-10)
#     B = GA ban         (2018-09-12)
#     C = The_Donald ban (2020-06-29)
#     D = Pizzagate ban  (2016-11-23)
#
# - Chronological letters: used by some plotting/period-slicing utilities.
#     A = FPH  (2015-06-10)
#     B = PG   (2016-11-23)
#     C = GA   (2018-09-12)
#     D = TD   (2020-06-29)
#
# To avoid silent bugs, keep `EVENTS` as the *legacy* mapping (backwards-compatible),
# and use `EVENTS_CHRONO` explicitly when you need A/B/C/D to be chronological.
EVENTS_LEGACY = {
    "A": pd.Timestamp("2015-06-10"),  # FPH
    "B": pd.Timestamp("2018-09-12"),  # GreatAwakening
    "C": pd.Timestamp("2020-06-29"),  # The_Donald
    "D": pd.Timestamp("2016-11-23"),  # Pizzagate
}

EVENT_LABELS_LEGACY = {
    "A": "FPH Ban",
    "B": "GA Ban",
    "C": "TD Ban",
    "D": "Pizzagate Ban",
}

# Chronological (period-slicing) mapping: FPH -> PG -> GA -> TD
EVENTS_CHRONO = {
    "A": EVENTS_LEGACY["A"],
    "B": EVENTS_LEGACY["D"],
    "C": EVENTS_LEGACY["B"],
    "D": EVENTS_LEGACY["C"],
}

EVENT_LABELS_CHRONO = {
    "A": EVENT_LABELS_LEGACY["A"],
    "B": EVENT_LABELS_LEGACY["D"],
    "C": EVENT_LABELS_LEGACY["B"],
    "D": EVENT_LABELS_LEGACY["C"],
}

# Backwards-compatible defaults (legacy semantics)
EVENTS = EVENTS_LEGACY
EVENT_LABELS = EVENT_LABELS_LEGACY

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
    
    pre = window.loc[window["month_dt"] < event_date].copy()
    post = window.loc[window["month_dt"] >= event_date].copy()
    
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
