#!/usr/bin/env python3
"""Plot global aggregate summary (Voat) across all communities.

8 Panels:
1. E-I Index
2. Mean Toxicity
3. Degree Assortativity
4. Active Users (rep > 1) split by Newcomers vs Existing
5. Newcomer Hub Rate (share of hubs)
6. Degree Share / Population Share Ratio
7. Event-Period Heatmap: Voat-Reddit Toxicity Difference by Period
8. Mean Reputation
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.dates as mdates
import numpy as np
import seaborn as sns

# Ensure repository root on path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS, EVENT_LABELS, newcomer_label_for_month

# Style
VOAT_COLOR = "#800080"  # Purple
REDDIT_COLOR = "#ff7f0e"  # Orange
TOXICITY_COLOR = "#D62728"  # Red
EVENT_COLOR = "#333333"
EVENT_ALPHA = 0.15

# Custom event labels using short names
SHORT_EVENT_LABELS = {
    "A": "FPH",
    "B": "PG",
    "C": "GA",
    "D": "TD",
}


COMMUNITIES = ["funny", "gaming", "technology", "videos", "gifs", "pics"]


def load_reddit_toxicity(results_root: Path, start_date, end_date) -> pd.DataFrame:
    """Load and aggregate Reddit toxicity across all communities."""
    all_data = []
    for comm in COMMUNITIES:
        path = results_root / "reddit" / comm / f"reddit_{comm}_monthly_aggregates.csv"
        if path.exists():
            df = pd.read_csv(path)
            df["month_dt"] = pd.to_datetime(df["month"] + "-01")
            df = df[(df["month_dt"] >= start_date) & (df["month_dt"] <= end_date)]
            if "toxicity_mean" in df.columns and "active_users" in df.columns:
                all_data.append(df[["month_dt", "toxicity_mean", "active_users"]])
    
    if not all_data:
        return None
    
    full_df = pd.concat(all_data, ignore_index=True)
    # Weighted average by active users
    def weighted_avg(group):
        if group["active_users"].sum() > 0:
            return np.average(group["toxicity_mean"], weights=group["active_users"])
        return np.nan
    
    agg = full_df.groupby("month_dt", as_index=False).apply(weighted_avg, include_groups=False)
    agg.columns = ["month_dt", "toxicity_mean"]
    return agg.sort_values("month_dt")


def load_active_users_by_status(results_root: Path, start_date, end_date) -> pd.DataFrame:
    """Load active users (rep > 1) split by newcomer/existing status across all communities.
    
    Joins user-month parquet with newcomer labels, filters rep > 1, applies
    newcomer_label_for_month() logic, and aggregates globally.
    
    Returns DataFrame with columns: month_dt, newcomer_active, existing_active
    """
    all_data = []
    
    for comm in COMMUNITIES:
        # Load user-month metrics
        parquet_path = results_root / "voat" / comm / f"voat_{comm}_user_month_metrics.parquet"
        labels_path = results_root / "voat" / comm / f"voat_{comm}_newcomer_labels.csv"
        
        if not parquet_path.exists() or not labels_path.exists():
            continue
        
        # Read parquet (small files, safe to load fully)
        user_df = pd.read_parquet(parquet_path)
        
        # Read newcomer labels (has first_month)
        labels_df = pd.read_csv(labels_path, dtype={"user_id": str})
        labels_df["first_seen_dt"] = pd.to_datetime(labels_df["first_month"] + "-01")
        
        # Join on user_id
        user_df["user_id"] = user_df["user_id"].astype(str)
        merged = user_df.merge(labels_df[["user_id", "first_seen_dt"]], on="user_id", how="left")
        
        # Filter to users with reputation > 1
        merged = merged[merged["mean_reputation"] > 1].copy()
        
        if merged.empty:
            continue
        
        # Convert month to datetime
        merged["month_dt"] = pd.to_datetime(merged["month"] + "-01")
        
        # Apply newcomer label for each row
        def get_status(row):
            return newcomer_label_for_month(row["first_seen_dt"], row["month_dt"])
        
        merged["status"] = merged.apply(get_status, axis=1)
        
        # Count by month and status
        counts = merged.groupby(["month_dt", "status"]).size().unstack(fill_value=0)
        counts = counts.reset_index()
        
        # Ensure both columns exist
        if "newcomer" not in counts.columns:
            counts["newcomer"] = 0
        if "existing" not in counts.columns:
            counts["existing"] = 0
        
        all_data.append(counts[["month_dt", "newcomer", "existing"]])
    
    if not all_data:
        return None
    
    # Concatenate and sum across communities
    full_df = pd.concat(all_data, ignore_index=True)
    agg = full_df.groupby("month_dt", as_index=False).agg({
        "newcomer": "sum",
        "existing": "sum"
    })
    agg = agg.rename(columns={"newcomer": "newcomer_active", "existing": "existing_active"})
    
    # Filter date range
    agg = agg[(agg["month_dt"] >= start_date) & (agg["month_dt"] <= end_date)]
    
    return agg.sort_values("month_dt")


def add_events_band(ax):
    """Add vertical bands for events with clear labels."""
    ylim = ax.get_ylim()
    y_pos = ylim[0] + (ylim[1] - ylim[0]) * 0.98
    for key, date in EVENTS.items():
        # Draw line
        ax.axvline(date, color=EVENT_COLOR, linestyle="--", alpha=0.4, linewidth=0.8, zorder=1)
        # Add label at top with background - use short labels
        label = SHORT_EVENT_LABELS.get(key, key)
        ax.text(date, y_pos, label, ha="center", va="top", fontsize=8, fontweight="bold",
                color=EVENT_COLOR, rotation=0, 
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", 
                         edgecolor="none", alpha=0.8))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", type=Path, required=True, help="Global aggregate CSV")
    parser.add_argument("--heatmap-file", type=Path, default=Path("results/global/event_period_toxicity_diff.csv"), help="Event period toxicity diff CSV")
    parser.add_argument("--degree-dynamics-file", type=Path, default=Path("results/voat/global/voat_global_newcomer_degree_dynamics.csv"), help="Newcomer degree dynamics CSV")
    parser.add_argument("--output-dir", type=Path, default=Path("figures/global"))
    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"Input file not found: {args.input_file}")
        sys.exit(1)

    # Load main aggregate data
    df = pd.read_csv(args.input_file)
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    df = df.sort_values("month_dt")
    
    # Filter date range: September 2015 to December 2020
    start_date = pd.Timestamp("2015-09-01")
    end_date = pd.Timestamp("2020-12-31")
    df = df[(df["month_dt"] >= start_date) & (df["month_dt"] <= end_date)].copy()
    
    # Load event-period heatmap data
    heatmap_df = None
    heatmap_pivot = None
    if args.heatmap_file.exists():
        heatmap_df = pd.read_csv(args.heatmap_file)
        # Pivot for heatmap: communities as rows, periods as columns
        heatmap_pivot = heatmap_df.pivot(index="community", columns="period", values="toxicity_diff")
        # Order columns chronologically: A-B, B-C, C-D, D-end
        period_order = ["A-B", "B-C", "C-D", "D-end"]
        heatmap_pivot = heatmap_pivot[[col for col in period_order if col in heatmap_pivot.columns]]

    # Load newcomer degree dynamics data
    degree_df = None
    if args.degree_dynamics_file.exists():
        degree_df = pd.read_csv(args.degree_dynamics_file)
        degree_df["month_dt"] = pd.to_datetime(degree_df["month"] + "-01")
        degree_df = degree_df[(degree_df["month_dt"] >= start_date) & (degree_df["month_dt"] <= end_date)].copy()
        degree_df = degree_df.sort_values("month_dt")
        # Compute rolling averages for degree share ratio
        if "degree_share_ratio" in degree_df.columns:
            degree_df["degree_share_ratio_roll"] = degree_df["degree_share_ratio"].rolling(
                window=3, center=True, min_periods=1).mean()

    # Create figure with 8 panels (4x2 grid)
    fig = plt.figure(figsize=(12, 18))
    gs = fig.add_gridspec(4, 2, height_ratios=[1, 1, 1, 1], hspace=0.35, wspace=0.3)
    
    ax1 = fig.add_subplot(gs[0, 0])  # E-I Index
    ax2 = fig.add_subplot(gs[0, 1])  # Mean Toxicity
    ax3 = fig.add_subplot(gs[1, 0])  # Assortativity
    ax4 = fig.add_subplot(gs[1, 1])  # Active Users by Status
    ax5 = fig.add_subplot(gs[2, 0])  # Newcomer Hub Rate
    ax6 = fig.add_subplot(gs[2, 1])  # Degree Share / Pop Share
    ax7 = fig.add_subplot(gs[3, 1])  # Event-Period Heatmap
    # ax8 created later for Mean Reputation (bottom left)
    
    # Colors for newcomer metrics
    NEWCOMER_COLOR = "#E24A33"  # Red-orange
    EXISTING_COLOR = "#348ABD"  # Blue
    
    # Compute 3-month rolling means
    df_rolling = df.copy()
    for col in ["ei_index", "toxicity_mean_voat", "degree_assortativity_voat", "reputation_mean_voat_agg"]:
        if col in df_rolling.columns:
            df_rolling[f"{col}_roll"] = df_rolling[col].rolling(window=3, center=True, min_periods=1).mean()
    
    # 1. E-I Index
    if "ei_index" in df.columns:
        ax1.plot(df["month_dt"], df["ei_index"], color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax1.plot(df_rolling["month_dt"], df_rolling["ei_index_roll"], color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
        ax1.set_ylabel("E-I Index", fontweight="bold")
        ax1.set_title("E-I Index (Voat)")
        ax1.axhline(0, color="k", linestyle="-", linewidth=0.5, alpha=0.3)
        ax1.legend(loc="upper left", fontsize=8)
        add_events_band(ax1)
    
    # 2. Mean Toxicity (both Reddit and Voat)
    # Load Reddit toxicity from community files and aggregate
    reddit_tox = load_reddit_toxicity(args.input_file.parent.parent, start_date, end_date)
    
    if "toxicity_mean_voat" in df.columns:
        ax2.plot(df["month_dt"], df["toxicity_mean_voat"], color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax2.plot(df_rolling["month_dt"], df_rolling["toxicity_mean_voat_roll"], color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
    
    if reddit_tox is not None and not reddit_tox.empty:
        reddit_tox["tox_roll"] = reddit_tox["toxicity_mean"].rolling(window=3, center=True, min_periods=1).mean()
        ax2.plot(reddit_tox["month_dt"], reddit_tox["toxicity_mean"], color=REDDIT_COLOR, linewidth=1, alpha=0.3)
        ax2.plot(reddit_tox["month_dt"], reddit_tox["tox_roll"], color=REDDIT_COLOR, linewidth=2.5, label="Reddit (3-mo avg)")
    
    ax2.set_ylabel("Mean Toxicity", fontweight="bold")
    ax2.set_title("Mean Toxicity")
    ax2.legend(loc="upper left", fontsize=8)
    add_events_band(ax2)

    # 3. Degree Assortativity
    if "degree_assortativity_voat" in df.columns:
        ax3.plot(df["month_dt"], df["degree_assortativity_voat"], color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax3.plot(df_rolling["month_dt"], df_rolling["degree_assortativity_voat_roll"], color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
        ax3.set_ylabel("Assortativity", fontweight="bold")
        ax3.set_title("Degree Assortativity (Voat)")
        ax3.axhline(0, color="k", linestyle="-", linewidth=0.5, alpha=0.3)
        ax3.legend(loc="upper left", fontsize=8)
        add_events_band(ax3)
    
    # 4. Active Users (rep > 1) split by Newcomers vs Existing
    # Load active users data
    active_users_df = load_active_users_by_status(args.input_file.parent.parent, start_date, end_date)
    
    if active_users_df is not None and not active_users_df.empty:
        # Compute rolling averages
        active_users_df["newcomer_roll"] = active_users_df["newcomer_active"].rolling(
            window=3, center=True, min_periods=1).mean()
        active_users_df["existing_roll"] = active_users_df["existing_active"].rolling(
            window=3, center=True, min_periods=1).mean()
        
        ax4.plot(active_users_df["month_dt"], active_users_df["newcomer_active"], 
                color=NEWCOMER_COLOR, linewidth=1, alpha=0.3)
        ax4.plot(active_users_df["month_dt"], active_users_df["newcomer_roll"], 
                color=NEWCOMER_COLOR, linewidth=2.5, label="Newcomers (3-mo avg)")
        ax4.plot(active_users_df["month_dt"], active_users_df["existing_active"], 
                color=EXISTING_COLOR, linewidth=1, alpha=0.3)
        ax4.plot(active_users_df["month_dt"], active_users_df["existing_roll"], 
                color=EXISTING_COLOR, linewidth=2.5, label="Existing (3-mo avg)")
        ax4.set_ylabel("Active Users (rep > 1)", fontweight="bold")
        ax4.set_title("Active Users by Status (Voat)")
        ax4.legend(loc="upper left", fontsize=8)
        add_events_band(ax4)
    else:
        ax4.text(0.5, 0.5, "Active users data not available", 
                ha="center", va="center", transform=ax4.transAxes)
        ax4.set_title("Active Users by Status (Voat)")
    
    # 5. Newcomer Hub Rate (share of hubs)
    if degree_df is not None and "newcomer_hub_rate" in degree_df.columns:
        # Compute rolling average for hub rate
        degree_df["newcomer_hub_rate_roll"] = degree_df["newcomer_hub_rate"].rolling(
            window=3, center=True, min_periods=1).mean()
        
        ax5.plot(degree_df["month_dt"], degree_df["newcomer_hub_rate"], 
                color=NEWCOMER_COLOR, linewidth=1, alpha=0.3)
        ax5.plot(degree_df["month_dt"], degree_df["newcomer_hub_rate_roll"], 
                color=NEWCOMER_COLOR, linewidth=2.5, label="Hub Rate (3-mo avg)")
        ax5.axhline(0.1, color="gray", linestyle=":", linewidth=1, alpha=0.5, label="Expected (10%)")
        ax5.set_ylabel("Newcomer Hub Rate", fontweight="bold")
        ax5.set_title("Share of Hubs Among Newcomers (Voat)")
        ax5.set_ylim(0, None)
        ax5.legend(loc="upper right", fontsize=8)
        add_events_band(ax5)
    else:
        ax5.text(0.5, 0.5, "Hub rate data not available", 
                ha="center", va="center", transform=ax5.transAxes)
        ax5.set_title("Share of Hubs Among Newcomers (Voat)")
    
    # 6. Degree Share / Population Share Ratio
    if degree_df is not None and "degree_share_ratio" in degree_df.columns:
        ax6.plot(degree_df["month_dt"], degree_df["degree_share_ratio"], 
                color=NEWCOMER_COLOR, linewidth=1, alpha=0.3)
        ax6.plot(degree_df["month_dt"], degree_df["degree_share_ratio_roll"], 
                color=NEWCOMER_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
        ax6.axhline(1.0, color="gray", linestyle="-", linewidth=1, alpha=0.5, label="Proportional (=1)")
        ax6.set_ylabel("Degree Share / Pop Share", fontweight="bold")
        ax6.set_title("Newcomer Degree Share Ratio (Voat)")
        ax6.legend(loc="upper right", fontsize=8)
        add_events_band(ax6)
    else:
        ax6.text(0.5, 0.5, "Degree dynamics data not available", 
                ha="center", va="center", transform=ax6.transAxes)
        ax6.set_title("Newcomer Degree Share Ratio (Voat)")
    
    # Format X axes for time series
    for ax in [ax1, ax2, ax3, ax4, ax5, ax6]:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.set_xlabel("Year")
    
    # 7. Event-Period Heatmap: Voat-Reddit Toxicity Difference
    if heatmap_df is not None and not heatmap_pivot.empty:
        # Create a visually appealing heatmap with square cells
        sns.heatmap(
            heatmap_pivot, 
            ax=ax7, 
            annot=True,
            annot_kws={"size": 10, "weight": "bold"},
            fmt=".2f", 
            cmap="coolwarm",
            center=0,
            cbar_kws={"label": "Toxicity Diff\n(Voat − Reddit)", "shrink": 0.8},
            linewidths=2,
            linecolor="white",
            vmin=-0.05,
            vmax=0.18,
            square=True  # Keep square cells for proper heatmap look
        )
        ax7.set_title("Toxicity Difference by Event Period", 
                     fontweight="bold", fontsize=11, pad=12)
        ax7.set_xlabel("Event Period", fontweight="bold", fontsize=10)
        ax7.set_ylabel("Community", fontweight="bold", fontsize=10)
        
        # Period labels using event names: FPH, PG, GA, TD
        period_labels = ["FPH→PG", "PG→GA", "GA→TD", "TD→End"]
        ax7.set_xticklabels(period_labels, rotation=0, ha="center", fontsize=8)
        ax7.set_yticklabels(ax7.get_yticklabels(), rotation=0, fontsize=9)
        
    else:
        ax7.text(0.5, 0.5, "Heatmap data not available", 
                ha="center", va="center", transform=ax7.transAxes)
        ax7.set_title("Voat-Reddit Toxicity Difference by Event Period")
    
    # 8. Mean Reputation (bottom-left)
    ax8 = fig.add_subplot(gs[3, 0])
    REPUTATION_COLOR = "#2E86AB"  # Blue
    
    if "reputation_mean_voat_agg" in df.columns:
        ax8.plot(df["month_dt"], df["reputation_mean_voat_agg"], 
                color=REPUTATION_COLOR, linewidth=1, alpha=0.3)
        ax8.plot(df_rolling["month_dt"], df_rolling["reputation_mean_voat_agg_roll"], 
                color=REPUTATION_COLOR, linewidth=2.5, label="Mean (3-mo avg)")
        ax8.set_ylabel("Mean Reputation", fontweight="bold")
        ax8.set_title("Mean Reputation (Voat, active users)")
        ax8.legend(loc="upper left", fontsize=8)
        ax8.xaxis.set_major_locator(mdates.YearLocator())
        ax8.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax8.set_xlabel("Year")
        add_events_band(ax8)
    else:
        ax8.text(0.5, 0.5, "Reputation data not available", 
                ha="center", va="center", transform=ax8.transAxes)
        ax8.set_title("Mean Reputation (Voat)")
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / "voat_global_summary.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

