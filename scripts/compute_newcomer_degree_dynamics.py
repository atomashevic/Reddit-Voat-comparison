#!/usr/bin/env python3
"""Compute newcomer degree dynamics metrics for Voat communities.

Calculates three key metrics per month capturing newcomer integration patterns:
1. Newcomer Degree Gini - Inequality in degree distribution among newcomers
2. Newcomer Hub Rate - Fraction of newcomers exceeding P90 of existing user degrees
3. Degree Share / Population Share - Whether newcomers are over/under-represented

Uses migration-cohort newcomer definition from migration_utils.newcomer_label_for_month().
"""

import argparse
import gc
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import networkx as nx

# Thread control
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from migration_utils import EVENTS, EVENT_LABELS, newcomer_label_for_month

logger = logging.getLogger(__name__)

# Normal communities to process
NORMAL_COMMUNITIES = ["funny", "gaming", "gifs", "pics", "technology", "videos"]


def configure_logging(verbose: bool) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def gini_coefficient(values: np.ndarray) -> float:
    """Compute Gini coefficient for a distribution.
    
    Returns value in [0, 1] where 0 = perfect equality, 1 = max inequality.
    Returns NaN for empty or all-zero arrays.
    """
    if len(values) == 0:
        return float("nan")
    
    values = np.asarray(values, dtype=float)
    if np.all(values == 0):
        return float("nan")
    
    sorted_vals = np.sort(values)
    n = len(sorted_vals)
    cumsum = np.cumsum(sorted_vals)
    
    # Gini = (2 * sum(i * x_i) - (n+1) * sum(x_i)) / (n * sum(x_i))
    total = cumsum[-1]
    if total == 0:
        return float("nan")
    
    index = np.arange(1, n + 1)
    return float((2 * np.sum(index * sorted_vals) - (n + 1) * total) / (n * total))


def load_edge_list(edge_file: Path) -> Optional[pd.DataFrame]:
    """Load edge list from whitespace-separated file."""
    if not edge_file.exists():
        return None
    
    try:
        df = pd.read_csv(
            edge_file,
            sep=r"\s+",
            names=["source", "target"],
            dtype=str,
            engine="python",
        )
        return df.dropna(subset=["source", "target"])
    except Exception as e:
        logger.warning(f"Failed to read {edge_file}: {e}")
        return None


def load_newcomer_labels(labels_path: Path) -> Optional[pd.DataFrame]:
    """Load newcomer labels CSV with first_month information."""
    if not labels_path.exists():
        logger.warning(f"Labels file not found: {labels_path}")
        return None
    
    try:
        df = pd.read_csv(labels_path, dtype={"user_id": str})
        if "first_month" in df.columns:
            df["first_seen_dt"] = pd.to_datetime(df["first_month"] + "-01")
        else:
            df["first_seen_dt"] = pd.NaT
        return df
    except Exception as e:
        logger.warning(f"Failed to read labels {labels_path}: {e}")
        return None


