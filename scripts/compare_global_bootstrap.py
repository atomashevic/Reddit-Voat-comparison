#!/usr/bin/env python3
"""Build Reddit-at-Voat-scale bootstrap distributions for global (non-CP) metrics.

For each Voat month, creates activity-matched bootstrap samples from Reddit's population.
Unlike the core-periphery version, this operates at the global community level.
"""

import argparse
import logging
import math
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]

ACTIVITY_BINS: Sequence[Tuple[int, Optional[int]]] = ((1, 1), (2, 2), (3, 5), (6, 10), (11, 20), (21, None))
METRICS = ["toxicity_mean", "vader_mean", "textblob_mean", "subjectivity_mean", "reputation_mean"]

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--basic-dir", type=Path, default=REPO_ROOT / "results" / "basic")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--bootstrap-iterations", type=int, default=40)
    parser.add_argument("--seed", type=int, default=2025)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()

def activity_bin(count: float) -> str:
    value = int(count) if pd.notna(count) else 0
    for low, high in ACTIVITY_BINS:
        if high is None and value >= low: return f"{low}+"
        if high is not None and low <= value <= high:
            return f"{low}" if low == high else f"{low}-{high}"
    return "0"

def load_user_month_metrics(basic_dir, platform, community):
    path = basic_dir / platform / "results" / f"{platform}_{community}_user_month_metrics.parquet"
    if not path.exists():
        raise FileNotFoundError(f"User-month metrics not found: {path}")
    df = pd.read_parquet(path)
    df["activity_bin"] = df["activity_count"].apply(activity_bin)
    df["platform"] = platform
    df["community"] = community.lower()
    logging.info(f"Loaded {len(df):,} user-month records for {platform}/{community}")
    return df

def aggregate_monthly_metrics(user_month_df):
    agg = user_month_df.groupby(["platform", "community", "month"], as_index=False).agg(
        active_users=("user_id", "nunique"),
        toxicity_mean=("mean_toxicity", "mean"), toxicity_std=("mean_toxicity", "std"),
        vader_mean=("mean_vader", "mean"), vader_std=("mean_vader", "std"),
        textblob_mean=("mean_textblob", "mean"), textblob_std=("mean_textblob", "std"),
        subjectivity_mean=("mean_subjectivity", "mean"), subjectivity_std=("mean_subjectivity", "std"),
        reputation_mean=("mean_reputation", "mean"), reputation_std=("mean_reputation", "std"),
        total_activity=("activity_count", "sum"))
    agg["month_dt"] = pd.to_datetime(agg["month"] + "-01")
    return agg.sort_values("month_dt").drop(columns=["month_dt"])

def _fallback_activity_bin(bin_name: str) -> Iterable[str]:
    labels = [activity_bin(high if high is not None else low) for low, high in ACTIVITY_BINS]
    if bin_name not in labels:
        yield from labels
        return
    idx = labels.index(bin_name)
    yield labels[idx]
    left, right = idx - 1, idx + 1
    while left >= 0 or right < len(labels):
        if left >= 0:
            yield labels[left]
            left -= 1
        if right < len(labels):
            yield labels[right]
            right += 1

