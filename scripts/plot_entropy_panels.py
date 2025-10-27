#!/usr/bin/env python3
"""Plot entropy panels: C-C/P-P and C-P/P-C mean per token by month.

Creates two-panel plots showing mean entropy per token for:
- Panel 1: C-C and P-P (same group interactions)
- Panel 2: C-P and P-C (cross group interactions)

No rolling means, no trimming - just raw monthly means.
"""

import argparse
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List, Dict, Any

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white", 
    "axes.edgecolor": "#333333",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titleweight": "bold",
    "axes.grid": False,
    "legend.frameon": False,
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "lines.linewidth": 1.6,
})


def load_entropy_data(csv_path: Path) -> pd.DataFrame:
    """Load and prepare entropy summary data."""
    df = pd.read_csv(csv_path)
    df['month'] = pd.to_datetime(df['month'])
    return df


def plot_entropy_panels(df: pd.DataFrame, community: str, output_path: Path) -> None:
    """Create two-panel plot: C-C/P-P and C-P/P-C mean entropy per token."""
    
    # Filter for AB pairs only (interpersonal interactions)
    ab_df = df[df['pair_type'] == 'AB'].copy()
    
    if ab_df.empty:
        print(f"No AB pairs found for {community}")
        return
    
    # Create figure with two panels
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, constrained_layout=True)
    
    # Panel 1: C-C and P-P (same group)
    same_group = ab_df[ab_df['cp_combo'].isin(['C-C', 'P-P'])]
    
    if not same_group.empty:
        for combo in ['C-C', 'P-P']:
            combo_data = same_group[same_group['cp_combo'] == combo]
            if not combo_data.empty:
                # Group by month and get mean
                monthly_means = combo_data.groupby('month')['mean_H_per_token'].mean().reset_index()
                monthly_means = monthly_means.sort_values('month')
                
                ax1.plot(
                    monthly_means['month'],
                    monthly_means['mean_H_per_token'],
                    marker='o',
                    label=combo,
                    linewidth=2,
                    markersize=4
                )
    
    ax1.set_title(f"Same Group Interactions: C-C and P-P")
    ax1.set_ylabel("Mean H per token")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Panel 2: C-P and P-C (cross group)
    cross_group = ab_df[ab_df['cp_combo'].isin(['C-P', 'P-C'])]
    
    if not cross_group.empty:
        for combo in ['C-P', 'P-C']:
            combo_data = cross_group[cross_group['cp_combo'] == combo]
            if not combo_data.empty:
                # Group by month and get mean
                monthly_means = combo_data.groupby('month')['mean_H_per_token'].mean().reset_index()
                monthly_means = monthly_means.sort_values('month')
                
                ax2.plot(
                    monthly_means['month'],
                    monthly_means['mean_H_per_token'],
                    marker='o',
                    label=combo,
                    linewidth=2,
                    markersize=4
                )
    
    ax2.set_title(f"Cross Group Interactions: C-P and P-C")
    ax2.set_ylabel("Mean H per token")
    ax2.set_xlabel("Month")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Format x-axis
    ax2.xaxis.set_major_locator(plt.matplotlib.dates.MonthLocator(interval=6))
    ax2.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y-%m'))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
    
    # Overall title
    fig.suptitle(f"Reddit /{community}: Mean Entropy per Token by Core-Periphery Interaction Type", 
                 fontsize=14, y=0.98)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close()


def plot_all_communities(results_dir: Path, output_dir: Path) -> None:
    """Plot entropy panels for all available communities."""
    
    reddit_dir = results_dir / "reddit"
    if not reddit_dir.exists():
        print(f"Reddit results directory not found: {reddit_dir}")
        return
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    communities = [d.name for d in reddit_dir.iterdir() if d.is_dir()]
    communities.sort()
    
    print(f"Found {len(communities)} communities: {communities}")
    
    for community in communities:
        community_dir = reddit_dir / community / "results"
        combo_file = community_dir / f"reddit_{community}_timeseries_summary_combo.csv"
        
        if not combo_file.exists():
            print(f"Skipping {community}: {combo_file} not found")
            continue
            
        print(f"Processing {community}...")
        
        try:
            df = load_entropy_data(combo_file)
            output_path = output_dir / f"reddit_{community}_entropy_panels.png"
            plot_entropy_panels(df, community, output_path)
            print(f"  Saved: {output_path}")
            
        except Exception as e:
            print(f"  Error processing {community}: {e}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--community", help="Specific community to plot")
    parser.add_argument("--combo-csv", type=Path, help="Path to combo summary CSV")
    parser.add_argument("--results-dir", type=Path, default=Path("results/entropy"), 
                       help="Base results directory")
    parser.add_argument("--output-dir", type=Path, default=Path("results/entropy/plots"),
                       help="Output directory for plots")
    parser.add_argument("--all", action="store_true", help="Plot all communities")
    
    args = parser.parse_args()
    
    if args.all:
        plot_all_communities(args.results_dir, args.output_dir)
    elif args.community and args.combo_csv:
        df = load_entropy_data(args.combo_csv)
        output_path = args.output_dir / f"reddit_{args.community}_entropy_panels.png"
        args.output_dir.mkdir(parents=True, exist_ok=True)
        plot_entropy_panels(df, args.community, output_path)
        print(f"Saved: {output_path}")
    else:
        print("Use --all to plot all communities, or --community and --combo-csv for specific community")
        parser.print_help()


if __name__ == "__main__":
    main()
