#!/usr/bin/env python3
"""Build global (non-core-periphery) monthly behavioral metrics from parquet data.

Computes per-user monthly averages of toxicity, sentiment, and subjectivity,
then aggregates reputation from daily to monthly means. Outputs user-month level
metrics without core/periphery stratification.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

# Thread limiting for parallel operations
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--community",
        required=True,
        help="Community name (e.g., funny, gaming, pics).",
    )
    parser.add_argument(
        "--platform",
        required=True,
        choices=["reddit", "voat"],
        help="Platform to process.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "data",
        help="Directory containing Parquet inputs.",
    )
    parser.add_argument(
        "--reputation-dir",
        type=Path,
        default=REPO_ROOT / "results" / "reputation",
        help="Base directory for reputation files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: results/basic/{platform}/results/).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level.",
    )
    return parser.parse_args()


def parquet_path(data_dir: Path, platform: str, community: str) -> Path:
    """Construct path to MADOC parquet file."""
    path = data_dir / f"{platform}_{community}_madoc.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")
    return path


def build_user_month_metrics(parquet_file: Path) -> pd.DataFrame:
    """Extract per-user monthly behavioral metrics using DuckDB.

    Returns DataFrame with columns:
        - user_id: str
        - month: str (YYYY-MM format)
        - mean_toxicity: float
        - mean_vader: float
        - mean_textblob: float
        - mean_subjectivity: float
        - activity_count: int (number of posts/comments)
    """
    conn = duckdb.connect()
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
    df = conn.execute(query).df()
    conn.close()

    df = df.dropna(subset=["month"])
    df["month"] = df["month"].astype(str)

    logging.info(
        f"Extracted {len(df):,} user-month records "
        f"({df['user_id'].nunique():,} unique users, "
        f"{df['month'].nunique()} months)"
    )

    return df


def find_reputation_file(
    reputation_dir: Path,
    platform: str,
    community: str,
) -> Optional[Path]:
    """Locate reputation file using common naming patterns."""
    plat = platform.lower()
    comm = community.lower()

    # Try multiple locations following repo conventions
    candidates = [
        reputation_dir / comm / plat / "results" / f"{plat}_{comm}_user_daily_reputation.parquet",
        reputation_dir / comm / plat / "results" / f"{plat}_{comm}_user_daily_reputation.csv",
        reputation_dir / plat / "results" / f"{plat}_{comm}_user_daily_reputation.parquet",
        reputation_dir / plat / "results" / f"{plat}_{comm}_user_daily_reputation.csv",
    ]

    for path in candidates:
        if path.exists():
            logging.info(f"Found reputation file: {path}")
            return path

    logging.warning(
        f"No reputation file found for {platform}/{community}. "
        f"Tried locations: {[str(c) for c in candidates]}"
    )
    return None


def load_reputation(reputation_file: Path) -> pd.DataFrame:
    """Load reputation data and ensure 'month' column exists."""
    if reputation_file.suffix == ".parquet":
        df = pd.read_parquet(reputation_file)
    else:
        df = pd.read_csv(reputation_file)

    logging.info(f"Loaded {len(df):,} reputation records")

    # Ensure month column exists
    if "month" not in df.columns:
        if "date" in df.columns:
            df["month"] = pd.to_datetime(
                df["date"], errors="coerce", utc=True
            ).dt.strftime("%Y-%m")
        elif "t_min" in df.columns and "day" in df.columns:
            # Reconstruct date from t_min + day offset
            tmin = pd.to_numeric(df["t_min"], errors="coerce")
            # Heuristic: ms vs s
            unit = "ms" if tmin.dropna().median() > 1e11 else "s"
            base = pd.to_datetime(tmin, unit=unit, utc=True, errors="coerce")
            df["date"] = base + pd.to_timedelta(
                pd.to_numeric(df["day"], errors="coerce").fillna(0).astype(int),
                unit="D",
            )
            df["month"] = pd.to_datetime(
                df["date"], errors="coerce", utc=True
            ).dt.strftime("%Y-%m")
        else:
            raise ValueError(
                "Reputation file missing both 'date' and ('t_min', 'day') columns"
            )

    df["user_id"] = df["user_id"].astype(str)
    df["month"] = df["month"].astype(str)

    return df


def aggregate_reputation_monthly(rep_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily reputation to monthly means per user.

    Uses active-only reputation (rep >= 1) following existing conventions.

    Returns DataFrame with columns:
        - user_id: str
        - month: str
        - mean_reputation: float (mean over active days)
        - active_days: int (number of days with rep >= 1)
    """
    # Filter to active reputation only
    active = rep_df[pd.to_numeric(rep_df["reputation"], errors="coerce") >= 1].copy()

    # Aggregate per user-month
    monthly = active.groupby(["user_id", "month"], as_index=False).agg(
        mean_reputation=("reputation", "mean"),
        active_days=("reputation", "count"),  # count of active days
    )

    logging.info(
        f"Aggregated reputation to {len(monthly):,} user-month records "
        f"({monthly['user_id'].nunique():,} users with active reputation)"
    )

    return monthly


def merge_metrics(
    behavioral: pd.DataFrame,
    reputation: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Merge behavioral and reputation metrics on user_id and month."""
    if reputation is None or reputation.empty:
        logging.warning("No reputation data to merge; proceeding without reputation")
        result = behavioral.copy()
        result["mean_reputation"] = float("nan")
        result["active_days"] = 0
        return result

    result = behavioral.merge(
        reputation,
        on=["user_id", "month"],
        how="left",
    )

    # Fill missing reputation with NaN
    result["mean_reputation"] = result["mean_reputation"].fillna(float("nan"))
    result["active_days"] = result["active_days"].fillna(0).astype(int)

    logging.info(
        f"Merged metrics: {len(result):,} user-month records, "
        f"{result['mean_reputation'].notna().sum():,} with reputation data"
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

    logging.info(f"Processing {platform}/{community}")

    # Build behavioral metrics
    pq_path = parquet_path(args.data_dir, platform, community)
    behavioral = build_user_month_metrics(pq_path)

    # Load and aggregate reputation
    rep_file = find_reputation_file(args.reputation_dir, platform, community)
    if rep_file:
        rep_daily = load_reputation(rep_file)
        rep_monthly = aggregate_reputation_monthly(rep_daily)
    else:
        rep_monthly = None

    # Merge
    user_month_metrics = merge_metrics(behavioral, rep_monthly)

    # Determine output path
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = REPO_ROOT / "results" / "basic" / platform / "results"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{platform}_{community}_user_month_metrics.parquet"

    # Save
    user_month_metrics.to_parquet(output_file, index=False)
    logging.info(f"Wrote {output_file} ({len(user_month_metrics):,} rows)")

    # Summary stats
    logging.info("=" * 60)
    logging.info("Summary Statistics:")
    logging.info(f"  Total user-months: {len(user_month_metrics):,}")
    logging.info(f"  Unique users: {user_month_metrics['user_id'].nunique():,}")
    logging.info(f"  Months covered: {user_month_metrics['month'].nunique()}")
    logging.info(f"  Date range: {user_month_metrics['month'].min()} to {user_month_metrics['month'].max()}")
    logging.info(f"  Mean toxicity: {user_month_metrics['mean_toxicity'].mean():.4f}")
    logging.info(f"  Mean VADER sentiment: {user_month_metrics['mean_vader'].mean():.4f}")
    logging.info(f"  Mean reputation (active): {user_month_metrics['mean_reputation'].mean():.4f}")
    logging.info("=" * 60)


if __name__ == "__main__":
    main()
