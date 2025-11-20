#!/usr/bin/env python3
"""Analyze monthly dynamics of Newcomers vs Existing users on Voat.

Computes:
1. Behavioral metrics (mean toxicity, sentiment, etc.) per group per month.
2. Network partition metrics (modularity, density, assortativity) per month.
"""

import argparse
import logging
import sys
import os
from pathlib import Path
from typing import Dict

import pandas as pd
import networkx as nx
import numpy as np

# Add scripts dir to path to import utils
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import METRICS, newcomer_label_for_month, EVENTS

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--basic-dir", type=Path, required=True)
    parser.add_argument("--networks-dir", type=Path, required=True)
    parser.add_argument("--voat-metrics", type=Path, default=None, help="Explicit path to Voat metrics parquet")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()

def compute_network_partition_metrics(edge_file: Path, labels: Dict[str, str]) -> Dict[str, float]:
    """Compute modularity and densities for the Newcomer/Existing partition."""
    if not edge_file.exists():
        return {}
        
    try:
        # Read edges
        edges = pd.read_csv(edge_file, sep=r"\s+", names=["src", "dst"], dtype=str)
        if edges.empty:
            return {}
            
        G = nx.from_pandas_edgelist(edges, "src", "dst")
        
        # Filter graph to nodes present in labels
        valid_nodes = [n for n in G.nodes() if n in labels]
        if not valid_nodes:
            return {}
            
        G_sub = G.subgraph(valid_nodes)
        
        # Partition
        nodes_new = [n for n in G_sub.nodes() if labels[n] == "newcomer"]
        nodes_old = [n for n in G_sub.nodes() if labels[n] == "existing"]
        
        n_new = len(nodes_new)
        n_old = len(nodes_old)
        
        if n_new == 0 or n_old == 0:
            # Cannot compute partition metrics if one group is missing
            return {
                "n_newcomers": n_new,
                "n_existing": n_old,
                "modularity": float("nan"),
                "assortativity": float("nan")
            }
            
        # Modularity
        partition = [{"newcomer": nodes_new, "existing": nodes_old}]
        # Creating partition dict for nx (node -> 0/1)
        part_map = {n: 0 for n in nodes_new}
        part_map.update({n: 1 for n in nodes_old})
        
        # Modularity
        try:
            # Communities format: list of sets
            communities = [set(nodes_new), set(nodes_old)]
            modularity = nx.community.modularity(G_sub, communities)
        except:
            modularity = float("nan")
            
        # Attribute Assortativity
        nx.set_node_attributes(G_sub, part_map, "group")
        try:
            assortativity = nx.attribute_assortativity_coefficient(G_sub, "group")
        except:
            assortativity = float("nan")

        # Mixing matrix fractions and EI index
        total_edges = G_sub.number_of_edges()
        ei_index = float("nan")
        if total_edges > 0:
            ne_edges = sum(1 for u, v in G_sub.edges() if labels.get(u) != labels.get(v))
            same_edges = total_edges - ne_edges
            ei_index = (ne_edges - same_edges) / total_edges
            
        # Densities
        def density(nodes):
            k = G_sub.subgraph(nodes)
            return nx.density(k)
            
        return {
            "n_newcomers": n_new,
            "n_existing": n_old,
            "modularity": modularity,
            "assortativity": assortativity,
            "ei_index": ei_index,
            "density_newcomer": density(nodes_new),
            "density_existing": density(nodes_old)
        }
        
    except Exception as e:
        logging.warning(f"Failed network metrics for {edge_file}: {e}")
        return {}

