#!/usr/bin/env python3
"""Plot global aggregate summary (Voat) across all communities.

8 Panels:
1. E-I Index
2. Mean ToxiGen classifier probability
3. Degree Assortativity
4. Active Users (rep > 1) split by Newcomers vs Existing
5. Newcomer Hub Rate (share of hubs)
6. Degree Share / Population Share Ratio
7. Event-Period Heatmap: Voat-Reddit ToxiGen classifier-probability difference by period
8. Mean Reputation
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import pandas as pd
import matplotlib.dates as mdates
import numpy as np
import seaborn as sns

# Ensure repository root on path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS_CHRONO, newcomer_label_for_month

# Style - Three-color scheme per colleague feedback (Saška/Ana):
# - Voat coral for whole-community metrics (panels 1,3,6,7,8)
# - Newcomer teal for newcomer-specific (panels 2,4,5)
# - Existing dark purple for existing users (panel 2 only)
VOAT_COLOR = "#F46036"      # Coral/orange-red
NEWCOMER_COLOR = "#1B998B"  # Teal/green
EXISTING_COLOR = "#2E294E"  # Dark purple/navy
EVENT_COLOR = "#333333"
EVENT_ALPHA = 0.15

# Custom sequential colormap: white → Voat coral (for heatmap)
VOAT_CMAP = mcolors.LinearSegmentedColormap.from_list(
    'voat_coral_seq',
    ['#FFFFFF', '#FDE4DC', '#FAB8A4', '#F46036', '#B8401F']
)
HLINE_STYLE = {
    "color": "gray",
    "linestyle": "--",
    "linewidth": 2.5,
    "alpha": 0.6,
}
EVENT_LABEL_OFFSET_X = 14

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


def add_panel_label(ax, label, fontsize=12):
    """Prepend panel number to the panel title."""
    title = ax.get_title()
    if title:
        ax.set_title(f"({label}) {title}")
    else:
        ax.set_title(f"({label})", fontsize=fontsize, fontweight="bold")


def add_events_band(ax, label_above=True):
    """Add vertical bands for events with improved visibility."""
    ylim = ax.get_ylim()
    # Extend y-axis downward to make room for labels
    y_range = ylim[1] - ylim[0]
    new_ylim = (ylim[0] - 0.15 * y_range, ylim[1])
    ax.set_ylim(new_ylim)

    for key, date in EVENTS_CHRONO.items():
        # Thicker, more visible lines
        ax.axvline(date, color=EVENT_COLOR, linestyle="--",
                   alpha=0.6, linewidth=1.5, zorder=1)

        # Label at BOTTOM, to the RIGHT of vertical line
        if label_above:
            label = SHORT_EVENT_LABELS.get(key, key)
            ax.annotate(label, xy=(date, new_ylim[0]), xytext=(EVENT_LABEL_OFFSET_X, 2),
                       textcoords='offset points', ha='left', va='bottom',
                       fontsize=9, fontweight='bold', color=EVENT_COLOR,
                       annotation_clip=False)


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

    # Create figure with 9 panels (5x4 grid) - logical narrative flow
    # Row 1: User activity, Row 2: Network structure, Row 3-4: Outcomes, Row 5: Heatmap (centered)
    fig = plt.figure(figsize=(12, 22))  # Taller for 5 rows
    gs = fig.add_gridspec(5, 4, height_ratios=[1, 1, 1, 1, 0.8], hspace=0.4, wspace=0.45)

    # Panel assignments in logical order (per plan):
    # 1: Total Active Users, 2: Users by Status, 3: E-I Index, 4: Hub Rate
    # 5: Degree Ratio, 6: Assortativity, 7: Reputation, 8: Toxicity, 9: Heatmap (centered)
    ax1 = fig.add_subplot(gs[0, 0:2])  # (1) Total Active Users
    ax2 = fig.add_subplot(gs[0, 2:4])  # (2) Active Users by Status
    ax3 = fig.add_subplot(gs[1, 0:2])  # (3) E-I Index
    ax4 = fig.add_subplot(gs[1, 2:4])  # (4) Newcomer Hub Rate
    ax5 = fig.add_subplot(gs[2, 0:2])  # (5) Degree Share / Pop Share
    ax6 = fig.add_subplot(gs[2, 2:4])  # (6) Degree Assortativity
    ax7 = fig.add_subplot(gs[3, 0:2])  # (7) Mean Reputation (with Stack Exchange reference)
    ax8 = fig.add_subplot(gs[3, 2:4])  # (8) Mean ToxiGen classifier probability
    ax9 = fig.add_subplot(gs[4, 1:3])  # (9) Event-Period Heatmap (centered between columns)
    
    # Compute 3-month rolling means
    df_rolling = df.copy()
    for col in ["ei_index", "toxicity_mean_voat", "degree_assortativity_voat", "reputation_mean_voat_agg"]:
        if col in df_rolling.columns:
            df_rolling[f"{col}_roll"] = df_rolling[col].rolling(window=3, center=True, min_periods=1).mean()

    # Load shared data needed for multiple panels
    reddit_tox = load_reddit_toxicity(args.input_file.parent.parent, start_date, end_date)
    active_users_df = load_active_users_by_status(args.input_file.parent.parent, start_date, end_date)

    # =========================================================================
    # PANEL 1: Total Active Users (NEW)
    # =========================================================================
    if active_users_df is not None and not active_users_df.empty:
        total_active = active_users_df["newcomer_active"] + active_users_df["existing_active"]
        total_roll = total_active.rolling(window=3, center=True, min_periods=1).mean()
        ax1.plot(active_users_df["month_dt"], total_active, color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax1.plot(active_users_df["month_dt"], total_roll, color=VOAT_COLOR, linewidth=2.5, label="Total (3-mo avg)")
        ax1.set_ylabel("Active Users (rep > 1)", fontweight="bold")
        ax1.set_title("Total Active Users (Voat)")
        ax1.set_ylim(0, None)
        ax1.legend(loc="upper left", fontsize=8)
        add_events_band(ax1)
    else:
        ax1.text(0.5, 0.5, "Active users data not available",
                ha="center", va="center", transform=ax1.transAxes)
        ax1.set_title("Total Active Users (Voat)")

    # =========================================================================
    # PANEL 2: Active Users by Status (Newcomers vs Existing)
    # =========================================================================
    if active_users_df is not None and not active_users_df.empty:
        active_users_df["newcomer_roll"] = active_users_df["newcomer_active"].rolling(
            window=3, center=True, min_periods=1).mean()
        active_users_df["existing_roll"] = active_users_df["existing_active"].rolling(
            window=3, center=True, min_periods=1).mean()

        ax2.plot(active_users_df["month_dt"], active_users_df["newcomer_active"],
                color=NEWCOMER_COLOR, linewidth=1, alpha=0.3)
        ax2.plot(active_users_df["month_dt"], active_users_df["newcomer_roll"],
                color=NEWCOMER_COLOR, linewidth=2.5, label="Newcomers (3-mo avg)")
        ax2.plot(active_users_df["month_dt"], active_users_df["existing_active"],
                color=EXISTING_COLOR, linewidth=1, alpha=0.3)
        ax2.plot(active_users_df["month_dt"], active_users_df["existing_roll"],
                color=EXISTING_COLOR, linewidth=2.5, label="Existing (3-mo avg)")
        ax2.set_ylabel("Active Users (rep > 1)", fontweight="bold")
        ax2.set_title("Active Users by Status (Voat)")
        ax2.legend(loc="upper left", fontsize=8)
        add_events_band(ax2)
    else:
        ax2.text(0.5, 0.5, "Active users data not available",
                ha="center", va="center", transform=ax2.transAxes)
        ax2.set_title("Active Users by Status (Voat)")

    # =========================================================================
    # PANEL 3: E-I Index
    # =========================================================================
    if "ei_index" in df.columns:
        ax3.plot(df["month_dt"], df["ei_index"], color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax3.plot(df_rolling["month_dt"], df_rolling["ei_index_roll"], color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
        ax3.set_ylabel("E-I Index", fontweight="bold")
        ax3.set_title("E-I Index (Voat)")
        ax3.axhline(0, **HLINE_STYLE)
        ax3.legend(loc="upper left", fontsize=8)
        add_events_band(ax3)

    # =========================================================================
    # PANEL 4: Newcomer Hub Rate
    # =========================================================================
    if degree_df is not None and "newcomer_hub_rate" in degree_df.columns:
        degree_df["newcomer_hub_rate_roll"] = degree_df["newcomer_hub_rate"].rolling(
            window=3, center=True, min_periods=1).mean()

        ax4.plot(degree_df["month_dt"], degree_df["newcomer_hub_rate"],
                color=NEWCOMER_COLOR, linewidth=1, alpha=0.3)
        ax4.plot(degree_df["month_dt"], degree_df["newcomer_hub_rate_roll"],
                color=NEWCOMER_COLOR, linewidth=2.5, label="Hub Rate (3-mo avg)")
        ax4.set_ylabel("Newcomer Hub Rate", fontweight="bold")
        ax4.set_title("Share of Hubs Among Newcomers (Voat)")
        ax4.set_ylim(0, None)
        ax4.legend(loc="upper right", fontsize=8)
        add_events_band(ax4)
    else:
        ax4.text(0.5, 0.5, "Hub rate data not available",
                ha="center", va="center", transform=ax4.transAxes)
        ax4.set_title("Share of Hubs Among Newcomers (Voat)")

    # =========================================================================
    # PANEL 5: Degree Share / Population Share Ratio
    # =========================================================================
    if degree_df is not None and "degree_share_ratio" in degree_df.columns:
        ax5.plot(degree_df["month_dt"], degree_df["degree_share_ratio"],
                color=NEWCOMER_COLOR, linewidth=1, alpha=0.3)
        ax5.plot(degree_df["month_dt"], degree_df["degree_share_ratio_roll"],
                color=NEWCOMER_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
        ax5.axhline(1.0, **HLINE_STYLE, label="Proportional (=1)")
        ax5.set_ylabel("Degree Share / Pop Share", fontweight="bold")
        ax5.set_title("Newcomer Degree Share Ratio (Voat)")
        ax5.legend(loc="upper right", fontsize=8)
        add_events_band(ax5)
    else:
        ax5.text(0.5, 0.5, "Degree dynamics data not available",
                ha="center", va="center", transform=ax5.transAxes)
        ax5.set_title("Newcomer Degree Share Ratio (Voat)")

    # =========================================================================
    # PANEL 6: Degree Assortativity
    # =========================================================================
    if "degree_assortativity_voat" in df.columns:
        ax6.plot(df["month_dt"], df["degree_assortativity_voat"], color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax6.plot(df_rolling["month_dt"], df_rolling["degree_assortativity_voat_roll"], color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")
        ax6.set_ylabel("Assortativity", fontweight="bold")
        ax6.set_title("Degree Assortativity (Voat)")
        ax6.axhline(0, **HLINE_STYLE)
        ax6.legend(loc="upper left", fontsize=8)
        add_events_band(ax6)

    # Format X axes for panels 1-6
    for ax in [ax1, ax2, ax3, ax4, ax5, ax6]:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.set_xlabel("Year")
    
    # =========================================================================
    # PANEL 7: Mean Reputation (with Stack Exchange 4.5 reference)
    # =========================================================================
    if "reputation_mean_voat_agg" in df.columns:
        ax7.plot(df["month_dt"], df["reputation_mean_voat_agg"],
                color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax7.plot(df_rolling["month_dt"], df_rolling["reputation_mean_voat_agg_roll"],
                color=VOAT_COLOR, linewidth=2.5, label="Mean (3-mo avg)")
        # Add 4.5 Stack Exchange reference line.
        ax7.axhline(4.5, **HLINE_STYLE,
                   label="Stack Exchange reference 4.5", zorder=2)
        ax7.set_ylabel("Mean Reputation", fontweight="bold")
        ax7.set_title("Mean Reputation (Voat, active users)")
        ax7.legend(loc="upper right", fontsize=8, frameon=True,
                  facecolor='white', edgecolor='none', framealpha=0.8)
        ax7.xaxis.set_major_locator(mdates.YearLocator())
        ax7.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax7.set_xlabel("Year")
        add_events_band(ax7)
    else:
        ax7.text(0.5, 0.5, "Reputation data not available",
                ha="center", va="center", transform=ax7.transAxes)
        ax7.set_title("Mean Reputation (Voat)")

    # =========================================================================
    # PANEL 8: Mean ToxiGen classifier probability (Voat only)
    # =========================================================================
    if "toxicity_mean_voat" in df.columns:
        ax8.plot(df["month_dt"], df["toxicity_mean_voat"], color=VOAT_COLOR, linewidth=1, alpha=0.3)
        ax8.plot(df_rolling["month_dt"], df_rolling["toxicity_mean_voat_roll"], color=VOAT_COLOR, linewidth=2.5, label="Voat (3-mo avg)")

    # Reddit toxicity removed per user request
    # if reddit_tox is not None and not reddit_tox.empty:
    #     reddit_tox["tox_roll"] = reddit_tox["toxicity_mean"].rolling(window=3, center=True, min_periods=1).mean()
    #     ax8.plot(reddit_tox["month_dt"], reddit_tox["toxicity_mean"], color=REDDIT_COLOR, linewidth=1, alpha=0.3)
    #     ax8.plot(reddit_tox["month_dt"], reddit_tox["tox_roll"], color=REDDIT_COLOR, linewidth=2.5, label="Reddit (3-mo avg)")

    ax8.set_ylabel("Mean ToxiGen classifier probability", fontweight="bold")
    ax8.set_title("Mean ToxiGen classifier probability (Voat)")
    ax8.legend(loc="upper left", fontsize=8)
    ax8.xaxis.set_major_locator(mdates.YearLocator())
    ax8.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax8.set_xlabel("Year")
    add_events_band(ax8)

    # =========================================================================
    # PANEL 9: Event-Period Heatmap (full width)
    # =========================================================================
    if heatmap_df is not None and not heatmap_pivot.empty:
        # Enhanced heatmap with better styling
        cbar_kws = {
            'label': 'Classifier-probability difference\n(Voat − Reddit)',
            'shrink': 0.6,
            'aspect': 20,
            'pad': 0.02
        }
        sns.heatmap(
            heatmap_pivot,
            ax=ax9,
            annot=True,
            annot_kws={"size": 11, "weight": "bold"},
            fmt=".2f",
            cmap=VOAT_CMAP,  # Sequential purple (Voat-branded)
            cbar_kws=cbar_kws,
            linewidths=2,
            linecolor="white",
            vmin=-0.05,
            vmax=0.18,
            square=False  # Allow rectangular for full-width layout
        )
        ax9.set_title("Classifier-probability difference by event period",
                     fontweight="bold", fontsize=11, pad=12)
        ax9.set_xlabel("Event Period", fontweight="bold", fontsize=11)
        ax9.set_ylabel("Community", fontweight="bold", fontsize=11)

        # Period labels using event names
        period_labels = ["FPH→PG", "PG→GA", "GA→TD", "TD→End"]
        ax9.set_xticklabels(period_labels, rotation=0, ha="center", fontsize=10)
        ax9.set_yticklabels(ax9.get_yticklabels(), rotation=0, fontsize=10)
    else:
        ax9.text(0.5, 0.5, "Heatmap data not available",
                ha="center", va="center", transform=ax9.transAxes)
        ax9.set_title("Voat-Reddit classifier-probability difference by event period")
    
    # =========================================================================
    # Add panel labels (1), (2), etc.
    # =========================================================================
    for i, ax in enumerate([ax1, ax2, ax3, ax4, ax5, ax6, ax7, ax8]):
        add_panel_label(ax, i + 1)
    add_panel_label(ax9, 9)

    # =========================================================================
    # Save figure - publication quality (300 DPI + PDF)
    # =========================================================================
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # PNG at 300 DPI
    out_path = args.output_dir / "voat_global_summary.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight",
                facecolor='white', edgecolor='none')
    print(f"Wrote {out_path}")

    # PDF for vector quality
    out_path_pdf = args.output_dir / "voat_global_summary.pdf"
    plt.savefig(out_path_pdf, bbox_inches="tight",
                facecolor='white', edgecolor='none')
    print(f"Wrote {out_path_pdf}")


if __name__ == "__main__":
    main()
