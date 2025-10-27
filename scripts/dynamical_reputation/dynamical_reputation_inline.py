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
        last_activity_date (datetime): Date-time stamp designating when the last recorded activity of user
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


def build_output_paths(base_output: str, community: str | None, platform: str | None) -> Tuple[str, str]:
    # Repo structure: results/reputation/<community|global>/<voat|reddit|compare>/{results,figures}
    comm = community.lower() if community else "global"
    plat = platform.lower() if platform else "compare"
    root = os.path.join(base_output, comm, plat)
    results_dir = os.path.join(root, "results")
    figures_dir = os.path.join(root, "figures")
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)
    return results_dir, figures_dir


def default_filename(community: str | None, platform: str | None, fmt: str) -> str:
    comm = (community or "global").lower()
    plat_prefix = f"{(platform or 'compare').lower()}_"
    base = f"{plat_prefix}{comm}_user_daily_reputation"
    return f"{base}.{fmt}"


def get_memory_info():
    """Return memory usage as a formatted string."""
    mem = psutil.virtual_memory()
    return f"{mem.used / (1024**3):.1f}GB/{mem.total / (1024**3):.1f}GB ({mem.percent:.1f}%)"


def extract_community_from_filename(filepath: str) -> str:
    """Extract community name from filename like reddit_COMMUNITY_madoc.parquet."""
    basename = os.path.basename(filepath)
    # Remove reddit_ prefix and _madoc.parquet suffix
    name = basename.replace("reddit_", "").replace("voat_", "")
    name = name.replace("_madoc.parquet", "").replace(".parquet", "")
    return name


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Compute per-user daily dynamical reputation from Parquet inputs. "
            "Reputation spans from each user's first activity through the community last day (decay applied)."
        )
    )
    p.add_argument("--input", "-i", required=True, help="Parquet file pattern (e.g., data/reddit_*.parquet)")
    p.add_argument("--platform", choices=["reddit", "voat"], help="Filter to platform")
    p.add_argument("--community", help="Filter to specific community (overrides multi-file processing)")
    p.add_argument("--output-dir", default=os.path.join("results", "reputation"), help="Base output directory")
    p.add_argument("--output-format", choices=["csv", "parquet"], default="csv")
    p.add_argument("--workers", type=int, default=3, help="Number of parallel workers (default: 3)")
    # Algorithm params (defaults match previous inline usage)
    p.add_argument("--beta", type=float, default=0.96)
    p.add_argument("--alpha", type=float, default=2.0)
    p.add_argument("--Ib", type=float, default=1.0)
    p.add_argument("--decay-per-day", action="store_true", help="Apply decay for each inactive day (default: False)")
    return p.parse_args()


def process_single_file(filepath: str, args, workers: int) -> dict:
    """Process a single parquet file and return stats."""
    community = args.community or extract_community_from_filename(filepath)
    filesize = os.path.getsize(filepath) / (1024**3)  # GB

    print(f"\n{'='*60}")
    print(f"Community: {community} ({filesize:.2f}GB)")
    print(f"Memory before: {get_memory_info()}")

    import time
    start = time.time()

    try:
        df = read_and_filter_parquet(filepath, platform=args.platform, community=args.community)

        out_df, tmin, tmax = compute_reputation_parallel(
            df,
            beta=args.beta,
            Ib=args.Ib,
            alpha=args.alpha,
            decay_per_day=args.decay_per_day,
            workers=workers,
        )

        # Clean up dataframe memory
        del df
        gc.collect()

        results_dir, _ = build_output_paths(args.output_dir, community, args.platform)
        fname = default_filename(community, args.platform, args.output_format)
        fpath = os.path.join(results_dir, fname)

        if args.output_format == "csv":
            out_df.to_csv(fpath, index=False)
        else:
            out_df.to_parquet(fpath, index=False)

        elapsed = time.time() - start
        stats = {
            'community': community,
            'success': True,
            'rows': len(out_df),
            'users': out_df['user_id'].nunique(),
            'date_from': pd.to_datetime(tmin, unit='s').date(),
            'date_to': pd.to_datetime(tmax, unit='s').date(),
            'output': fpath,
            'elapsed': elapsed,
            'error': None
        }

        print(f"✓ Success: {stats['rows']:,} rows, {stats['users']:,} users")
        print(f"  Date range: {stats['date_from']} to {stats['date_to']}")
        print(f"  Output: {fpath}")
        print(f"  Time: {elapsed:.1f}s")
        print(f"Memory after: {get_memory_info()}")

        # Clean up output dataframe
        del out_df
        gc.collect()

        return stats

    except Exception as e:
        elapsed = time.time() - start
        print(f"✗ Failed: {str(e)}")
        print(f"Memory after: {get_memory_info()}")
        gc.collect()
        return {
            'community': community,
            'success': False,
            'error': str(e),
            'elapsed': elapsed
        }


def main():
    args = parse_args()
    workers = decide_workers(args.workers)

    # Expand glob pattern
    files = sorted(glob(args.input))
    if not files:
        raise FileNotFoundError(f"No files match pattern: {args.input}")

    # Sort by file size (smallest first)
    files = sorted(files, key=lambda f: os.path.getsize(f))

    print("="*60)
    print("Dynamical Reputation Computation")
    print("="*60)
    print(f"Platform: {args.platform or 'all'}")
    print(f"Workers: {workers}")
    print(f"Files to process: {len(files)}")
    print(f"Initial memory: {get_memory_info()}")

    results = []
    for i, filepath in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] Processing: {os.path.basename(filepath)}")
        stats = process_single_file(filepath, args, workers)
        results.append(stats)

        # Brief pause for memory cleanup
        import time
        time.sleep(1)

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    success = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    print(f"Total: {len(results)}")
    print(f"✓ Succeeded: {len(success)}")
    if failed:
        print(f"✗ Failed: {len(failed)}")
        for f in failed:
            print(f"  - {f['community']}: {f['error']}")

    print(f"\nFinal memory: {get_memory_info()}")


if __name__ == "__main__":
    main()