def compute_monthly_metrics(
    edges_df: pd.DataFrame,
    first_seen_map: Dict[str, pd.Timestamp],
    month: str,
) -> Dict[str, float]:
    """Compute degree dynamics metrics for a single month.
    
    Args:
        edges_df: DataFrame with 'source' and 'target' columns
        first_seen_map: Dict mapping user_id -> first_seen timestamp
        month: Month string (YYYY-MM)
    
    Returns:
        Dict with computed metrics
    """
    month_dt = pd.to_datetime(month + "-01")
    
    # Build graph
    G = nx.Graph()
    G.add_edges_from(zip(edges_df["source"], edges_df["target"]))
    
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    
    if n_nodes == 0:
        return {
            "month": month,
            "n_nodes": 0,
            "n_edges": 0,
            "n_newcomers": 0,
            "n_existing": 0,
            "newcomer_gini": float("nan"),
            "existing_gini": float("nan"),
            "hub_threshold_p90": float("nan"),
            "newcomer_hub_rate": float("nan"),
            "newcomer_degree_share": float("nan"),
            "newcomer_pop_share": float("nan"),
            "degree_share_ratio": float("nan"),
            "mean_newcomer_degree": float("nan"),
            "mean_existing_degree": float("nan"),
        }
    
    # Compute degrees
    degree_dict = dict(G.degree())
    
    # Partition nodes using migration-cohort logic
    newcomers = []
    existing = []
    newcomer_degrees = []
    existing_degrees = []
    
    for node in G.nodes():
        first_seen = first_seen_map.get(node, pd.NaT)
        label = newcomer_label_for_month(first_seen, month_dt)
        deg = degree_dict[node]
        
        if label == "newcomer":
            newcomers.append(node)
            newcomer_degrees.append(deg)
        else:
            existing.append(node)
            existing_degrees.append(deg)
    
    newcomer_degrees = np.array(newcomer_degrees, dtype=float)
    existing_degrees = np.array(existing_degrees, dtype=float)
    all_degrees = np.array(list(degree_dict.values()), dtype=float)
    
    n_newcomers = len(newcomers)
    n_existing = len(existing)
    
    # Compute Gini coefficients
    newcomer_gini = gini_coefficient(newcomer_degrees)
    existing_gini = gini_coefficient(existing_degrees)
    
    # Compute hub rate (newcomers above P90 of existing degrees)
    if len(existing_degrees) > 0 and len(newcomer_degrees) > 0:
        p90_existing = np.percentile(existing_degrees, 90)
        newcomer_hub_rate = float(np.mean(newcomer_degrees > p90_existing))
    else:
        p90_existing = float("nan")
        newcomer_hub_rate = float("nan")
    
    # Compute degree share / population share
    total_degree = all_degrees.sum()
    if total_degree > 0 and n_nodes > 0:
        newcomer_degree_sum = newcomer_degrees.sum()
        newcomer_degree_share = newcomer_degree_sum / total_degree
        newcomer_pop_share = n_newcomers / n_nodes
        
        if newcomer_pop_share > 0:
            degree_share_ratio = newcomer_degree_share / newcomer_pop_share
        else:
            degree_share_ratio = float("nan")
    else:
        newcomer_degree_share = float("nan")
        newcomer_pop_share = float("nan")
        degree_share_ratio = float("nan")
    
    # Mean degrees for reference
    mean_newcomer_degree = float(np.mean(newcomer_degrees)) if len(newcomer_degrees) > 0 else float("nan")
    mean_existing_degree = float(np.mean(existing_degrees)) if len(existing_degrees) > 0 else float("nan")
    
    return {
        "month": month,
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "n_newcomers": n_newcomers,
        "n_existing": n_existing,
        "newcomer_gini": newcomer_gini,
        "existing_gini": existing_gini,
        "hub_threshold_p90": p90_existing,
        "newcomer_hub_rate": newcomer_hub_rate,
        "newcomer_degree_share": newcomer_degree_share,
        "newcomer_pop_share": newcomer_pop_share,
        "degree_share_ratio": degree_share_ratio,
        "mean_newcomer_degree": mean_newcomer_degree,
        "mean_existing_degree": mean_existing_degree,
    }


def process_community(
    community: str,
    networks_dir: Path,
    labels_dir: Path,
    output_dir: Path,
) -> Optional[pd.DataFrame]:
    """Process a single community and compute all monthly metrics."""
    logger.info(f"Processing community: {community}")
    
    # Find network files
    net_dir = networks_dir / "voat" / f"{community}_monthly"
    if not net_dir.exists():
        logger.warning(f"Network directory not found: {net_dir}")
        return None
    
    # Find and load labels
    labels_candidates = [
        labels_dir / community / f"voat_{community}_newcomer_labels.csv",
        labels_dir / f"{community}/voat_{community}_newcomer_labels.csv",
    ]
    labels_path = next((p for p in labels_candidates if p.exists()), None)
    
    if labels_path is None:
        logger.warning(f"Labels not found for {community}. Tried: {labels_candidates}")
        return None
    
    labels_df = load_newcomer_labels(labels_path)
    if labels_df is None:
        return None
    
    # Build first_seen map
    first_seen_map = dict(zip(labels_df["user_id"].astype(str), labels_df["first_seen_dt"]))
    logger.info(f"  Loaded {len(first_seen_map)} user labels")
    
    # Find all monthly network files
    edge_files = sorted(net_dir.glob(f"{community}_*.txt"))
    logger.info(f"  Found {len(edge_files)} monthly network files")
    
    results = []
    for edge_file in edge_files:
        # Extract month from filename: community_YYYY-MM.txt
        month = edge_file.stem.replace(f"{community}_", "")
        
        edges_df = load_edge_list(edge_file)
        if edges_df is None or edges_df.empty:
            logger.debug(f"  Skipping empty/missing: {month}")
            continue
        
        metrics = compute_monthly_metrics(edges_df, first_seen_map, month)
        results.append(metrics)
        
        logger.debug(f"  {month}: n={metrics['n_nodes']}, newcomers={metrics['n_newcomers']}, "
                    f"gini={metrics['newcomer_gini']:.3f}, hub_rate={metrics['newcomer_hub_rate']:.3f}")
    
    if not results:
        logger.warning(f"  No results computed for {community}")
        return None
    
    df = pd.DataFrame(results)
    df = df.sort_values("month").reset_index(drop=True)
    
    # Save results
    community_output_dir = output_dir / community
    community_output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = community_output_dir / f"voat_{community}_newcomer_degree_dynamics.csv"
    df.to_csv(out_path, index=False)
    logger.info(f"  Wrote {out_path} ({len(df)} rows)")
    
    return df


