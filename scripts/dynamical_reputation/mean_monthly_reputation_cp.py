#!/usr/bin/env python3
import os
import argparse
import logging
from typing import Optional

import pandas as pd


def _ensure_month_str(df: pd.DataFrame, date_col: str = "date", tmin_col: str = "t_min", day_col: str = "day") -> pd.DataFrame:
    """Ensure a 'month' column (YYYY-MM) exists in the reputation DataFrame.

    Supports two input formats for reputation outputs:
    - With a 'date' column (datetime-like or string). We'll parse to UTC and derive month.
    - Without 'date', but with 't_min' (epoch seconds) and 'day' offset; we reconstruct the date.
    """
    out = df.copy()
    if "month" in out.columns:
        return out

    if date_col in out.columns:
        out["month"] = pd.to_datetime(out[date_col], errors="coerce", utc=True).dt.strftime("%Y-%m")
        return out

    # Fallback: rebuild date from t_min + day
    if tmin_col in out.columns and day_col in out.columns:
        tmin = pd.to_numeric(out[tmin_col], errors="coerce")
        # seconds vs milliseconds heuristic
        unit = "ms" if tmin.dropna().median() > 1e11 else "s"
        base = pd.to_datetime(tmin, unit=unit, utc=True, errors="coerce")
        out["date"] = base + pd.to_timedelta(pd.to_numeric(out[day_col], errors="coerce").fillna(0).astype(int), unit="D")
        out["month"] = pd.to_datetime(out["date"], errors="coerce", utc=True).dt.strftime("%Y-%m")
        return out

    raise ValueError("Reputation input missing both 'date' and ('t_min','day') columns; cannot derive month")


