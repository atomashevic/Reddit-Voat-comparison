#!/usr/bin/env python3
"""
Compute correlations between reputation, toxicity, and sentiment time series.

The script scans existing monthly aggregated outputs for both Voat and Reddit,
aligns the metrics on a per-community basis, and writes a CSV summarising the
pairwise Pearson correlations between:
    * mean reputation (weighted across core/periphery active users)
    * mean toxicity (Toxigen)
    * mean sentiment (VADER and TextBlob)

By default the script expects the repository results layout and writes the
summary under results/basic/compare/results. Use the CLI options to override
inputs/outputs if needed.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd


REPUTATION_SUFFIX = "_cp_monthly_reputation.csv"


@dataclass
class MetricTimeseries:
    community: str
    platform: str
    data: pd.DataFrame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute correlations between reputation, toxicity, and sentiment time series "
        "for Voat and Reddit communities."
    )
    parser.add_argument(
        "--reputation-dir",
        type=Path,
        default=Path("results/reputation"),
        help="Directory containing reputation CSV outputs (default: results/reputation)",
    )
    parser.add_argument(
        "--basic-dir",
        type=Path,
        default=Path("results/basic"),
        help="Directory containing basic monthly platform community CSV outputs "
        "(default: results/basic)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/basic/compare/results/metric_correlations.csv"),
        help="Destination CSV for correlation summary "
        "(default: results/basic/compare/results/metric_correlations.csv)",
    )
    return parser.parse_args()


def weighted_mean_reputation(df: pd.DataFrame) -> pd.Series:
    core_users = df["core_active_users"].fillna(0.0)
    periphery_users = df["periphery_active_users"].fillna(0.0)
    total_users = core_users + periphery_users

    weighted_sum = (
        df["core_mean_rep_active"].fillna(0.0) * core_users
        + df["periphery_mean_rep_active"].fillna(0.0) * periphery_users
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_rep = weighted_sum / total_users.replace({0.0: np.nan})
    mean_rep[total_users == 0] = np.nan
    return mean_rep


def load_reputation_timeseries(reputation_dir: Path, platform: str) -> List[MetricTimeseries]:
    platform_dir = reputation_dir / platform / "results"
    prefix = f"{platform}_"
    if not platform_dir.exists():
        return []

    series: List[MetricTimeseries] = []
    for csv_path in sorted(platform_dir.glob(f"{prefix}*{REPUTATION_SUFFIX}")):
        community = csv_path.stem
        if not community.startswith(prefix) or not community.endswith(REPUTATION_SUFFIX[:-4]):
            # Fallback in case glob matches unexpected files.
            community = csv_path.stem.removeprefix(prefix).removesuffix(REPUTATION_SUFFIX[:-4])
        else:
            community = community[len(prefix) : -len(REPUTATION_SUFFIX[:-4])]

        community = community.strip("_")
        if not community:
            continue

        rep_df = pd.read_csv(csv_path)
        if "month" not in rep_df.columns:
            continue
        rep_df = rep_df.copy()
        rep_df["mean_reputation"] = weighted_mean_reputation(rep_df)
        rep_df = rep_df[["month", "mean_reputation"]]
        series.append(MetricTimeseries(community=community, platform=platform, data=rep_df))
    return series


def load_basic_metrics(basic_dir: Path, platform: str) -> pd.DataFrame:
    csv_path = basic_dir / platform / "results" / "monthly_platform_community.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing basic metrics file: {csv_path}")
    df = pd.read_csv(csv_path)
    expected = [
        "month",
        "community",
        "mean_sentiment_vader",
        "mean_sentiment_textblob",
        "mean_toxicity_toxigen",
    ]
    missing = [col for col in expected if col not in df.columns]
    if missing:
        raise ValueError(f"Basic metrics file {csv_path} is missing columns: {missing}")
    return df


def safe_corr(df: pd.DataFrame, col_a: str, col_b: str) -> float:
    sub = df[[col_a, col_b]].dropna()
    if len(sub) < 2:
        return math.nan
    if sub[col_a].nunique() < 2 or sub[col_b].nunique() < 2:
        return math.nan
    return float(sub[col_a].corr(sub[col_b]))


def compute_correlations(
    reputation_series: Iterable[MetricTimeseries],
    basic_metrics: pd.DataFrame,
) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    for series in reputation_series:
        community_mask = basic_metrics["community"] == series.community
        community_df = basic_metrics.loc[community_mask].copy()
        if community_df.empty:
            # Try case-insensitive match if necessary.
            community_mask = basic_metrics["community"].str.lower() == series.community.lower()
            community_df = basic_metrics.loc[community_mask].copy()
            if community_df.empty:
                continue

        merged = pd.merge(series.data, community_df, on="month", how="inner", validate="one_to_one")
        merged = merged.rename(
            columns={
                "mean_toxicity_toxigen": "mean_toxicity",
                "mean_sentiment_vader": "mean_sentiment_vader",
                "mean_sentiment_textblob": "mean_sentiment_textblob",
            }
        )

        merged_metrics = merged[
            ["mean_reputation", "mean_toxicity", "mean_sentiment_vader", "mean_sentiment_textblob"]
        ]

        result_row: Dict[str, object] = {
            "platform": series.platform,
            "community": series.community,
            "num_months_overlap": len(merged),
            "num_months_all_metrics": len(merged_metrics.dropna()),
        }
        result_row["corr_rep_toxicity"] = safe_corr(merged_metrics, "mean_reputation", "mean_toxicity")
        result_row["corr_rep_sentiment_vader"] = safe_corr(
            merged_metrics, "mean_reputation", "mean_sentiment_vader"
        )
        result_row["corr_rep_sentiment_textblob"] = safe_corr(
            merged_metrics, "mean_reputation", "mean_sentiment_textblob"
        )
        result_row["corr_toxicity_sentiment_vader"] = safe_corr(
            merged_metrics, "mean_toxicity", "mean_sentiment_vader"
        )
        result_row["corr_toxicity_sentiment_textblob"] = safe_corr(
            merged_metrics, "mean_toxicity", "mean_sentiment_textblob"
        )
        result_row["corr_sentiment_vader_textblob"] = safe_corr(
            merged_metrics, "mean_sentiment_vader", "mean_sentiment_textblob"
        )

        results.append(result_row)
    return results


def ensure_output_directory(path: Path) -> None:
    output_dir = path.parent
    output_dir.mkdir(parents=True, exist_ok=True)


def main() -> None:
    args = parse_args()
    all_series: List[MetricTimeseries] = []
    basic_cache: Dict[str, pd.DataFrame] = {}

    for platform in ("voat", "reddit"):
        platform_series = load_reputation_timeseries(args.reputation_dir, platform)
        all_series.extend(platform_series)
        basic_cache[platform] = load_basic_metrics(args.basic_dir, platform)

    correlation_rows: List[Dict[str, object]] = []
    for platform in ("voat", "reddit"):
        platform_series = [s for s in all_series if s.platform == platform]
        platform_basic = basic_cache[platform]
        correlation_rows.extend(compute_correlations(platform_series, platform_basic))

    if not correlation_rows:
        raise RuntimeError("No correlations computed – check that input data is present.")

    summary_df = pd.DataFrame(correlation_rows)
    summary_df = summary_df.sort_values(["platform", "community"]).reset_index(drop=True)

    ensure_output_directory(args.output)
    summary_df.to_csv(args.output, index=False)


if __name__ == "__main__":
    main()
