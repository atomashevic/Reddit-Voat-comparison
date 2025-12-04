#!/usr/bin/env python3
"""Aggregate metrics across all communities (weighted by active users).

Computes user-weighted averages for:
- E-I Index (Voat)
- Degree Assortativity (Voat)
- Mean Degree (Voat)
- Toxicity (Voat) - for overlay
- Reputation Mean and Median (Voat) - for active users (rep >= 1)
"""

import argparse
import logging
from pathlib import Path
from typing import List

import pandas as pd
import numpy as np

# Hardcoded list of communities to include
COMMUNITIES = ["funny", "gaming", "technology", "videos", "gifs", "pics"]


def load_community_data(results_root: Path, community: str) -> pd.DataFrame:
    """Load monthly metrics and partition metrics for a community."""
    # Load merged monthly metrics (contains degree, assortativity, toxicity, active users, ei_index)
    monthly_path = results_root / "compare" / community / f"{community}_monthly_metrics.csv"
    if not monthly_path.exists():
        logging.warning(f"Missing monthly metrics for {community}: {monthly_path}")
        return pd.DataFrame()

    df = pd.read_csv(monthly_path)
    df["month"] = df["month"].astype(str)

    # Load Voat monthly aggregates (contains reputation_mean, reputation_median, rep_active_users)
    voat_agg_path = results_root / "voat" / community / f"voat_{community}_monthly_aggregates.csv"
    if voat_agg_path.exists():
        voat_df = pd.read_csv(voat_agg_path)
        voat_df["month"] = voat_df["month"].astype(str)
        # Merge reputation columns
        rep_cols = ["month"]
        if "reputation_mean" in voat_df.columns:
            rep_cols.append("reputation_mean")
        if "reputation_median" in voat_df.columns:
            rep_cols.append("reputation_median")
        if "rep_active_users" in voat_df.columns:
            rep_cols.append("rep_active_users")
        if len(rep_cols) > 1:
            df = df.merge(voat_df[rep_cols], on="month", how="left", suffixes=("", "_voat_agg"))
            # Rename to voat-specific names
            if "reputation_mean" in df.columns:
                df = df.rename(columns={"reputation_mean": "reputation_mean_voat_agg"})
            if "reputation_median" in df.columns:
                df = df.rename(columns={"reputation_median": "reputation_median_voat"})
            if "rep_active_users" in df.columns:
                df = df.rename(columns={"rep_active_users": "rep_active_users_voat"})
    else:
        logging.warning(f"Missing Voat aggregates for {community}: {voat_agg_path}")

    df["community"] = community
    return df


def compute_weighted_average(df: pd.DataFrame, metric_col: str, weight_col: str) -> pd.Series:
    """Compute weighted average per month."""
    def weighted_mean(x):
        d = x[metric_col]
        w = x[weight_col]
        mask = d.notna() & w.notna()
        if not mask.any():
            return np.nan
        
        weights = w[mask]
        if weights.sum() == 0:
            return np.nan
            
        return np.average(d[mask], weights=weights)

    # Groupby month and apply. To avoid FutureWarning and ensure correct behavior,
    # we can just use the full dataframe as apply input but should be careful.
    # The warning suggests include_groups=False, but we need the columns inside.
    # We can ignore the warning for now or better: explicit select.
    
    # Fix: Select only needed columns + grouping key
    subset = df[["month", metric_col, weight_col]]
    return subset.groupby("month")[subset.columns].apply(weighted_mean)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", type=Path, default=Path("results"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/global"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    all_data = []
    for comm in COMMUNITIES:
        df = load_community_data(args.results_root, comm)
        if not df.empty:
            all_data.append(df)

    if not all_data:
        logging.error("No data found for any community.")
        return

    full_df = pd.concat(all_data, ignore_index=True)
    
    # Ensure month is datetime for sorting (but groupby uses string usually)
    # We keep it as string for groupby, then convert later
    
    # Metrics to aggregate (Voat) - use active_users_voat for general metrics,
    # rep_active_users_voat (users with rep >= 1) for reputation metrics
    metrics = {
        "ei_index": "active_users_voat",
        "degree_assortativity_voat": "active_users_voat",
        "mean_degree_voat": "active_users_voat",
        "toxicity_mean_voat": "active_users_voat",
        "reputation_mean_voat_agg": "rep_active_users_voat",
        "reputation_median_voat": "rep_active_users_voat",
    }
    
    # Also compute sum of active users
    total_users = full_df.groupby("month")["active_users_voat"].sum().rename("total_active_users_voat")
    
    agg_dfs = [total_users]
    
    for metric, weight in metrics.items():
        if metric in full_df.columns and weight in full_df.columns:
            logging.info(f"Aggregating {metric} weighted by {weight}")
            agg = compute_weighted_average(full_df, metric, weight).rename(metric)
            agg_dfs.append(agg)
        else:
            logging.warning(f"Metric {metric} or weight {weight} missing in columns")

    result = pd.concat(agg_dfs, axis=1).reset_index()
    result = result.sort_values("month")

    # Compute q90 for degree (Optional per user request: "Average (or q90) degree... Optional overlay... q90")
    # We don't have individual user degrees here, so we can't compute true global q90.
    # We can only compute weighted average of community q90s if we had them.
    # But we don't have q90 in the monthly metrics CSV (only mean).
    # So we skip q90 unless we calculate it upstream.
    # The user said "Average (or q90) degree". We stick to Average.

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / "voat_global_aggregate.csv"
    result.to_csv(out_path, index=False)
    logging.info(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