def _read_cp_files(cp_base_dir: str, platform: str, community: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read CP labels and block stats for a given platform/community.

    Expects files named '<platform>_<community>_cp_labels.csv' and '<platform>_<community>_cp_block_stats.csv'
    under '<cp_base_dir>/<platform>/results/'.
    """
    plat = platform.lower()
    comm = community.lower()
    res_dir = os.path.join(cp_base_dir, plat, "results")
    labels_fp = os.path.join(res_dir, f"{plat}_{comm}_cp_labels.csv")
    block_fp = os.path.join(res_dir, f"{plat}_{comm}_cp_block_stats.csv")
    if not os.path.isfile(labels_fp):
        raise FileNotFoundError(f"CP labels not found: {labels_fp}")
    if not os.path.isfile(block_fp):
        raise FileNotFoundError(f"CP block stats not found: {block_fp}")
    labels = pd.read_csv(labels_fp)
    blocks = pd.read_csv(block_fp)
    # normalize expected columns
    need_lab = {"community", "window", "node_id", "label"}
    missing = [c for c in need_lab if c not in labels.columns]
    if missing:
        raise ValueError(f"CP labels missing columns {missing}; got {list(labels.columns)}")
    need_blk = {"community", "window", "ns_core", "ns_peri"}
    missing_b = [c for c in need_blk if c not in blocks.columns]
    if missing_b:
        raise ValueError(f"CP block stats missing columns {missing_b}; got {list(blocks.columns)}")
    return labels, blocks


def _read_reputation(results_rep_base: str, platform: str, community: str, explicit_file: Optional[str] = None) -> pd.DataFrame:
    """Read precomputed per-user daily reputation. Accept an explicit file path or try common locations.

    Supported locations (in order):
    - explicit_file if provided
    - results/reputation/<community>/<platform>/results/<platform>_<community>_user_daily_reputation.(parquet|csv)
    - results/reputation/<platform>/<community>/<platform>/results/<platform>_<community>_user_daily_reputation.(parquet|csv)
    - results/reputation/<platform>/results/<platform>_<community>_user_daily_reputation.(parquet|csv)
    """
    tried: list[str] = []
    if explicit_file:
        tried.append(explicit_file)
    # Common patterns observed in this repo
    plat = platform.lower()
    comm = community.lower()
    tried.append(os.path.join(results_rep_base, comm, plat, "results", f"{plat}_{comm}_user_daily_reputation.parquet"))
    tried.append(os.path.join(results_rep_base, comm, plat, "results", f"{plat}_{comm}_user_daily_reputation.csv"))
    tried.append(os.path.join(results_rep_base, plat, comm, plat, "results", f"{plat}_{comm}_user_daily_reputation.parquet"))
    tried.append(os.path.join(results_rep_base, plat, comm, plat, "results", f"{plat}_{comm}_user_daily_reputation.csv"))
    tried.append(os.path.join(results_rep_base, plat, "results", f"{plat}_{comm}_user_daily_reputation.parquet"))
    tried.append(os.path.join(results_rep_base, plat, "results", f"{plat}_{comm}_user_daily_reputation.csv"))

    for fp in tried:
        if not fp:
            continue
        if os.path.isfile(fp):
            if fp.lower().endswith(".parquet"):
                try:
                    return pd.read_parquet(fp)
                except Exception as e:
                    logging.warning("Failed to read parquet %s: %s", fp, e)
            else:
                try:
                    return pd.read_csv(fp)
                except Exception as e:
                    logging.warning("Failed to read csv %s: %s", fp, e)
    raise FileNotFoundError("Could not locate reputation file in expected locations; pass --reputation-file explicitly")


def compute_monthly_means_cp(labels_df: pd.DataFrame, blocks_df: pd.DataFrame, rep_df: pd.DataFrame) -> pd.DataFrame:
    """Compute monthly reputation summaries for core/periphery.

    Mean (active-only):
    - For each day and label, include only users with reputation >= 1.
    - Daily mean = sum(reputation) / count(active users).
    - Monthly mean = average of daily means over days with at least 1 active user.

    Median (active-only, per-user monthly):
    - For each (month, user, label), average the user's daily reputation over active days (rep >= 1).
    - Take the median of these user-month means per label.

    We also report:
    - Average daily active users per month per label.
    - Total number of active users per month per label (unique users with reputation >= 1 at least once in the month).

        Returns columns:
            ['month',
             'core_mean_rep_active','periphery_mean_rep_active',
             'core_median_rep_active','periphery_median_rep_active',
             'core_active_daily_avg','periphery_active_daily_avg',
             'core_active_users','periphery_active_users',
             'n_core','n_periphery']
    """
    # Normalize labels and reputation
    lab = labels_df.rename(columns={"window": "month", "node_id": "user_id"})[["month", "user_id", "label"]].copy()
    lab["label"] = pd.to_numeric(lab["label"], errors="coerce").fillna(-1).astype(int)
    rep = rep_df.copy()
    rep["user_id"] = rep["user_id"].astype(str)
    lab["user_id"] = lab["user_id"].astype(str)
    rep = _ensure_month_str(rep)
    if "date" not in rep.columns:
        raise ValueError("Reputation input must include or allow derivation of a 'date' column")
    rep["date"] = pd.to_datetime(rep["date"], errors="coerce", utc=True).dt.floor("D")

    # Join monthly labels
    j = rep.merge(lab, on=["month", "user_id"], how="inner")

    # Filter active rows (rep >= 1)
    active = j[pd.to_numeric(j["reputation"], errors="coerce") >= 1].copy()

    # Daily sums and active counts
    daily_act = active.groupby(["month","date","label"], as_index=False).agg(
        sum_rep=("reputation","sum"),
        active_users=("user_id","nunique"),
    )

    # Per-user monthly mean on active days for median
    per_user = (
        active.groupby(["month","label","user_id"], as_index=False)
              .agg(u_mean_rep=("reputation","mean"))
    )
    med_by_group = per_user.groupby(["month","label"], as_index=False).agg(median_rep=("u_mean_rep","median"))
    med_map = {(r["month"], int(r["label"])): float(r["median_rep"]) for _, r in med_by_group.iterrows()}

    # Monthly active user counts per label (unique users with rep>=1 at least one day in the month)
    active_users_monthly = (
        active.groupby(["month","label"], as_index=False)
              .agg(active_users_month=("user_id","nunique"))
    )
    act_map = {(r["month"], int(r["label"])): int(r["active_users_month"]) for _, r in active_users_monthly.iterrows()}

    # Group sizes from block stats (for reference)
    sizes = blocks_df[["window","ns_core","ns_peri"]].rename(columns={"window":"month"}).copy()

    months = sorted(set(sizes["month"].astype(str)))
    out_rows = []
    for m in months:
        # sizes
        srow = sizes[sizes["month"].astype(str) == m]
        if srow.empty:
            continue
        n_core = pd.to_numeric(srow["ns_core"], errors="coerce").iloc[0]
        n_peri = pd.to_numeric(srow["ns_peri"], errors="coerce").iloc[0]

        # Daily means for this month per label
        dm = daily_act[daily_act["month"].astype(str) == m]
        if dm.empty:
            core_mean = float('nan'); peri_mean = float('nan')
            core_active_avg = float('nan'); peri_active_avg = float('nan')
        else:
            # compute daily mean rep per label only for days with at least 1 active
            dm_core = dm[dm["label"]==0]
            dm_peri = dm[dm["label"]==1]
            core_mean = float((dm_core["sum_rep"] / dm_core["active_users"]).mean()) if not dm_core.empty else float('nan')
            peri_mean = float((dm_peri["sum_rep"] / dm_peri["active_users"]).mean()) if not dm_peri.empty else float('nan')
            core_active_avg = float(dm_core["active_users"].mean()) if not dm_core.empty else float('nan')
            peri_active_avg = float(dm_peri["active_users"].mean()) if not dm_peri.empty else float('nan')

        # Active user totals for the month per label
        core_active_users = act_map.get((m,0), 0)
        periphery_active_users = act_map.get((m,1), 0)

        # Cast group sizes robustly
        try:
            n_core_i = int(n_core) if not pd.isna(n_core) else 0
        except Exception:
            n_core_i = 0
        try:
            n_peri_i = int(n_peri) if not pd.isna(n_peri) else 0
        except Exception:
            n_peri_i = 0

        out_rows.append({
            "month": m,
            "core_mean_rep_active": core_mean,
            "periphery_mean_rep_active": peri_mean,
            "core_median_rep_active": med_map.get((m,0), float('nan')),
            "periphery_median_rep_active": med_map.get((m,1), float('nan')),
            "core_active_daily_avg": core_active_avg,
            "periphery_active_daily_avg": peri_active_avg,
            "core_active_users": core_active_users,
            "periphery_active_users": periphery_active_users,
            "n_core": n_core_i,
            "n_periphery": n_peri_i,
        })

    out = pd.DataFrame(out_rows, columns=[
        "month",
        "core_mean_rep_active","periphery_mean_rep_active",
        "core_median_rep_active","periphery_median_rep_active",
        "core_active_daily_avg","periphery_active_daily_avg",
        "core_active_users","periphery_active_users",
        "n_core","n_periphery",
    ])
    try:
        out["_order"] = pd.to_datetime(out["month"] + "-01", errors="coerce")
        out = out.sort_values("_order").drop(columns=["_order"])
    except Exception:
        pass
    return out


def decide_output_path(base_out: str, platform: str, community: str, rep_source_path: Optional[str] = None) -> str:
    """Choose an output CSV path consistent with repo guidelines and existing structure.

    Preference order:
    - If rep_source_path is provided and contains a 'results' directory, write alongside it.
    - Else write to '<base_out>/<platform>/results/'.
    Filename: '<platform>_<community>_cp_monthly_reputation.csv'
    """
    plat = platform.lower()
    comm = community.lower()
    fname = f"{plat}_{comm}_cp_monthly_reputation.csv"
    if rep_source_path:
        # try to find 'results' ancestor in path
        d = os.path.dirname(rep_source_path)
        # ascend until we find a 'results' dir or stop at base_out
        for _ in range(5):
            if os.path.basename(d) == "results":
                os.makedirs(d, exist_ok=True)
                return os.path.join(d, fname)
            nd = os.path.dirname(d)
            if not nd or nd == d:
                break
            d = nd
    # default
    results_dir = os.path.join(base_out, plat, "results")
    os.makedirs(results_dir, exist_ok=True)
    return os.path.join(results_dir, fname)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute monthly mean reputation by core/periphery and include group sizes.")
    p.add_argument("--platform", required=True, choices=["voat", "reddit"], help="Platform")
    p.add_argument("--community", required=True, help="Community name (subreddit/subverse)")
    p.add_argument("--cp-dir", default=os.path.join("results", "core-periphery"), help="Core-periphery results base directory")
    p.add_argument("--reputation-dir", default=os.path.join("results", "reputation"), help="Base directory for precomputed reputation outputs")
    p.add_argument("--reputation-file", help="Explicit path to per-user daily reputation CSV/Parquet (optional)")
    p.add_argument("--output-dir", default=os.path.join("results", "reputation"), help="Base output directory (category root)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]) 
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")

    labels_df, blocks_df = _read_cp_files(args.cp_dir, args.platform, args.community)
    rep_df = _read_reputation(args.reputation_dir, args.platform, args.community, explicit_file=args.reputation_file)

    logging.info("Loaded: labels %d rows, blocks %d rows, reputation %d rows", len(labels_df), len(blocks_df), len(rep_df))

    out_df = compute_monthly_means_cp(labels_df, blocks_df, rep_df)

    out_path = decide_output_path(args.output_dir, args.platform, args.community, rep_source_path=args.reputation_file)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_df.to_csv(out_path, index=False)

    logging.info("Wrote %s (%d rows)", out_path, len(out_df))


if __name__ == "__main__":
    main()
