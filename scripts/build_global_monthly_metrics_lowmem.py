#!/usr/bin/env python3
"""Build global monthly metrics with LOW MEMORY footprint.

Memory-optimized version that uses DuckDB for both behavioral metrics
AND reputation aggregation. Safe for large communities (gaming, funny).
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--community", required=True)
    parser.add_argument("--platform", required=True, choices=["reddit", "voat"])
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--reputation-dir", type=Path, default=REPO_ROOT / "results" / "reputation")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--skip-reputation", action="store_true", help="Skip reputation merging")
    return parser.parse_args()


def parquet_path(data_dir: Path, platform: str, community: str) -> Path:
    path = data_dir / f"{platform}_{community}_madoc.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")
    return path


def build_user_month_metrics(parquet_file: Path) -> pd.DataFrame:
    """Extract per-user monthly behavioral metrics using DuckDB streaming."""
    conn = duckdb.connect()
    conn.execute("PRAGMA memory_limit='4GB'")
    conn.execute("PRAGMA threads=2")

    query = f"""
        WITH base AS (
            SELECT
                CAST(user_id AS VARCHAR) AS user_id,
                LOWER(CAST(interaction_type AS VARCHAR)) AS interaction_type,
                CAST(publish_date AS DOUBLE) AS publish_date,
                CAST(sentiment_vader AS DOUBLE) AS sentiment_vader,
                CAST(sentiment_textblob AS DOUBLE) AS sentiment_textblob,
                CAST(subjectivity_textblob AS DOUBLE) AS subjectivity_textblob,
                CAST(toxicity_toxigen AS DOUBLE) AS toxicity_toxigen
            FROM read_parquet('{parquet_file.as_posix()}')
        ),
        cleaned AS (
            SELECT
                user_id,
                interaction_type,
                CASE WHEN publish_date IS NULL THEN NULL
                     WHEN publish_date > 100000000000 THEN publish_date / 1000
                     ELSE publish_date END AS ts_seconds,
                sentiment_vader,
                sentiment_textblob,
                subjectivity_textblob,
                toxicity_toxigen
            FROM base
            WHERE user_id IS NOT NULL
        ),
        filtered AS (
            SELECT
                *,
                strftime('%Y-%m', CAST(to_timestamp(ts_seconds) AS TIMESTAMP)) AS month
            FROM cleaned
            WHERE interaction_type IN ('post', 'comment')
              AND ts_seconds IS NOT NULL
        )
        SELECT
            user_id,
            month,
            AVG(toxicity_toxigen) AS mean_toxicity,
            AVG(sentiment_vader) AS mean_vader,
            AVG(sentiment_textblob) AS mean_textblob,
            AVG(subjectivity_textblob) AS mean_subjectivity,
            COUNT(*) AS activity_count
        FROM filtered
        WHERE month IS NOT NULL
        GROUP BY user_id, month
    """

    logging.info("Executing DuckDB query (streaming from parquet)...")
    df = conn.execute(query).df()
    conn.close()

    df = df.dropna(subset=["month"])
    df["month"] = df["month"].astype(str)

    logging.info(
        f"Extracted {len(df):,} user-month records "
        f"({df['user_id'].nunique():,} unique users, {df['month'].nunique()} months)"
    )

    return df


def find_reputation_file(reputation_dir: Path, platform: str, community: str) -> Optional[Path]:
    """Locate reputation file."""
    plat = platform.lower()
    comm = community.lower()

    candidates = [
        reputation_dir / comm / plat / "results" / f"{plat}_{comm}_user_daily_reputation.parquet",
        reputation_dir / plat / "results" / f"{plat}_{comm}_user_daily_reputation.parquet",
    ]

    for path in candidates:
        if path.exists():
            logging.info(f"Found reputation file: {path}")
            return path

    logging.warning(f"No reputation file found for {platform}/{community}")
    return None


def aggregate_reputation_with_duckdb(reputation_file: Path) -> pd.DataFrame:
    """Aggregate daily reputation to monthly using DuckDB (memory-efficient)."""
    conn = duckdb.connect()
    conn.execute("PRAGMA memory_limit='4GB'")
    conn.execute("PRAGMA threads=2")

    logging.info("Aggregating reputation with DuckDB (streaming)...")

    query = f"""
        WITH reputation_base AS (
            SELECT
                CAST(user_id AS VARCHAR) AS user_id,
                CAST(reputation AS DOUBLE) AS reputation,
                CAST(date AS TIMESTAMP) AS date
            FROM read_parquet('{reputation_file.as_posix()}')
        ),
        with_month AS (
            SELECT
                user_id,
                reputation,
                strftime('%Y-%m', date) AS month
            FROM reputation_base
            WHERE reputation >= 1
        )
        SELECT
            user_id,
            month,
            AVG(reputation) AS mean_reputation,
            COUNT(*) AS active_days
        FROM with_month
        GROUP BY user_id, month
    """

    try:
        df = conn.execute(query).df()
        df["month"] = df["month"].astype(str)
        df["user_id"] = df["user_id"].astype(str)

        logging.info(
            f"Aggregated reputation to {len(df):,} user-month records "
            f"({df['user_id'].nunique():,} users)"
        )

        return df
    except Exception as e:
        logging.error(f"Failed to aggregate reputation: {e}")
        return pd.DataFrame(columns=["user_id", "month", "mean_reputation", "active_days"])
    finally:
        conn.close()


def merge_metrics_chunked(behavioral: pd.DataFrame, reputation: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Merge behavioral and reputation."""
    if reputation is None or reputation.empty:
        logging.warning("No reputation data to merge")
        result = behavioral.copy()
        result["mean_reputation"] = float("nan")
        result["active_days"] = 0
        return result

    result = behavioral.merge(reputation, on=["user_id", "month"], how="left")
    result["mean_reputation"] = result["mean_reputation"].fillna(float("nan"))
    result["active_days"] = result["active_days"].fillna(0).astype(int)

    logging.info(
        f"Merged metrics: {len(result):,} user-month records, "
        f"{result['mean_reputation'].notna().sum():,} with reputation"
    )

    return result


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    platform = args.platform.lower()
    community = args.community.lower()

    logging.info(f"Processing {platform}/{community} (LOW MEMORY MODE)")

    pq_path = parquet_path(args.data_dir, platform, community)
    behavioral = build_user_month_metrics(pq_path)

    if args.skip_reputation:
        logging.info("Skipping reputation (--skip-reputation flag)")
        rep_monthly = None
    else:
        rep_file = find_reputation_file(args.reputation_dir, platform, community)
        if rep_file:
            rep_monthly = aggregate_reputation_with_duckdb(rep_file)
        else:
            rep_monthly = None

    user_month_metrics = merge_metrics_chunked(behavioral, rep_monthly)

    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = REPO_ROOT / "results" / "alternative" / platform / "results"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{platform}_{community}_user_month_metrics.parquet"

    user_month_metrics.to_parquet(output_file, index=False)
    logging.info(f"Wrote {output_file} ({len(user_month_metrics):,} rows)")

    logging.info("=" * 60)
    logging.info("Summary Statistics:")
    logging.info(f"  Total user-months: {len(user_month_metrics):,}")
    logging.info(f"  Unique users: {user_month_metrics['user_id'].nunique():,}")
    logging.info(f"  Months covered: {user_month_metrics['month'].nunique()}")
    logging.info(f"  With reputation: {user_month_metrics['mean_reputation'].notna().sum():,}")
    logging.info("=" * 60)


if __name__ == "__main__":
    main()
