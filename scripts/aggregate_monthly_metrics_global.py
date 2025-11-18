#!/usr/bin/env python3
"""Aggregate user-month metrics to community-month level without CP stratification."""

import argparse
import logging
from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--platform", required=True, choices=["reddit", "voat"])
    parser.add_argument("--basic-dir", type=Path, default=REPO_ROOT / "results" / "basic")
    parser.add_argument("--networks-dir", type=Path, default=REPO_ROOT / "results" / "networks")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()

def load_user_month_metrics(basic_dir, platform, community):
    path = basic_dir / platform / "results" / f"{platform}_{community}_user_month_metrics.parquet"
    if not path.exists():
        raise FileNotFoundError(f"User-month metrics not found: {path}")
    df = pd.read_parquet(path)
    logging.info(f"Loaded {len(df):,} user-month records")
    return df

def load_network_metrics(networks_dir, platform, community):
    path = networks_dir / platform / "results" / f"{platform}_{community}_global_metrics.csv"
    if not path.exists():
        logging.warning(f"Network metrics not found: {path}")
        return pd.DataFrame()
    df = pd.read_csv(path)
    logging.info(f"Loaded {len(df)} network snapshots")
    return df

def aggregate_behavioral_metrics(user_month_df):
    grouped = user_month_df.groupby("month")
    agg = grouped.agg({
        "user_id": "nunique",
        "activity_count": "sum",
        "mean_toxicity": ["mean", "median", "std"],
        "mean_vader": ["mean", "median", "std"],
        "mean_textblob": ["mean", "median", "std"],
        "mean_subjectivity": ["mean", "median", "std"],
        "mean_reputation": ["mean", "median", "std"],
    })
    agg.columns = ["_".join(col).strip("_") if col[1] else col[0] for col in agg.columns.values]
    agg = agg.rename(columns={
        "user_id_nunique": "active_users", "activity_count_sum": "total_activity",
        "mean_toxicity_mean": "toxicity_mean", "mean_toxicity_median": "toxicity_median", "mean_toxicity_std": "toxicity_std",
        "mean_vader_mean": "vader_mean", "mean_vader_median": "vader_median", "mean_vader_std": "vader_std",
        "mean_textblob_mean": "textblob_mean", "mean_textblob_median": "textblob_median", "mean_textblob_std": "textblob_std",
        "mean_subjectivity_mean": "subjectivity_mean", "mean_subjectivity_median": "subjectivity_median", "mean_subjectivity_std": "subjectivity_std",
        "mean_reputation_mean": "reputation_mean", "mean_reputation_median": "reputation_median", "mean_reputation_std": "reputation_std",
    })
    return agg.reset_index()

def merge_with_network_metrics(behavioral_df, network_df, platform, community):
    if network_df.empty:
        result = behavioral_df.copy()
        result["platform"] = platform
        result["community"] = community
        for col in ["n_nodes", "n_edges", "mean_degree", "median_degree", "std_degree", "degree_heterogeneity",
                    "mean_clustering", "er_expected_clustering", "normalized_clustering", "avg_shortest_path",
                    "diameter", "giant_component_size", "giant_component_fraction", "density", "degree_assortativity"]:
            result[col] = float("nan")
    else:
        result = behavioral_df.merge(network_df.drop(columns=["platform", "community"], errors="ignore"), on="month", how="left")
        result["platform"] = platform
        result["community"] = community
    cols = ["platform", "community", "month"]
    other_cols = [c for c in result.columns if c not in cols]
    return result[cols + other_cols]

def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s [%(levelname)s] %(message)s")
    
    platform = args.platform.lower()
    community = args.community.lower()
    
    user_month_df = load_user_month_metrics(args.basic_dir, platform, community)
    behavioral_agg = aggregate_behavioral_metrics(user_month_df)
    network_df = load_network_metrics(args.networks_dir, platform, community)
    monthly_aggregates = merge_with_network_metrics(behavioral_agg, network_df, platform, community)
    
    output_dir = args.output_dir if args.output_dir else REPO_ROOT / "results" / "basic" / platform / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{platform}_{community}_monthly_aggregates.csv"
    
    monthly_aggregates.to_csv(output_file, index=False)
    logging.info(f"Wrote {output_file} ({len(monthly_aggregates)} rows)")

if __name__ == "__main__":
    main()
