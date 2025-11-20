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
    parser.add_argument("--memory-limit", default="24GB", help="DuckDB memory limit (default: 24GB)")
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "duckdb_spill",
        help="Directory for DuckDB temp/spill files (default: tmp/duckdb_spill)",
    )
    return parser.parse_args()


def parquet_path(data_dir: Path, platform: str, community: str) -> Path:
    path = data_dir / f"{platform}_{community}_madoc.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")
    return path


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


def run_duckdb_pipeline(
    parquet_file: Path,
    reputation_file: Optional[Path],
    output_file: Path,
    memory_limit: str,
    temp_dir: Path,
) -> None:
    """Execute the full extraction and merge pipeline using DuckDB SQL."""

    temp_dir.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect()
    conn.execute(f"PRAGMA memory_limit='{memory_limit}'")
    conn.execute(f"PRAGMA temp_directory='{temp_dir.as_posix()}'")
    conn.execute("PRAGMA threads=4")

    logging.info(f"DuckDB initialized with {memory_limit} RAM limit")

    # 1. Define Behavioral CTE
    behavioral_cte = f"""
        behavioral_base AS (
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
        behavioral_cleaned AS (
            SELECT
                user_id,
                CASE WHEN publish_date IS NULL THEN NULL
                     WHEN publish_date > 100000000000 THEN publish_date / 1000
                     ELSE publish_date END AS ts_seconds,
                sentiment_vader,
                sentiment_textblob,
                subjectivity_textblob,
                toxicity_toxigen
            FROM behavioral_base
            WHERE user_id IS NOT NULL
              AND interaction_type IN ('post', 'comment')
        ),
        behavioral_monthly AS (
            SELECT
                user_id,
                strftime('%Y-%m', CAST(to_timestamp(ts_seconds) AS TIMESTAMP)) AS month,
                AVG(toxicity_toxigen) AS mean_toxicity,
                AVG(sentiment_vader) AS mean_vader,
                AVG(sentiment_textblob) AS mean_textblob,
                AVG(subjectivity_textblob) AS mean_subjectivity,
                COUNT(*) AS activity_count
            FROM behavioral_cleaned
            WHERE ts_seconds IS NOT NULL
            GROUP BY user_id, month
            HAVING month IS NOT NULL
        )
    """

    # 2. Define Reputation CTE (if exists)
    if reputation_file:
        reputation_cte = f"""
        , reputation_base AS (
            SELECT
                CAST(user_id AS VARCHAR) AS user_id,
                CAST(reputation AS DOUBLE) AS reputation,
                CAST(date AS TIMESTAMP) AS date
            FROM read_parquet('{reputation_file.as_posix()}')
        ),
        reputation_monthly AS (
            SELECT
                user_id,
                strftime('%Y-%m', date) AS month,
                AVG(reputation) AS mean_reputation,
                COUNT(*) AS active_days
            FROM reputation_base
            WHERE reputation >= 1
            GROUP BY user_id, month
        )
        """
        final_select = """
        SELECT
            b.user_id,
            b.month,
            b.mean_toxicity,
            b.mean_vader,
            b.mean_textblob,
            b.mean_subjectivity,
            b.activity_count,
            r.mean_reputation AS mean_reputation,
            COALESCE(r.active_days, 0) AS active_days
        FROM behavioral_monthly b
        LEFT JOIN reputation_monthly r ON b.user_id = r.user_id AND b.month = r.month
        """
    else:
        reputation_cte = ""
        final_select = """
        SELECT
            user_id,
            month,
            mean_toxicity,
            mean_vader,
            mean_textblob,
            mean_subjectivity,
            activity_count,
            CAST(NULL AS DOUBLE) AS mean_reputation,
            0 AS active_days
        FROM behavioral_monthly
        """

    # 3. Construct Full Query
    full_query = f"""
        WITH {behavioral_cte}
        {reputation_cte}
        {final_select}
    """

    logging.info("Executing DuckDB pipeline and writing directly to Parquet...")
    
    try:
        conn.execute(f"""
            COPY ({full_query}) 
            TO '{output_file.as_posix()}' 
            (FORMAT PARQUET, COMPRESSION 'SNAPPY')
        """)
        logging.info(f"Successfully wrote: {output_file}")
        
        # Verify output
        count = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{output_file.as_posix()}')").fetchone()[0]
        logging.info(f"Total rows written: {count:,}")
        
    except Exception as e:
        logging.error(f"DuckDB pipeline failed: {e}")
        if output_file.exists():
            output_file.unlink()
        raise
    finally:
        conn.close()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    platform = args.platform.lower()
    community = args.community.lower()

    logging.info(f"Processing {platform}/{community} (PURE DUCKDB MODE)")

    pq_path = parquet_path(args.data_dir, platform, community)
    
    if args.skip_reputation:
        logging.info("Skipping reputation (--skip-reputation flag)")
        rep_file = None
    else:
        rep_file = find_reputation_file(args.reputation_dir, platform, community)

    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = REPO_ROOT / "results" / "alternative" / platform / "results"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{platform}_{community}_user_month_metrics.parquet"

    run_duckdb_pipeline(pq_path, rep_file, output_file, args.memory_limit, args.temp_dir)


if __name__ == "__main__":
    main()
