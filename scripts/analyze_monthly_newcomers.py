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
from scripts.migration_utils import METRICS

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--basic-dir", type=Path, required=True)
    parser.add_argument("--networks-dir", type=Path, required=True)
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
            
        # Densities
        def density(nodes):
            k = G_sub.subgraph(nodes)
            return nx.density(k)
            
        return {
            "n_newcomers": n_new,
            "n_existing": n_old,
            "modularity": modularity,
            "assortativity": assortativity,
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
    metrics_path = args.basic_dir / "voat" / "results" / f"voat_{args.community}_user_month_metrics.parquet"
    labels_path = args.basic_dir / "voat" / "results" / f"voat_{args.community}_newcomer_labels.csv"
    
    if not labels_path.exists():
        # Try output dir if passed
        if args.output_dir:
             labels_path = args.output_dir / f"voat_{args.community}_newcomer_labels.csv"
    
    if not metrics_path.exists() or not labels_path.exists():
        logging.error("Missing input files (metrics or labels)")
        return

    # Load Data
    metrics = pd.read_parquet(metrics_path)
    labels_df = pd.read_csv(labels_path)
    
    # Check string match
    metrics["user_id"] = metrics["user_id"].astype(str)
    labels_df["user_id"] = labels_df["user_id"].astype(str)
    
    # Merge Labels
    merged = metrics.merge(labels_df, on="user_id", how="inner")
    
    # 1. Behavioral Analysis
    behavioral = merged.groupby(["month", "label"]).agg({
        "toxicity_toxigen": "mean", # Note: col name in user_month is 'mean_toxicity' usually?
        # Wait, build_global_monthly_metrics outputs: mean_toxicity, mean_vader, etc.
        "mean_toxicity": "mean",
        "mean_vader": "mean",
        "mean_textblob": "mean",
        "mean_subjectivity": "mean",
        "mean_reputation": "mean",
        "user_id": "count" # Activity/User count
    }).reset_index()
    
    # Pivot to have one row per month with columns like toxicity_newcomer, toxicity_existing
    pivoted = behavioral.pivot(index="month", columns="label")
    # Flatten
    pivoted.columns = [f"{col[0]}_{col[1]}" for col in pivoted.columns]
    pivoted = pivoted.reset_index()
    
    # 2. Network Analysis
    # Need labels dict
    labels_map = dict(zip(labels_df["user_id"], labels_df["label"]))
    
    net_results = []
    # Iterate months present in data
    months = sorted(merged["month"].unique())
    
    net_dir = args.networks_dir / "voat" / f"{args.community}_monthly"
    
    if net_dir.exists():
        for month in months:
            # Edge file: community_YYYY-MM.txt
            edge_file = net_dir / f"{args.community}_{month}.txt"
            res = compute_network_partition_metrics(edge_file, labels_map)
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

