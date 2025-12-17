import argparse
import os
import gc
import psutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, Iterable, List, Tuple
from glob import glob

import pandas as pd
import datetime
from datetime import timedelta
import numpy as np

def _sec_to_datetime(ts: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(int(ts))

def calculate_user_reputation(dates, d_min, day_max, beta=0.999, Ib=1, alpha=2, decay_per_day = "True" ):
    """Returns a dictionary of user's reputational values for each day
    Args:
        dates (DataFrame): Pandas DataFrame with timestamp and day columns.
        Each row is a single interaction by the same user.
        d_min (datetime): Date-time stamp of the first interaction: 'YYYY-MM-DDTHH:MM:SS.SSS'
        day_max (int): Upper limit for days after first interaction which are counted.
        beta (float, optional): Reputation decay parameter. Defaults to 0.999.
        Ib (float, optional): Basic reputational value of a single interaction. Defaults to 1.
        alpha (float, optional): Cumulation parameter. Defaults to 2.
        decay_per_day (str, optional): Perform decay in each day of inactivity? Defaults to "True".
    Returns:
        (dict): A dictionary of user's reputational values for each day
    """
    dates = dates.sort_values(by='Time')
    Ru = {}
    first_day = dates.iloc[0].days
    first_date = dates.iloc[0].Time
    # Note: We intentionally do NOT prefill days before first interaction.
    # We only return days from user's first activity onward.
    A = 1
    Ru[first_day] = Ib + Ib*alpha*(1.-1./(A+1))
    last_day = first_day
    last_activity_date = first_date
    last_activity_day = first_day
    for i in range(1,len(dates)):
        curr_day = dates.iloc[i].days
        curr_activity_date = dates.iloc[i].Time
        if curr_day > (last_day+1):
            for i in range(curr_day-last_day - 1):
                inactive_date = pd.to_datetime(d_min) + timedelta(days=int(last_day)+2)
                update_reputation_inactive(Ru, inactive_date, last_activity_date, last_activity_day,  last_day, beta=beta, decay_per_day = decay_per_day)
                last_day = last_day + 1
                A = 0
        A+=1
        update_reputation(Ru, A, curr_activity_date, last_activity_date, last_day, last_activity_day, curr_day, beta=beta,  Ib=Ib, alpha=alpha, decay_per_day=decay_per_day)
        last_activity_date = curr_activity_date
        last_activity_day = curr_day
        last_day = curr_day
    rest_days = day_max - last_day
    for i in range(rest_days):
        inactive_date = pd.to_datetime(d_min) + timedelta(days=int(last_day)+2)
        update_reputation_inactive(Ru, inactive_date, last_activity_date, last_activity_day,  last_day, beta=beta, decay_per_day = decay_per_day)
        last_day = last_day + 1
    return Ru

def update_reputation_inactive(R, inactive_date, last_activity_date, last_activity_day, last_day, beta=0.999, decay_per_day = 'True'):
    """Performs the decay of user's reputation during a period of inactivity.
    Args:
        R (dict): Dictionary of user's reputation which will be updated.
        inactive_date (datetime): Date-time stamp designating when the period of inactivity ends
        last_activity_date (datetime): Date-time stamp designating previous activity of the user
        last_activity_day (int): Day in which last activity was recorded
        last_day (int): Last day for which reputation was previously updated
        beta (float, optional): Reputation decay parameter. Defaults to 0.999.
        decay_per_day (str, optional): Perform decay in each day of inactivity? Defaults to "True".
    """
    dt = ( pd.to_datetime(inactive_date) - pd.to_datetime(last_activity_date))/np.timedelta64(1,'D')
    if decay_per_day=='True':
        D = R[last_day]*np.power(beta, dt)
    else:
        D = R[last_activity_day]*np.power(beta, dt)
    R[last_day+1] = D

def update_reputation(R, A, curr_date, last_activity_date, last_day, last_activity_day, curr_day, beta=0.999,  Ib=1, alpha=2, decay_per_day='True'):
    """Performs the decay of user's reputation during a period of inactivity.
    Args:
        R (dict): Dictionary of user's reputation which will be updated.
        A (int): Count of consecutive interactions within time-window frame
        curr_date (datetime): Date-time stamp of current activity when update function was called
        last_activity_date (datetime): Date-time stamp designating previous activity of the user
        last_activity_day (int): Day in which last activity was recorded
        last_day (int): Last day for which reputation was previously updated
        beta (float, optional): Reputation decay parameter. Defaults to 0.999.
        decay_per_day (str, optional): Perform decay in each day of inactivity? Defaults to "True".
    """
    dt = ( pd.to_datetime(curr_date) - pd.to_datetime(last_activity_date))/np.timedelta64(1,'D')
    In = Ib + Ib*alpha*(1.-1./(A+1))
    if (decay_per_day=='False') and (A==1):
        D = R[last_activity_day]*np.power(beta, dt)
    else:
        D = R[last_day]*np.power(beta, dt)
    y = R.get(curr_day, 0.)
    y = In+D
    R[curr_day] = y

def _compute_user_ru(
    user_and_times: Tuple[str, List[int]],
    tmin: int,
    tmax: int,
    beta: float,
    Ib: float,
    alpha: float,
    decay_per_day: bool,
):
    """Compute daily reputation for a single user.

    Returns a list of tuples (user_id, day, reputation). Only days from the user's
    first interaction up to the community last day are included.
    """
    user_id, times = user_and_times
    if not times:
        return []
    times_sorted = sorted(int(t) for t in times)
    # Build DataFrame expected by calculate_user_reputation
    days = [(_sec_to_datetime(t) - _sec_to_datetime(tmin)).days for t in times_sorted]
    df = pd.DataFrame({
        "Time": [_sec_to_datetime(t) for t in times_sorted],
        "days": days,
    })

    d_min = _sec_to_datetime(tmin)
    day_max = (_sec_to_datetime(tmax) - _sec_to_datetime(tmin)).days
    Ru = calculate_user_reputation(
        df,
        d_min=d_min,
        day_max=day_max,
        beta=beta,
        Ib=Ib,
        alpha=alpha,
        decay_per_day="True" if decay_per_day else "False",
    )

    # Only return days from user's first interaction onward
    first_day = min(days)
    rows = [(str(user_id), int(day), float(val)) for day, val in Ru.items() if int(day) >= int(first_day)]
    return rows


def _detect_ms_epoch(series: pd.Series) -> bool:
    """Heuristic: detect if epoch is in milliseconds (values ~ 1e12)."""
    try:
        s = pd.to_numeric(series.dropna().astype("int64"))
    except Exception:
        return False
    if s.empty:
        return False
    q = s.quantile(0.5)
    return q > 1e11  # seconds ~1e9, ms ~1e12


def read_and_filter_parquet(filepath: str, platform: str = None, community: str = None) -> pd.DataFrame:
    """Read a single Parquet file and filter to columns of interest.

    Required columns: publish_date, user_id, platform, community, interaction_type
    Filters: platform (optional), community (optional), interaction_type in {POST, COMMENT}
    """
    cols = [
        "publish_date",
        "user_id",
        "platform",
        "community",
        "interaction_type",
    ]

    df = pd.read_parquet(filepath, columns=cols)

    # Basic cleaning
    df = df.dropna(subset=["publish_date", "user_id"]).copy()

    # Normalize epoch to seconds if needed
    if _detect_ms_epoch(df["publish_date"]):
        df["publish_date"] = (df["publish_date"].astype("int64") // 1000).astype("int64")
    else:
        df["publish_date"] = df["publish_date"].astype("int64")

    # Filter interaction types (case-insensitive)
    df = df[df["interaction_type"].str.lower().isin(["post", "comment"])].copy()

    if platform is not None:
        df = df[df["platform"].str.lower() == platform.lower()].copy()
    if community is not None:
        df = df[df["community"].str.lower() == community.lower()].copy()

    if df.empty:
        raise ValueError("No rows after filtering by platform/community and interaction types")

    return df


def decide_workers(requested: int | None) -> int:
    max_workers = os.cpu_count() or 4
    # target 5-10 range, capped by CPU
    if requested is not None and requested > 0:
        return max(1, min(requested, max_workers))
    # heuristic default: min(10, max(5, cpu-1))
    return max(1, min(10, max(5, max_workers - 1)))


def compute_reputation_parallel(
    df: pd.DataFrame,
    beta: float,
    Ib: float,
    alpha: float,
    decay_per_day: bool,
    workers: int,
) -> Tuple[pd.DataFrame, int, int]:
    # Global Tmin/Tmax across the filtered dataset (community scope)
    tmin = int(df["publish_date"].min())
    tmax = int(df["publish_date"].max())

    # Prepare per-user timestamp lists
    grouped = df.groupby("user_id")["publish_date"].apply(list)
    tasks = [(str(uid), times) for uid, times in grouped.items()]

    rows: List[Tuple[str, int, float]] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(
                _compute_user_ru,
                task,
                tmin,
                tmax,
                beta,
                Ib,
                alpha,
                decay_per_day,
            ): task[0]
            for task in tasks
        }
        for fut in as_completed(futs):
            res = fut.result()
            if res:
                rows.extend(res)

    if not rows:
        raise ValueError("No reputation rows produced; check input data")

    out = pd.DataFrame(rows, columns=["user_id", "day", "reputation"])  # long format
    # Add date relative to global tmin
    out["t_min"] = tmin
    out["t_max"] = tmax
    out["date"] = (pd.to_datetime(out["t_min"], unit="s") + pd.to_timedelta(out["day"], unit="D"))
    return out, tmin, tmax
