#!/usr/bin/env python3
"""
Compute monthly correlations between user-level toxicity and reputation.

For each requested platform/community pair, the script:
    1. Reads MADOC interaction data to derive per-user monthly mean toxicity.
    2. Reads user daily reputation timeseries and aggregates to monthly means.
    3. Joins the aggregates on (month, user) and computes the Pearson
       correlation between mean toxicity and mean reputation across users
       within each month.

Outputs a CSV summarising the per-month correlations alongside basic coverage
statistics to help interpret the results (user counts, average interaction
volume, etc.).
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import duckdb
import pandas as pd


@dataclass
class CommunityFiles:
    community: str
    reputation_path: Path
    toxicity_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute per-month user-level correlations between toxicity and reputation."
    )
    parser.add_argument(
        "--reputation-dir",
        type=Path,
        default=Path("results/reputation"),
        help="Base directory containing per-community reputation outputs "
        "(default: results/reputation).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Base directory containing MADOC parquet files (default: data).",
    )
    parser.add_argument(
        "--platforms",
        type=str,
        nargs="*",
        default=["voat", "reddit"],
        help="Platforms to process, each of {voat, reddit}.",
    )
    parser.add_argument(
        "--communities",
        type=str,
        nargs="*",
        help="Optional subset of communities to process (case-insensitive).",
    )
    parser.add_argument(
        "--min-users",
        type=int,
        default=5,
        help="Minimum number of users required in a month to report a correlation (default: 5).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "results/reputation/compare/results/user_monthly_toxicity_reputation_correlations.csv"
        ),
        help="Destination CSV path (default: results/reputation/compare/results/user_monthly_toxicity_reputation_correlations.csv).",
    )
    return parser.parse_args()


def discover_communities(
    reputation_dir: Path,
    data_dir: Path,
    platform: str,
) -> Dict[str, CommunityFiles]:
    community_map: Dict[str, CommunityFiles] = {}
    if not reputation_dir.exists():
        return community_map

    community_dirs = [
        p for p in reputation_dir.iterdir() if p.is_dir() and (p / platform / "results").exists()
    ]
    for community_dir in community_dirs:
        results_dir = community_dir / platform / "results"
        parquet_files = sorted(results_dir.glob(f"{platform}_*_user_daily_reputation.parquet"))
        if not parquet_files:
            continue
        rep_path = parquet_files[0]
        stem = rep_path.stem
        prefix = f"{platform}_"
        suffix = "_user_daily_reputation"
        if not stem.startswith(prefix) or not stem.endswith(suffix):
            continue
        community = stem[len(prefix) : -len(suffix)]
        toxicity_path = data_dir / f"{platform}_{community}_madoc.parquet"
        if not toxicity_path.exists():
            continue
        community_map[community.lower()] = CommunityFiles(
            community=community,
            reputation_path=rep_path,
            toxicity_path=toxicity_path,
        )
    return community_map


def execute_df(query: str, params: Sequence[object]) -> pd.DataFrame:
    with duckdb.connect() as con:
        return con.execute(query, params).df()


def aggregate_toxicity(path: Path) -> pd.DataFrame:
    query = """
        SELECT
            strftime(to_timestamp(publish_date), '%Y-%m') AS month,
            user_id,
            avg(toxicity_toxigen) AS mean_toxicity,
            count(*) AS interaction_count
        FROM read_parquet(?)
        WHERE user_id IS NOT NULL AND toxicity_toxigen IS NOT NULL
        GROUP BY 1, 2
    """
    return execute_df(query, [str(path)])


def aggregate_reputation(path: Path) -> pd.DataFrame:
    query = """
        SELECT
            strftime(CAST(date AS TIMESTAMP), '%Y-%m') AS month,
            user_id,
            avg(reputation) AS mean_reputation,
            count(*) AS daily_records
        FROM read_parquet(?)
        WHERE user_id IS NOT NULL AND reputation IS NOT NULL
        GROUP BY 1, 2
    """
    return execute_df(query, [str(path)])


def monthly_correlations(
    platform: str,
    community: str,
    aggregation: pd.DataFrame,
    min_users: int,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    if aggregation.empty:
        return rows

    for month, sub in aggregation.groupby("month"):
        num_users = len(sub)
        row: Dict[str, object] = {
            "platform": platform,
            "community": community,
            "month": month,
            "num_users": int(num_users),
            "total_interactions": int(sub["interaction_count"].sum()),
            "total_reputation_days": int(sub["daily_records"].sum()),
            "mean_toxicity": float(sub["mean_toxicity"].mean()),
            "mean_reputation": float(sub["mean_reputation"].mean()),
        }

        if num_users < min_users:
            row["corr_toxicity_reputation"] = math.nan
        else:
            unique_toxic = sub["mean_toxicity"].nunique(dropna=True)
            unique_rep = sub["mean_reputation"].nunique(dropna=True)
            if unique_toxic < 2 or unique_rep < 2:
                row["corr_toxicity_reputation"] = math.nan
            else:
                row["corr_toxicity_reputation"] = float(
                    sub["mean_toxicity"].corr(sub["mean_reputation"])
                )
        rows.append(row)
    return rows


def ensure_output_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def filter_requested(
    available: Dict[str, CommunityFiles],
    requested: Optional[Sequence[str]],
) -> Iterable[CommunityFiles]:
    if not requested:
        return available.values()
    requested_set = {c.lower() for c in requested}
    return [cfg for name, cfg in available.items() if name in requested_set]


def main() -> None:
    args = parse_args()
    results: List[Dict[str, object]] = []

    for platform in args.platforms:
        available = discover_communities(args.reputation_dir, args.data_dir, platform)
        if not available:
            continue
        selected = filter_requested(available, args.communities)
        for cfg in selected:
            toxicity_df = aggregate_toxicity(cfg.toxicity_path)
            reputation_df = aggregate_reputation(cfg.reputation_path)
            if toxicity_df.empty or reputation_df.empty:
                continue
            merged = pd.merge(
                toxicity_df,
                reputation_df,
                on=["month", "user_id"],
                how="inner",
                validate="one_to_one",
            )
            if merged.empty:
                continue
            results.extend(
                monthly_correlations(platform, cfg.community, merged, args.min_users)
            )

    if not results:
        raise RuntimeError("No correlations computed – check input paths and filters.")

    summary = pd.DataFrame(results)
    summary["month_dt"] = pd.to_datetime(summary["month"], format="%Y-%m", errors="coerce")
    summary = summary.sort_values(["platform", "community", "month_dt"]).drop(columns="month_dt")

    ensure_output_directory(args.output)
    summary.to_csv(args.output, index=False)


if __name__ == "__main__":
    main()