def plot_community(
    df: pd.DataFrame,
    community: str,
    output_dir: Path,
) -> None:
    """Create 3-panel time series plot for a community."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        logger.warning("matplotlib not available, skipping plots")
        return
    
    # Convert month to datetime
    df = df.copy()
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    
    # Filter to valid data range (post-FPH ban typically)
    df = df[df["month_dt"] >= "2015-06-01"].copy()
    
    if df.empty:
        logger.warning(f"No data to plot for {community}")
        return
    
    # Create figure
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    
    # Style
    NEWCOMER_COLOR = "#E24A33"  # Red-orange
    EXISTING_COLOR = "#348ABD"  # Blue
    EVENT_COLOR = "#333333"
    
    # Event labels
    SHORT_LABELS = {"A": "FPH", "B": "GA", "C": "TD", "D": "PG"}
    
    def add_events(ax):
        """Add event vertical lines and labels."""
        ylim = ax.get_ylim()
        y_pos = ylim[0] + (ylim[1] - ylim[0]) * 0.95
        for key, date in EVENTS.items():
            if key in ["A", "B", "C"]:  # Only main events
                ax.axvline(date, color=EVENT_COLOR, linestyle="--", alpha=0.4, linewidth=1)
                ax.text(date, y_pos, SHORT_LABELS.get(key, key), ha="center", va="top",
                       fontsize=9, fontweight="bold", color=EVENT_COLOR,
                       bbox=dict(boxstyle="round,pad=0.2", facecolor="white", 
                                edgecolor="none", alpha=0.8))
    
    # Panel 1: Gini coefficients
    ax1 = axes[0]
    ax1.plot(df["month_dt"], df["newcomer_gini"], color=NEWCOMER_COLOR, 
             linewidth=2, label="Newcomers", marker="o", markersize=3)
    ax1.plot(df["month_dt"], df["existing_gini"], color=EXISTING_COLOR, 
             linewidth=2, label="Existing", marker="s", markersize=3)
    ax1.set_ylabel("Degree Gini Coefficient", fontweight="bold")
    ax1.set_title(f"{community.capitalize()} - Newcomer Degree Dynamics", fontsize=12, fontweight="bold")
    ax1.legend(loc="upper right", fontsize=9)
    ax1.set_ylim(0, 1)
    add_events(ax1)
    ax1.grid(True, alpha=0.3)
    
    # Panel 2: Hub rate
    ax2 = axes[1]
    ax2.plot(df["month_dt"], df["newcomer_hub_rate"], color=NEWCOMER_COLOR, 
             linewidth=2, marker="o", markersize=3)
    ax2.set_ylabel("Newcomer Hub Rate", fontweight="bold")
    ax2.axhline(0.1, color="gray", linestyle=":", alpha=0.5, label="Expected (10%)")
    ax2.legend(loc="upper right", fontsize=9)
    add_events(ax2)
    ax2.grid(True, alpha=0.3)
    
    # Panel 3: Degree share ratio
    ax3 = axes[2]
    ax3.plot(df["month_dt"], df["degree_share_ratio"], color=NEWCOMER_COLOR, 
             linewidth=2, marker="o", markersize=3)
    ax3.axhline(1.0, color="gray", linestyle="-", alpha=0.5, label="Proportional (ratio=1)")
    ax3.set_ylabel("Degree Share / Pop Share", fontweight="bold")
    ax3.set_xlabel("Month", fontweight="bold")
    ax3.legend(loc="upper right", fontsize=9)
    add_events(ax3)
    ax3.grid(True, alpha=0.3)
    
    # Format x-axis
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    
    # Save
    figures_dir = output_dir / community / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = figures_dir / f"voat_{community}_newcomer_degree_dynamics.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info(f"  Saved plot: {out_path}")


def compute_global_weighted_metrics(combined_df: pd.DataFrame) -> pd.DataFrame:
    """Compute weighted global metrics across all communities.
    
    Weights are based on n_nodes (network size) for each community-month.
    """
    df = combined_df.copy()
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    
    # Filter to months with valid data (n_nodes > 0)
    df = df[df["n_nodes"] > 0].copy()
    
    # Metrics to aggregate with weighted average
    weighted_metrics = [
        "newcomer_gini", "existing_gini", "newcomer_hub_rate",
        "newcomer_degree_share", "newcomer_pop_share", "degree_share_ratio",
        "mean_newcomer_degree", "mean_existing_degree"
    ]
    
    # Sum metrics (just sum across communities)
    sum_metrics = ["n_nodes", "n_edges", "n_newcomers", "n_existing"]
    
    results = []
    for month, month_df in df.groupby("month"):
        row = {"month": month}
        
        # Sum metrics
        for col in sum_metrics:
            row[col] = month_df[col].sum()
        
        # Weighted average metrics (weight by n_nodes)
        weights = month_df["n_nodes"].values
        total_weight = weights.sum()
        
        for col in weighted_metrics:
            valid_mask = month_df[col].notna()
            if valid_mask.sum() > 0:
                valid_weights = weights[valid_mask]
                valid_values = month_df.loc[valid_mask, col].values
                if valid_weights.sum() > 0:
                    row[col] = np.average(valid_values, weights=valid_weights)
                else:
                    row[col] = float("nan")
            else:
                row[col] = float("nan")
        
        # Recompute degree_share_ratio from aggregated values
        if row["newcomer_pop_share"] > 0:
            row["degree_share_ratio"] = row["newcomer_degree_share"] / row["newcomer_pop_share"]
        
        results.append(row)
    
    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values("month").reset_index(drop=True)
    return result_df


def plot_global(
    global_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Create 3-panel global time series plot with rolling averages."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        logger.warning("matplotlib not available, skipping plots")
        return
    
    df = global_df.copy()
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    
    # Filter to valid data range
    df = df[df["month_dt"] >= "2015-06-01"].copy()
    
    if df.empty:
        logger.warning("No data to plot for global aggregate")
        return
    
    # Compute 3-month rolling averages
    for col in ["newcomer_gini", "existing_gini", "newcomer_hub_rate", "degree_share_ratio"]:
        df[f"{col}_roll"] = df[col].rolling(window=3, center=True, min_periods=1).mean()
    
    # Create figure
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    
    # Style
    NEWCOMER_COLOR = "#E24A33"  # Red-orange
    EXISTING_COLOR = "#348ABD"  # Blue
    EVENT_COLOR = "#333333"
    
    SHORT_LABELS = {"A": "FPH", "B": "GA", "C": "TD", "D": "PG"}
    
    def add_events(ax):
        """Add event vertical lines and labels."""
        ylim = ax.get_ylim()
        y_pos = ylim[0] + (ylim[1] - ylim[0]) * 0.95
        for key, date in EVENTS.items():
            if key in ["A", "B", "C"]:
                ax.axvline(date, color=EVENT_COLOR, linestyle="--", alpha=0.4, linewidth=1)
                ax.text(date, y_pos, SHORT_LABELS.get(key, key), ha="center", va="top",
                       fontsize=9, fontweight="bold", color=EVENT_COLOR,
                       bbox=dict(boxstyle="round,pad=0.2", facecolor="white", 
                                edgecolor="none", alpha=0.8))
    
    # Panel 1: Gini coefficients (with rolling average)
    ax1 = axes[0]
    ax1.plot(df["month_dt"], df["newcomer_gini"], color=NEWCOMER_COLOR, 
             linewidth=1, alpha=0.3)
    ax1.plot(df["month_dt"], df["newcomer_gini_roll"], color=NEWCOMER_COLOR, 
             linewidth=2.5, label="Newcomers (3-mo avg)")
    ax1.plot(df["month_dt"], df["existing_gini"], color=EXISTING_COLOR, 
             linewidth=1, alpha=0.3)
    ax1.plot(df["month_dt"], df["existing_gini_roll"], color=EXISTING_COLOR, 
             linewidth=2.5, label="Existing (3-mo avg)")
    ax1.set_ylabel("Degree Gini Coefficient", fontweight="bold")
    ax1.set_title("Global (Weighted) - Newcomer Degree Dynamics", fontsize=12, fontweight="bold")
    ax1.legend(loc="upper right", fontsize=9)
    ax1.set_ylim(0, 1)
    add_events(ax1)
    ax1.grid(True, alpha=0.3)
    
    # Panel 2: Hub rate (with rolling average)
    ax2 = axes[1]
    ax2.plot(df["month_dt"], df["newcomer_hub_rate"], color=NEWCOMER_COLOR, 
             linewidth=1, alpha=0.3)
    ax2.plot(df["month_dt"], df["newcomer_hub_rate_roll"], color=NEWCOMER_COLOR, 
             linewidth=2.5, label="Newcomer Hub Rate (3-mo avg)")
    ax2.axhline(0.1, color="gray", linestyle=":", alpha=0.5, label="Expected (10%)")
    ax2.set_ylabel("Newcomer Hub Rate", fontweight="bold")
    ax2.legend(loc="upper right", fontsize=9)
    add_events(ax2)
    ax2.grid(True, alpha=0.3)
    
    # Panel 3: Degree share ratio (with rolling average)
    ax3 = axes[2]
    ax3.plot(df["month_dt"], df["degree_share_ratio"], color=NEWCOMER_COLOR, 
             linewidth=1, alpha=0.3)
    ax3.plot(df["month_dt"], df["degree_share_ratio_roll"], color=NEWCOMER_COLOR, 
             linewidth=2.5, label="Degree Share Ratio (3-mo avg)")
    ax3.axhline(1.0, color="gray", linestyle="-", alpha=0.5, label="Proportional (ratio=1)")
    ax3.set_ylabel("Degree Share / Pop Share", fontweight="bold")
    ax3.set_xlabel("Month", fontweight="bold")
    ax3.legend(loc="upper right", fontsize=9)
    add_events(ax3)
    ax3.grid(True, alpha=0.3)
    
    # Format x-axis
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    
    # Save
    figures_dir = output_dir / "global" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = figures_dir / "voat_global_newcomer_degree_dynamics.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info(f"Saved global plot: {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Compute newcomer degree dynamics metrics for Voat communities"
    )
    parser.add_argument(
        "--networks-dir",
        type=Path,
        default=Path("results/networks"),
        help="Directory containing network edge lists",
    )
    parser.add_argument(
        "--labels-dir",
        type=Path,
        default=Path("results/voat"),
        help="Directory containing newcomer label CSVs",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/voat"),
        help="Output directory for results and figures",
    )
    parser.add_argument(
        "--communities",
        nargs="+",
        default=NORMAL_COMMUNITIES,
        help="Communities to process (default: normal communities)",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate plots for each community",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    configure_logging(args.verbose)
    
    logger.info(f"Processing communities: {args.communities}")
    logger.info(f"Networks dir: {args.networks_dir}")
    logger.info(f"Labels dir: {args.labels_dir}")
    logger.info(f"Output dir: {args.output_dir}")
    
    all_results = []
    
    for community in args.communities:
        result_df = process_community(
            community=community,
            networks_dir=args.networks_dir,
            labels_dir=args.labels_dir,
            output_dir=args.output_dir,
        )
        
        if result_df is not None:
            result_df["community"] = community
            all_results.append(result_df)
            
            if args.plot:
                plot_community(result_df, community, args.output_dir)
        
        gc.collect()
    
    # Optionally combine all results
    if all_results:
        combined = pd.concat(all_results, ignore_index=True)
        combined_path = args.output_dir / "voat_all_communities_newcomer_degree_dynamics.csv"
        combined.to_csv(combined_path, index=False)
        logger.info(f"Wrote combined results: {combined_path} ({len(combined)} rows)")
        
        # Compute and save global weighted metrics
        logger.info("Computing global weighted metrics...")
        global_df = compute_global_weighted_metrics(combined)
        
        global_dir = args.output_dir / "global"
        global_dir.mkdir(parents=True, exist_ok=True)
        
        global_path = global_dir / "voat_global_newcomer_degree_dynamics.csv"
        global_df.to_csv(global_path, index=False)
        logger.info(f"Wrote global results: {global_path} ({len(global_df)} rows)")
        
        # Generate global plot
        if args.plot:
            plot_global(global_df, args.output_dir)
    
    logger.info("Done!")


if __name__ == "__main__":
    main()

