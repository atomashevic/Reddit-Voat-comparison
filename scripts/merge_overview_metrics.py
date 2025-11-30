#!/usr/bin/env python3
"""Merge monthly metrics for the overview figure and write summary CSVs.

Outputs:
- compare/<community>_monthly_metrics.csv  (wide, one row per month)
- compare/<community>_summary.csv         (mean/median per metric)
- voat/<community>_newcomer_partition.csv (assortativity / E-I over time)
"""

import argparse
from pathlib import Path
import pandas as pd


def load_monthly(path: Path, platform: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["platform"] = platform
    df["month"] = df["month"].astype(str)
    return df


def load_reputation_data(backup_path: Path, platform: str, community: str) -> pd.DataFrame:
    """Load and aggregate reputation from backup CP monthly reputation files."""
    rep_path = backup_path / "results" / "reputation" / platform / "results" / f"{platform}_{community}_cp_monthly_reputation.csv"
    if not rep_path.exists():
        # Try alternative location
        rep_path = backup_path / "results" / "reputation" / community / platform / "results" / f"{platform}_{community}_cp_monthly_reputation.csv"
    if not rep_path.exists():
        return pd.DataFrame()
    
    rep_df = pd.read_csv(rep_path)
    rep_df["month"] = rep_df["month"].astype(str)
    
    # Compute weighted average of core and periphery reputation
    # Use active users as weights
    rep_df["reputation_mean"] = (
        (rep_df["core_mean_rep_active"] * rep_df["core_active_users"]).fillna(0) +
        (rep_df["periphery_mean_rep_active"] * rep_df["periphery_active_users"]).fillna(0)
    ) / (rep_df["core_active_users"].fillna(0) + rep_df["periphery_active_users"].fillna(0))
    
    return rep_df[["month", "reputation_mean"]]


def pivot_metric(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    subset = df[["month", "platform", metric]].copy()
    wide = subset.pivot(index="month", columns="platform", values=metric)
    wide.columns = [f"{metric}_{c}" for c in wide.columns]
    wide = wide.reset_index()
    return wide


def attach_bootstrap_bands(monthly: pd.DataFrame, bootstrap_path: Path) -> pd.DataFrame:
    if not bootstrap_path.exists():
        return monthly
    bs = pd.read_csv(bootstrap_path)
    if not {"metric", "percentile", "value", "month"}.issubset(bs.columns):
        return monthly
    bs["month"] = bs["month"].astype(str)
    bands = {}
    for metric in ["toxicity_mean", "vader_mean"]:
        sub = bs[bs["metric"] == metric]
        if sub.empty:
            continue
        pivot = sub.pivot_table(index="month", columns="percentile", values="value")
        for p in [5, 50, 95]:
            if p in pivot.columns:
                bands[f"{metric}_p{p}"] = pivot[p]
    if not bands:
        return monthly
    band_df = pd.DataFrame(bands).reset_index().rename(columns={"index": "month"})
    merged = monthly.merge(band_df, on="month", how="left")
    return merged


def save_partition(partition_src: Path, out_path: Path) -> pd.DataFrame:
    part_df = pd.read_csv(partition_src)
    keep_cols = [c for c in part_df.columns if c in {"month", "assortativity", "ei_index", "n_newcomers", "n_existing"}]
    part_df = part_df[keep_cols].copy()
    part_df.to_csv(out_path, index=False)
    return part_df


def write_summary(monthly: pd.DataFrame, out_path: Path) -> None:
    numeric_cols = [c for c in monthly.columns if c != "month" and pd.api.types.is_numeric_dtype(monthly[c])]
    rows = []
    for col in numeric_cols:
        series = monthly[col]
        rows.append(
            {
                "metric": col,
                "mean": series.mean(),
                "median": series.median(),
            }
        )
    pd.DataFrame(rows).to_csv(out_path, index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--results-root", type=Path, required=True, help="results root dir")
    parser.add_argument("--compare-dir", type=Path, required=True, help="output dir for merged metrics")
    parser.add_argument("--output-dir", type=Path, help="ignored (legacy compatibility)")
    parser.add_argument("--backup-root", type=Path, default=Path("backup"), help="backup directory with reputation data")
    args = parser.parse_args()

    community = args.community
    results_root = args.results_root
    compare_dir = args.compare_dir
    backup_root = args.backup_root

    # Adjusted paths for new structure: results/{platform}/{community}/...
    reddit_monthly = results_root / "reddit" / community / f"reddit_{community}_monthly_aggregates.csv"
    voat_monthly = results_root / "voat" / community / f"voat_{community}_monthly_aggregates.csv"
    bootstrap_path = compare_dir / f"{community}_global_bootstrap_summary.csv"
    
    # Partition source/dest
    partition_src = results_root / "voat" / community / f"voat_{community}_monthly_newcomer_analysis.csv"
    partition_out = results_root / "voat" / community / f"{community}_newcomer_partition.csv"

    r_df = load_monthly(reddit_monthly, "reddit")
    v_df = load_monthly(voat_monthly, "voat")
    
    # Load reputation data from backup
    r_rep = load_reputation_data(backup_root, "reddit", community)
    v_rep = load_reputation_data(backup_root, "voat", community)
    
    # Merge reputation into monthly data
    if not r_rep.empty:
        r_df = r_df.merge(r_rep, on="month", how="left", suffixes=("", "_from_backup"))
        # Override reputation_mean with backup data
        if "reputation_mean_from_backup" in r_df.columns:
            r_df["reputation_mean"] = r_df["reputation_mean_from_backup"].fillna(r_df["reputation_mean"])
            r_df = r_df.drop(columns=["reputation_mean_from_backup"])
    
    if not v_rep.empty:
        v_df = v_df.merge(v_rep, on="month", how="left", suffixes=("", "_from_backup"))
        # Override reputation_mean with backup data
        if "reputation_mean_from_backup" in v_df.columns:
            v_df["reputation_mean"] = v_df["reputation_mean_from_backup"].fillna(v_df["reputation_mean"])
            v_df = v_df.drop(columns=["reputation_mean_from_backup"])
    
    base = pd.concat([r_df, v_df], ignore_index=True)

    metrics = [
        "toxicity_mean",
        "vader_mean",
        "reputation_mean",
        "mean_degree",
        "active_users",
        "degree_assortativity",
        "mean_clustering",
    ]

    merged = pd.DataFrame({"month": sorted(base["month"].unique())})
    for metric in metrics:
        wide = pivot_metric(base, metric)
        merged = merged.merge(wide, on="month", how="left")

    # Attach E/I index from partition file
    if partition_src.exists():
        partition_df = pd.read_csv(partition_src)
        partition_df["month"] = partition_df["month"].astype(str)
        if "ei_index" in partition_df.columns:
            ei_df = partition_df[["month", "ei_index"]].copy()
            merged = merged.merge(ei_df, on="month", how="left")

    merged = attach_bootstrap_bands(merged, bootstrap_path)

    compare_out = compare_dir / f"{community}_monthly_metrics.csv"
    merged.to_csv(compare_out, index=False)

    summary_out = compare_dir / f"{community}_summary.csv"
    write_summary(merged, summary_out)

    if partition_src.exists():
        partition_df = save_partition(partition_src, partition_out)
        print(f"wrote {partition_out} ({len(partition_df)} rows)")
    else:
        print(f"Partition file not found: {partition_src} - skipping")

    print(f"wrote {compare_out}")
    print(f"wrote {summary_out}")


if __name__ == "__main__":
    main()
