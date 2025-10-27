#!/usr/bin/env python3
"""
Build calendar-month window user interaction networks from MADOC Parquet files.

This script reads one or more Parquet files with the MADOC schema (for Reddit or
Voat), filters to the specified platform and community, extracts commenter →
parent edges for comments, and writes per-window edge lists under
`results/networks/<community>/window<window_days>/`.

Defaults:
- Window size: 1 calendar month
- Step size: 1 month (discrete, non-overlapping shifts by month)
- Undirected edges: enabled (we output one edge per pair, irrespective of order)
- Minimum interactions (per window) to include an edge: 1

Outputs:
- For each monthly window, a TXT file of unique edges:
  `networks/<platform>/<community>_monthly/<community>_<YYYY-MM>.txt`
  If using multi-month windows (k>1):
  `networks/<platform>/<community>_months<k>/<community>_<YYYY-MM>_to_<YYYY-MM>.txt`
  Each line contains two identifiers separated by a single space: `user_id parent_user_id`.

Notes:
- The script only needs a subset of columns: publish_date, user_id, parent_user_id,
  interaction_type, platform, community.
- Timestamps are converted to UTC dates using a seconds vs milliseconds heuristic
  (same approach as scripts/basic_stats_timeseries.py). Windows are indexed in
  number of days since the first observed date in the filtered data (start=0).
- For performance, all filtering and windowing happens in-memory per community.

Examples:
- Build Reddit networks for `fatpeoplehate` with defaults:
  python scripts/core_periphery/build_networks_from_parquet.py \
      --input data/reddit_fatpeoplehate_madoc.parquet \
      --platform reddit --community fatpeoplehate

- Build Voat networks for `pics`, 3-month windows (stepping 1 month), only edges with ≥3 interactions:
  python scripts/core_periphery/build_networks_from_parquet.py \
      --input data/voat_pics_madoc.parquet \
      --platform voat --community pics \
      --months-per-window 3 --min-interactions 3

Requirements: pandas, pyarrow (preferred). If pyarrow is unavailable, pandas' read_parquet
fallback may work if `fastparquet` is installed.
"""

import os
import sys
import math
import glob
import argparse
import logging
from typing import Iterable, List

import pandas as pd