def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    
    # Paths
    if args.voat_metrics:
        metrics_path = args.voat_metrics
    else:
        filename = f"voat_{args.community}_user_month_metrics.parquet"
        metrics_candidates = [
            args.basic_dir / args.community / "voat" / filename,              # alt layout
            args.basic_dir / args.community / "voat" / "results" / filename,  # alt with results/
            args.basic_dir / "voat" / "results" / filename,                  # canonical basic
            args.basic_dir / "voat" / filename,                              # flattened alt
            Path("results/basic") / "voat" / "results" / filename,           # fallback basic
        ]
        metrics_path = next((p for p in metrics_candidates if p.exists()), None)

    labels_candidates = [
        args.basic_dir / args.community / "voat" / f"voat_{args.community}_newcomer_labels.csv",
        args.basic_dir / args.community / "voat" / "results" / f"voat_{args.community}_newcomer_labels.csv",
        args.basic_dir / "voat" / "results" / f"voat_{args.community}_newcomer_labels.csv",
        args.basic_dir / "voat" / f"voat_{args.community}_newcomer_labels.csv",
    ]
    if args.output_dir:
        labels_candidates.append(args.output_dir / f"voat_{args.community}_newcomer_labels.csv")

    labels_path = next((p for p in labels_candidates if p.exists()), None)

    if metrics_path is None or labels_path is None:
        logging.error(f"Missing input files (metrics or labels). Tried metrics: {metrics_candidates}, labels: {labels_candidates}")
        return

    # Load Data
    metrics = pd.read_parquet(metrics_path)
    # Ensure reputation column exists even if upstream skipped reputation merge
    if "mean_reputation" not in metrics.columns:
        metrics["mean_reputation"] = np.nan
    labels_df = pd.read_csv(labels_path)
    
    # Check string match
    metrics["user_id"] = metrics["user_id"].astype(str)
    labels_df["user_id"] = labels_df["user_id"].astype(str)
    if "first_month" in labels_df.columns:
        labels_df["first_seen_dt"] = pd.to_datetime(labels_df["first_month"])
    else:
        labels_df["first_seen_dt"] = pd.NaT
    
    # Merge Labels
    merged = metrics.merge(labels_df, on="user_id", how="inner", suffixes=("", "_label"))
    
    # Dynamic labels per month based on first_seen and month
    merged["month_dt"] = pd.to_datetime(merged["month"] + "-01")
    merged["first_seen_dt"] = merged["first_seen_dt"].fillna(merged.get("first_month", merged["month_dt"]))
    merged["label"] = merged.apply(lambda row: newcomer_label_for_month(row["first_seen_dt"], row["month_dt"]), axis=1)
    
    # 1. Behavioral Analysis (only aggregate columns that exist)
    agg_fields = {
        "mean_toxicity": "mean",
        "mean_vader": "mean",
        "mean_textblob": "mean",
        "mean_subjectivity": "mean",
        "mean_reputation": "mean",
        "user_id": "count",  # Activity/User count
    }
    available_fields = {col: func for col, func in agg_fields.items() if col in merged.columns}

    behavioral = merged.groupby(["month", "label"]).agg(available_fields).reset_index()
    
    # Pivot to have one row per month with columns like toxicity_newcomer, toxicity_existing
    pivoted = behavioral.pivot(index="month", columns="label")
    # Flatten
    pivoted.columns = [f"{col[0]}_{col[1]}" for col in pivoted.columns]
    pivoted = pivoted.reset_index()
    
    # 2. Network Analysis
    # Need month-specific labels dict
    first_seen_map = dict(zip(labels_df["user_id"], labels_df["first_seen_dt"]))
    
    net_results = []
    # Iterate months present in data
    months = sorted(merged["month"].unique())
    
    net_dir = args.networks_dir / "voat" / f"{args.community}_monthly"
    
    if net_dir.exists():
        for month in months:
            # Edge file: community_YYYY-MM.txt
            edge_file = net_dir / f"{args.community}_{month}.txt"
            month_dt = pd.to_datetime(month + "-01")
            labels_map_month = {uid: newcomer_label_for_month(fs, month_dt) for uid, fs in first_seen_map.items()}
            res = compute_network_partition_metrics(edge_file, labels_map_month)
            res["month"] = month
            net_results.append(res)
    else:
        logging.warning(f"Network directory not found: {net_dir}")
        
    # Combine
    if net_results:
        net_df = pd.DataFrame(net_results)
        final = pd.merge(pivoted, net_df, on="month", how="left")
    else:
        final = pivoted
        
    output_dir = args.output_dir if args.output_dir else args.basic_dir / "voat" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"voat_{args.community}_monthly_newcomer_analysis.csv"
    final.to_csv(out_path, index=False)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