def bootstrap_reddit_at_voat_scale(voat_user_month, reddit_user_month, iterations, rng):
    results: List[Dict] = []
    reddit_by_month: Dict = {}
    for (community, month), frame in reddit_user_month.groupby(["community", "month"], observed=True, sort=False):
        reddit_by_month[(community, month)] = frame.reset_index(drop=True)

    for (community, month), voat_slice in voat_user_month.groupby(["community", "month"], observed=True, sort=False):
        reddit_slice = reddit_by_month.get((community, month))
        if reddit_slice is None or reddit_slice.empty:
            continue

        reddit_slice = reddit_slice.copy()
        reddit_slice["activity_bin"] = reddit_slice["activity_bin"].astype(str)
        voat_slice = voat_slice.copy()
        voat_slice["activity_bin"] = voat_slice["activity_bin"].astype(str)
        bin_counts = voat_slice["activity_bin"].value_counts().to_dict()

        reddit_bins: Dict = {}
        for activity_value, subframe in reddit_slice.groupby("activity_bin", observed=True, sort=False):
            reddit_bins[str(activity_value)] = subframe.reset_index(drop=True)

        for iteration in range(iterations):
            sampled_segments: List = []
            unable = False
            for bin_name, target_count in bin_counts.items():
                if target_count <= 0: continue
                chosen_df = None
                for candidate_bin in _fallback_activity_bin(bin_name):
                    candidate_df = reddit_bins.get(candidate_bin)
                    if candidate_df is not None and not candidate_df.empty:
                        chosen_df = candidate_df
                        break
                if chosen_df is None:
                    unable = True
                    break
                indices = rng.integers(0, len(chosen_df), size=target_count)
                sampled_segments.append(chosen_df.iloc[indices])

            if unable or not sampled_segments: continue

            sample = pd.concat(sampled_segments, ignore_index=True)
            sample_size = len(sample)
            if sample_size == 0: continue

            for metric in METRICS:
                if metric not in sample.columns: continue
                values = pd.to_numeric(sample[metric], errors="coerce")
                mean_value = values.mean() if not values.empty else math.nan
                results.append({"platform": "reddit_voat_scale", "community": community,
                               "month": month, "metric": metric, "iteration": iteration,
                               "value": mean_value, "sample_size": sample_size})

    return pd.DataFrame(results)

def summarize_bootstrap(bootstrap_df):
    if bootstrap_df.empty:
        return pd.DataFrame(columns=["platform", "community", "month", "metric", "percentile", "value"])

    percentiles = [5, 25, 50, 75, 95]
    summary_records: List = []

    for (platform, community, month, metric), frame in bootstrap_df.groupby(["platform", "community", "month", "metric"], observed=True, sort=False):
        values = frame["value"].dropna()
        if values.empty: continue
        quantiles = np.percentile(values, percentiles)
        for pct, val in zip(percentiles, quantiles):
            summary_records.append({"platform": platform, "community": community,
                                   "month": month, "metric": metric,
                                   "percentile": pct, "value": val})

    return pd.DataFrame(summary_records)

def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()),
                       format="%(asctime)s [%(levelname)s] %(message)s")

    community = args.community.lower()
    rng = np.random.default_rng(args.seed)

    logging.info(f"Processing community: {community}")

    reddit_user = load_user_month_metrics(args.basic_dir, "reddit", community)
    voat_user = load_user_month_metrics(args.basic_dir, "voat", community)

    reddit_monthly = aggregate_monthly_metrics(reddit_user)
    voat_monthly = aggregate_monthly_metrics(voat_user)

    combined_monthly = pd.concat([reddit_monthly, voat_monthly], ignore_index=True)
    combined_monthly = combined_monthly.sort_values(["platform", "month"])

    logging.info("Generating bootstrap samples...")
    bootstrap_samples = bootstrap_reddit_at_voat_scale(voat_user, reddit_user, args.bootstrap_iterations, rng)
    logging.info(f"Generated {len(bootstrap_samples):,} bootstrap samples")

    bootstrap_summary = summarize_bootstrap(bootstrap_samples)
    logging.info(f"Summarized to {len(bootstrap_summary):,} percentile records")

    output_dir = args.output_dir if args.output_dir else REPO_ROOT / "results" / "basic" / "compare" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    combined_monthly.to_csv(output_dir / f"{community}_global_monthly_metrics.csv", index=False)
    bootstrap_samples.to_csv(output_dir / f"{community}_global_bootstrap_samples.csv", index=False)
    bootstrap_summary.to_csv(output_dir / f"{community}_global_bootstrap_summary.csv", index=False)

    logging.info(f"Wrote outputs to {output_dir}")

if __name__ == "__main__":
    main()
