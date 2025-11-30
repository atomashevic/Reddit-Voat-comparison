#!/usr/bin/env python3
"""Aggregate user-month metrics to community-month level without CP stratification."""

import argparse
import logging
from pathlib import Path
import pandas as pd
import duckdb

REPO_ROOT = Path(__file__).resolve().parents[1]

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--platform", required=True, choices=["reddit", "voat"])
    parser.add_argument("--basic-dir", type=Path, default=REPO_ROOT / "results" / "basic")
    parser.add_argument("--networks-dir", type=Path, default=REPO_ROOT / "results" / "networks")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--input-file", type=Path, default=None, help="Explicit path to input user-month parquet file")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()

def aggregate_with_duckdb(parquet_path):
    """Aggregate user-month metrics using DuckDB streaming."""
    if not parquet_path.exists():
        raise FileNotFoundError(f"User-month metrics not found: {parquet_path}")

    logging.info(f"Aggregating from {parquet_path} using DuckDB...")

    conn = duckdb.connect()
    try:
        # Detect whether reputation is present; older files may omit it
        cols = {row[0].lower() for row in conn.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{parquet_path.as_posix()}')"
        ).fetchall()}
        has_reputation = "mean_reputation" in cols

        reputation_select = """
            AVG(mean_reputation) AS reputation_mean,
            MEDIAN(mean_reputation) AS reputation_median,
            STDDEV(mean_reputation) AS reputation_std
        """ if has_reputation else """
            CAST(NULL AS DOUBLE) AS reputation_mean,
            CAST(NULL AS DOUBLE) AS reputation_median,
            CAST(NULL AS DOUBLE) AS reputation_std
        """
        rep_active_select = "COUNT(DISTINCT CASE WHEN mean_reputation > 1 THEN user_id END) AS rep_active_users" if has_reputation else "CAST(NULL AS BIGINT) AS rep_active_users"

        query = f"""
            SELECT
                month,
                COUNT(DISTINCT user_id) AS active_users,
                SUM(activity_count) AS total_activity,
                {rep_active_select},

                AVG(mean_toxicity) AS toxicity_mean,
                MEDIAN(mean_toxicity) AS toxicity_median,
                STDDEV(mean_toxicity) AS toxicity_std,

                AVG(mean_vader) AS vader_mean,
                MEDIAN(mean_vader) AS vader_median,
                STDDEV(mean_vader) AS vader_std,

                AVG(mean_textblob) AS textblob_mean,
                MEDIAN(mean_textblob) AS textblob_median,
                STDDEV(mean_textblob) AS textblob_std,

                AVG(mean_subjectivity) AS subjectivity_mean,
                MEDIAN(mean_subjectivity) AS subjectivity_median,
                STDDEV(mean_subjectivity) AS subjectivity_std,

                {reputation_select}
            FROM read_parquet('{parquet_path.as_posix()}')
            GROUP BY month
            ORDER BY month
        """

        df = conn.execute(query).df()
        logging.info(f"Aggregated {len(df)} monthly records")
        return df
    finally:
        conn.close()

def load_network_metrics(networks_dir, platform, community):
    # Look for network metrics in:
    # 1. {networks_dir}/{platform}/{community}/... (New structure)
    # 2. {networks_dir}/{platform}/results/... (Old structure)
    # 3. {networks_dir}/{platform}/... (Flattened)
    
    filename = f"{platform}_{community}_global_metrics.csv"
    candidates = [
        networks_dir / platform / community / filename,
        networks_dir / platform / "results" / filename,
        networks_dir / platform / filename,
    ]
    
    path = next((p for p in candidates if p.exists()), None)

    if path is None:
        logging.warning(f"Network metrics not found in candidates: {candidates}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    logging.info(f"Loaded {len(df)} network snapshots from {path}")
    return df

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
        # Ensure month is string for merge
        behavioral_df["month"] = behavioral_df["month"].astype(str)
        network_df["month"] = network_df["month"].astype(str)
        # Derive normalized clustering if not present in network metrics
        if "normalized_clustering" not in network_df.columns and {"mean_clustering", "er_expected_clustering"}.issubset(set(network_df.columns)):
            network_df["normalized_clustering"] = network_df["mean_clustering"] / network_df["er_expected_clustering"]

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
    
    if args.input_file:
        parquet_path = args.input_file
    else:
        parquet_path = args.basic_dir / platform / "results" / f"{platform}_{community}_user_month_metrics.parquet"
    
    behavioral_agg = aggregate_with_duckdb(parquet_path)
    network_df = load_network_metrics(args.networks_dir, platform, community)
    monthly_aggregates = merge_with_network_metrics(behavioral_agg, network_df, platform, community)
    
    output_dir = args.output_dir if args.output_dir else REPO_ROOT / "results" / "basic" / platform / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{platform}_{community}_monthly_aggregates.csv"
    
    monthly_aggregates.to_csv(output_file, index=False)
    logging.info(f"Wrote {output_file} ({len(monthly_aggregates)} rows)")

if __name__ == "__main__":
    main()