# Avoid BLAS oversubscription for smoother parallel runs
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("BLIS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("ARROW_NUM_THREADS", "1")


def _find_inputs(paths_or_globs: Iterable[str]) -> List[str]:
    files: List[str] = []
    for p in paths_or_globs:
        if os.path.isdir(p):
            files.extend(sorted(glob.glob(os.path.join(p, "**", "*.parquet"), recursive=True)))
        elif os.path.isfile(p):
            files.append(p)
        else:
            files.extend(sorted(glob.glob(p)))
    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for f in files:
        if f not in seen:
            uniq.append(f)
            seen.add(f)
    return uniq


def _safe_to_date(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    med = s.dropna().median()
    unit = "s"
    try:
        if pd.notna(med) and med > 1e11:
            unit = "ms"
    except Exception:
        unit = "s"
    dt = pd.to_datetime(s, unit=unit, utc=True, errors="coerce")
    return dt.dt.floor("D")


def build_edges(
    inputs: List[str],
    platform: str,
    community: str,
    months_per_window: int = 1,
    min_interactions: int = 1,
    undirected: bool = True,
    output_dir: str | None = None,
):
    """Build sliding-window edge lists from MADOC Parquet files.

    Parameters
    - inputs: list of Parquet files (paths)
    - platform: 'reddit' or 'voat'
    - community: community name to filter (case-insensitive)
    - months_per_window: number of consecutive calendar months per window (>=1)
    - min_interactions: minimum interactions per edge within a window
    - undirected: if True, normalize edges so (u,v) == (v,u)
    - output_dir: base output directory. Defaults to networks/<platform>/<community>_monthly (or _monthsK)
    """
    if not inputs:
        raise FileNotFoundError("No input parquet files matched. Check --input path or glob.")

    # Read only required columns
    required_cols = [
        "publish_date",
        "user_id",
        "parent_user_id",
        "interaction_type",
        "platform",
        "community",
    ]

    # Try pyarrow first for performance
    df_parts: List[pd.DataFrame] = []
    for path in inputs:
        try:
            import pyarrow.parquet as pq  # type: ignore

            table = pq.read_table(
                path,
                columns=required_cols,
                use_threads=False,
            )
            part = table.to_pandas(types_mapper=None)
        except Exception:
            # Fallback to pandas
            part = pd.read_parquet(path, columns=required_cols)
        df_parts.append(part)

    df = pd.concat(df_parts, ignore_index=True)

    # Normalize and filter
    df["platform"] = df["platform"].astype(str).str.lower()
    df["community"] = df["community"].astype(str)
    df = df[df["platform"] == platform.lower()]
    df = df[df["community"].str.lower() == community.lower()]

    if df.empty:
        logging.warning("No rows after platform/community filter. Nothing to do.")
        return

    # Comments only, require both ids, remove self-loops
    itype = df["interaction_type"].astype(str).str.lower()
    df = df[itype.isin(["comment", "reply"])]
    df = df[df["user_id"].notna() & df["parent_user_id"].notna()]
    df = df[df["user_id"] != df["parent_user_id"]]

    if df.empty:
        logging.warning("No comment edges after filtering. Nothing to do.")
        return

    # Date bucketing: calendar months
    df["_date"] = _safe_to_date(df["publish_date"])
    df = df[df["_date"].notna()]
    if df.empty:
        logging.warning("No valid dates after conversion. Nothing to do.")
        return
    df["_month"] = df["_date"].dt.to_period("M")

    # Prepare edges (optionally undirected)
    # Keep the monthly bucket for downstream grouping
    if undirected:
        # Normalize as sorted tuple per row; avoid Python apply where possible
        a = df[["user_id", "parent_user_id"]].astype(str)
        # Create normalized columns
        src = a.min(axis=1)
        dst = a.max(axis=1)
        df = pd.DataFrame({"_month": df["_month"], "src": src, "dst": dst})
    else:
        df = pd.DataFrame({"_month": df["_month"], "src": df["user_id"].astype(str), "dst": df["parent_user_id"].astype(str)})

    # Pre-aggregate counts per month, per pair to accelerate windowing
    monthly_pairs = (
        df.groupby(["_month", "src", "dst"], observed=True, sort=False)
          .size().reset_index(name="w")
    )

    if monthly_pairs.empty:
        logging.warning("No monthly edges after grouping. Nothing to do.")
        return

    # Sorted month list
    months = sorted(monthly_pairs["_month"].unique())
    if months_per_window < 1:
        raise ValueError("months-per-window must be >= 1")

    if output_dir is None:
        if months_per_window == 1:
            output_dir = os.path.join("networks", platform.lower(), f"{community}_monthly")
        else:
            output_dir = os.path.join("networks", platform.lower(), f"{community}_months{months_per_window}")
    os.makedirs(output_dir, exist_ok=True)

    # Enumerate monthly windows (discrete step of 1 month)
    n_windows = 0
    for i in range(0, len(months) - months_per_window + 1):
        window_months = months[i : i + months_per_window]
        sel = monthly_pairs[monthly_pairs["_month"].isin(window_months)]
        if sel.empty:
            continue
        # Sum weights across months within the window, filter by min_interactions
        win_pairs = sel.groupby(["src", "dst"], observed=True, sort=False)["w"].sum().reset_index()
        if min_interactions > 1:
            win_pairs = win_pairs[win_pairs["w"] >= int(min_interactions)]
        if win_pairs.empty:
            continue

        start_m = pd.Period(window_months[0]).strftime("%Y-%m")
        end_m = pd.Period(window_months[-1]).strftime("%Y-%m")
        if months_per_window == 1:
            fname = f"{community}_{start_m}.txt"
        else:
            fname = f"{community}_{start_m}_to_{end_m}.txt"
        out_path = os.path.join(output_dir, fname)
        # Write two columns, space-separated, no header
        win_pairs[["src", "dst"]].to_csv(out_path, index=False, header=False, sep=" ")
        n_windows += 1

    logging.info("Wrote %d window edge files to %s", n_windows, output_dir)


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build sliding-window user interaction networks from MADOC Parquet (Reddit/Voat)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--input",
        nargs="+",
        required=True,
        help="Parquet file(s), directory, or glob(s) (space-separated)",
    )
    p.add_argument(
        "--platform",
        choices=["reddit", "voat"],
        required=True,
        help="Platform to filter (case-insensitive)",
    )
    p.add_argument(
        "--community",
        required=True,
        help="Community/subreddit/subverse name (case-insensitive)",
    )
    p.add_argument("--months-per-window", type=int, default=1, help="Number of calendar months per window (step = 1 month)")
    p.add_argument(
        "--min-interactions",
        type=int,
        default=1,
        help="Minimum number of interactions within a window to include an edge",
    )
    p.add_argument(
        "--directed",
        action="store_true",
        help="If set, keep edges directed (default is undirected)",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        help="Base output dir; defaults to results/networks/<community>/window<window_days>",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s: %(message)s",
    )

    inputs = _find_inputs(args.input)
    logging.info("Found %d input file(s)", len(inputs))
    try:
        build_edges(
            inputs=inputs,
            platform=args.platform,
            community=args.community,
            months_per_window=args.months_per_window,
            min_interactions=args.min_interactions,
            undirected=not args.directed,
            output_dir=args.output_dir,
        )
    except Exception as e:
        logging.error("Failed: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
