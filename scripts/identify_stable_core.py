#!/usr/bin/env python3
"""Identify stable core and periphery members based on consistent classification.

This script analyzes core-periphery labels over time to identify users who maintain
their classification (C or P) for a minimum number of consecutive months.
"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Set
import matplotlib.pyplot as plt

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


def load_cp_labels(cp_labels_path: Path) -> pd.DataFrame:
    """Load and prepare core-periphery labels."""
    df = pd.read_csv(cp_labels_path)
    df['window'] = pd.to_datetime(df['window'])
    df = df.sort_values(['node_id', 'window'])
    return df


def find_stable_periods(df: pd.DataFrame, min_months: int = 6) -> pd.DataFrame:
    """Find users with stable C/P classification for at least min_months."""
    
    stable_users = []
    
    for node_id, group in df.groupby('node_id'):
        group = group.sort_values('window')
        
        # Find consecutive periods of same label
        group['label_change'] = group['label'].diff().fillna(0) != 0
        group['period_id'] = group['label_change'].cumsum()
        
        for period_id, period_group in group.groupby('period_id'):
            period_length = len(period_group)
            if period_length >= min_months:
                stable_users.append({
                    'node_id': node_id,
                    'label': period_group['label'].iloc[0],
                    'start_window': period_group['window'].min(),
                    'end_window': period_group['window'].max(),
                    'duration_months': period_length,
                    'stability_type': 'stable_core' if period_group['label'].iloc[0] == 0 else 'stable_periphery'
                })
    
    return pd.DataFrame(stable_users)


def find_overlapping_stable_periods(stable_df: pd.DataFrame, 
                                  analysis_start: str, 
                                  analysis_end: str) -> pd.DataFrame:
    """Find stable users whose periods overlap with the analysis timeframe."""
    
    analysis_start = pd.to_datetime(analysis_start)
    analysis_end = pd.to_datetime(analysis_end)
    
    # Filter for periods that overlap with analysis timeframe
    overlapping = stable_df[
        (stable_df['start_window'] <= analysis_end) & 
        (stable_df['end_window'] >= analysis_start)
    ].copy()
    
    # For users with multiple overlapping periods, pick the longest
    overlapping = overlapping.sort_values('duration_months', ascending=False)
    overlapping = overlapping.drop_duplicates('node_id', keep='first')
    
    return overlapping


def create_stable_cp_map(stable_df: pd.DataFrame, 
                        analysis_months: List[str]) -> Dict[str, str]:
    """Create a mapping from node_id to stable classification for analysis months."""
    
    cp_map = {}
    
    for _, row in stable_df.iterrows():
        node_id = str(row['node_id'])
        label_type = 'C' if row['label'] == 0 else 'P'
        
        # Assign this classification to all analysis months
        for month in analysis_months:
            month_key = f"{node_id}_{month}"
            cp_map[month_key] = label_type
    
    return cp_map


def analyze_stability_patterns(cp_labels_path: Path, 
                             min_months: int = 6,
                             analysis_start: str = "2014-01",
                             analysis_end: str = "2020-12") -> Dict:
    """Analyze core-periphery stability patterns."""
    
    print(f"Loading CP labels from {cp_labels_path}")
    df = load_cp_labels(cp_labels_path)
    
    print(f"Finding stable periods (min {min_months} months)...")
    stable_df = find_stable_periods(df, min_months)
    
    print(f"Found {len(stable_df)} stable periods")
    print(f"Stable core periods: {(stable_df['label'] == 0).sum()}")
    print(f"Stable periphery periods: {(stable_df['label'] == 1).sum()}")
    
    # Find overlapping periods
    overlapping = find_overlapping_stable_periods(stable_df, analysis_start, analysis_end)
    
    print(f"Overlapping with analysis period: {len(overlapping)} periods")
    
    # Generate analysis months
    analysis_months = pd.date_range(start=analysis_start, end=analysis_end, freq='M').strftime('%Y-%m').tolist()
    
    # Create stable CP mapping
    stable_cp_map = create_stable_cp_map(overlapping, analysis_months)
    
    return {
        'stable_df': stable_df,
        'overlapping_df': overlapping,
        'stable_cp_map': stable_cp_map,
        'analysis_months': analysis_months,
        'total_users': df['node_id'].nunique(),
        'stable_users': len(overlapping)
    }


def plot_stability_analysis(stable_df: pd.DataFrame, 
                           community: str, 
                           output_path: Path) -> None:
    """Plot stability analysis results."""
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)
    
    # Duration distribution
    axes[0, 0].hist(stable_df['duration_months'], bins=20, alpha=0.7, edgecolor='black')
    axes[0, 0].set_title('Distribution of Stable Period Durations')
    axes[0, 0].set_xlabel('Duration (months)')
    axes[0, 0].set_ylabel('Count')
    axes[0, 0].grid(True, alpha=0.3)
    
    # Core vs Periphery counts
    stability_counts = stable_df['stability_type'].value_counts()
    axes[0, 1].bar(stability_counts.index, stability_counts.values, alpha=0.7, edgecolor='black')
    axes[0, 1].set_title('Stable Core vs Periphery Counts')
    axes[0, 1].set_ylabel('Count')
    axes[0, 1].grid(True, alpha=0.3)
    
    # Timeline of stable periods
    for i, (label, group) in enumerate(stable_df.groupby('label')):
        color = 'red' if label == 0 else 'blue'
        label_name = 'Core' if label == 0 else 'Periphery'
        
        for _, row in group.iterrows():
            axes[1, 0].barh(
                row['node_id'], 
                row['duration_months'],
                left=row['start_window'],
                height=0.8,
                color=color,
                alpha=0.6,
                label=label_name if row['node_id'] == group['node_id'].iloc[0] else ""
            )
    
    axes[1, 0].set_title('Timeline of Stable Periods')
    axes[1, 0].set_xlabel('Time')
    axes[1, 0].set_ylabel('User ID')
    axes[1, 0].legend()
    
    # Monthly active stable users
    monthly_stable = []
    for month in pd.date_range(start=stable_df['start_window'].min(), 
                              end=stable_df['end_window'].max(), 
                              freq='M'):
        month_str = month.strftime('%Y-%m')
        active_core = stable_df[
            (stable_df['label'] == 0) & 
            (stable_df['start_window'] <= month) & 
            (stable_df['end_window'] >= month)
        ]
        active_periphery = stable_df[
            (stable_df['label'] == 1) & 
            (stable_df['start_window'] <= month) & 
            (stable_df['end_window'] >= month)
        ]
        
        monthly_stable.append({
            'month': month,
            'stable_core': len(active_core),
            'stable_periphery': len(active_periphery)
        })
    
    monthly_df = pd.DataFrame(monthly_stable)
    
    axes[1, 1].plot(monthly_df['month'], monthly_df['stable_core'], 
                    label='Stable Core', color='red', linewidth=2)
    axes[1, 1].plot(monthly_df['month'], monthly_df['stable_periphery'], 
                    label='Stable Periphery', color='blue', linewidth=2)
    axes[1, 1].set_title('Monthly Active Stable Users')
    axes[1, 1].set_xlabel('Month')
    axes[1, 1].set_ylabel('Count')
    axes[1, 1].legend()
    axes[1, 1].grid(True, alpha=0.3)
    
    fig.suptitle(f'Stable Core-Periphery Analysis: {community}', fontsize=16)
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cp-labels", required=True, type=Path, 
                       help="Path to CP labels CSV")
    parser.add_argument("--community", required=True, 
                       help="Community name")
    parser.add_argument("--min-months", type=int, default=6,
                       help="Minimum months for stable classification")
    parser.add_argument("--analysis-start", default="2014-01",
                       help="Analysis start date (YYYY-MM)")
    parser.add_argument("--analysis-end", default="2020-12", 
                       help="Analysis end date (YYYY-MM)")
    parser.add_argument("--output-dir", type=Path, default=Path("results/entropy/stable_core"),
                       help="Output directory")
    
    args = parser.parse_args()
    
    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Analyze stability
    results = analyze_stability_patterns(
        args.cp_labels, 
        args.min_months,
        args.analysis_start,
        args.analysis_end
    )
    
    # Save results
    stable_path = args.output_dir / f"{args.community}_stable_core_periphery.csv"
    results['overlapping_df'].to_csv(stable_path, index=False)
    print(f"Saved stable classifications: {stable_path}")
    
    # Create stable CP map for entropy analysis
    cp_map_path = args.output_dir / f"{args.community}_stable_cp_map.csv"
    cp_map_data = []
    for key, value in results['stable_cp_map'].items():
        node_id, month = key.split('_', 1)
        cp_map_data.append({'node_id': node_id, 'month': month, 'label_type': value})
    
    pd.DataFrame(cp_map_data).to_csv(cp_map_path, index=False)
    print(f"Saved stable CP map: {cp_map_path}")
    
    # Plot analysis
    plot_path = args.output_dir / f"{args.community}_stability_analysis.png"
    plot_stability_analysis(results['stable_df'], args.community, plot_path)
    print(f"Saved stability plot: {plot_path}")
    
    # Summary statistics
    print(f"\nSummary for {args.community}:")
    print(f"Total users in CP analysis: {results['total_users']}")
    print(f"Stable users (min {args.min_months} months): {results['stable_users']}")
    print(f"Stability rate: {results['stable_users']/results['total_users']:.2%}")


if __name__ == "__main__":
    main()
