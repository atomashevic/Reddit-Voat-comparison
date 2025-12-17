#!/usr/bin/env python3
"""
Package C2: Rolling-tenure cohort sensitivity for E-I index.

Recomputes newcomer/existing partition and E-I index using a tenure-based
definition:
  newcomer iff first_seen_dt >= (current_month - tenure_months).

This addresses circularity concerns in event-based cohorts.

Outputs:
  - Per-community CSV: c2_ei_rolling_tenure<k>_<community>.csv
  - Global mean CSV: c2_ei_rolling_tenure<k>_global.csv
  - Text summary: c2_ei_rolling_tenure<k>_summary.txt
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from scripts.migration_utils import EVENTS  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_COMMUNITIES = ["funny", "gaming", "gifs", "pics", "technology", "videos"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="C2 rolling cohort E-I sensitivity.")
    p.add_argument("--communities", nargs="*", default=None)
    p.add_argument(
        "--tenure-months",
        type=int,
        default=6,
        help="Rolling newcomer window in months (default 6).",
    )
    p.add_argument(
        "--networks-dir",
        type=Path,
        default=REPO_ROOT / "results" / "networks",
        help="Directory with monthly edge lists.",
    )
    p.add_argument(
        "--results-dir",
        type=Path,
        default=REPO_ROOT / "results",
        help="Base results directory (for event-based E-I files).",
    )
    p.add_argument(
        "--labels-dir",
        type=Path,
        default=REPO_ROOT / "results" / "voat",
        help="Directory containing newcomer label CSVs.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "results" / "basic" / "compare" / "results",
        help="Output directory for CSV and TXT summaries.",
    )
    p.add_argument("--min-month", type=str, default=None)
    p.add_argument("--max-month", type=str, default=None)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def parse_month_from_filename(path: Path) -> str:
    match = re.search(r"(19|20)\d{2}-\d{2}$", path.stem)
    if not match:
        raise ValueError(f"Unable to parse month from filename: {path}")
    return match.group(0)


def load_first_seen_map(labels_dir: Path, community: str) -> Dict[str, pd.Timestamp]:
    candidates = [
        labels_dir / community / f"voat_{community}_newcomer_labels.csv",
        labels_dir / f"voat_{community}_newcomer_labels.csv",
    ]
    labels_path = next((p for p in candidates if p.exists()), None)
    if labels_path is None:
        raise FileNotFoundError(f"Newcomer labels not found for {community}: {candidates}")

    df = pd.read_csv(labels_path, dtype={"user_id": str})
    if "first_month" in df.columns:
        df["first_seen_dt"] = pd.to_datetime(df["first_month"] + "-01", errors="coerce")
    elif "first_seen_dt" in df.columns:
        df["first_seen_dt"] = pd.to_datetime(df["first_seen_dt"], errors="coerce")
    else:
        raise ValueError(f"Labels file missing first_month/first_seen_dt: {labels_path}")

    return dict(zip(df["user_id"].astype(str), df["first_seen_dt"]))


def load_event_ei(results_dir: Path, community: str) -> pd.DataFrame:
    candidates = [
        results_dir / "voat" / community / f"{community}_newcomer_partition.csv",
        results_dir / "basic" / "voat" / "results" / f"{community}_newcomer_partition.csv",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        return pd.DataFrame(columns=["month", "ei_index_event"])
    df = pd.read_csv(path, usecols=["month", "ei_index"])
    df = df.rename(columns={"ei_index": "ei_index_event"})
    df["month"] = df["month"].astype(str)
    return df


def rolling_label(first_seen: pd.Timestamp, month_dt: pd.Timestamp, tenure_months: int) -> str:
    if pd.isna(first_seen):
        return "existing"
    cutoff = month_dt - pd.DateOffset(months=tenure_months)
    return "newcomer" if first_seen >= cutoff else "existing"


def compute_month_ei(
    edge_file: Path,
    first_seen_map: Dict[str, pd.Timestamp],
    tenure_months: int,
) -> Optional[Dict[str, object]]:
    edges = pd.read_csv(edge_file, sep=r"\s+", names=["source", "target"], dtype=str, engine="python")
    edges = edges.dropna(subset=["source", "target"])
    if edges.empty:
        return None

    month = parse_month_from_filename(edge_file)
    month_dt = pd.to_datetime(month + "-01")

    # Collapse to unique undirected edges to match unweighted Graph E-I.
    pairs = edges[["source", "target"]].astype(str)
    a = pairs.min(axis=1)
    b = pairs.max(axis=1)
    unique_pairs = pd.DataFrame({"a": a, "b": b}).drop_duplicates()
    if unique_pairs.empty:
        return None

    nodes = pd.Index(pd.unique(unique_pairs[["a", "b"]].values.ravel("K"))).tolist()
    labels_map: Dict[str, str] = {}
    for n in nodes:
        fs = first_seen_map.get(str(n), pd.NaT)
        labels_map[str(n)] = rolling_label(fs, month_dt, tenure_months)

    n_new = sum(1 for n in nodes if labels_map[str(n)] == "newcomer")
    n_old = len(nodes) - n_new

    total_edges = int(len(unique_pairs))
    a_lab = unique_pairs["a"].map(labels_map).fillna("existing")
    b_lab = unique_pairs["b"].map(labels_map).fillna("existing")
    same_edges = int((a_lab == b_lab).sum())
    between_edges = total_edges - same_edges
    ei_index = (between_edges - same_edges) / total_edges if total_edges > 0 else float("nan")

    return {
        "month": month,
        "n_nodes": len(nodes),
        "n_edges": total_edges,
        "n_newcomers_rolling": n_new,
        "n_existing_rolling": n_old,
        "ei_index_rolling": ei_index,
    }


def filter_months(df: pd.DataFrame, min_month: Optional[str], max_month: Optional[str]) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["month_dt"] = pd.to_datetime(df["month"] + "-01", errors="coerce")
    if min_month:
        df = df[df["month_dt"] >= pd.Timestamp(min_month + "-01")]
    if max_month:
        df = df[df["month_dt"] <= pd.Timestamp(max_month + "-01")]
    return df.drop(columns=["month_dt"])


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    communities = args.communities or DEFAULT_COMMUNITIES
    tenure = int(args.tenure_months)

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    all_frames: List[pd.DataFrame] = []
    summary_lines: List[str] = []
    summary_lines.append(f"Package C2: Rolling-tenure E-I sensitivity (tenure={tenure} months)")
    summary_lines.append("=" * 72)
    summary_lines.append(f"Communities: {', '.join(communities)}")
    summary_lines.append("")

    ga_cutoff = pd.Timestamp(EVENTS["B"].strftime("%Y-%m-01"))

    for community in communities:
        first_seen_map = load_first_seen_map(args.labels_dir, community)
        net_dir = args.networks_dir / "voat" / f"{community}_monthly"
        if not net_dir.exists():
            raise FileNotFoundError(f"Network dir not found: {net_dir}")

        rows: List[Dict[str, object]] = []
        edge_files = sorted(net_dir.glob(f"{community}_*.txt"))
        logger.info(f"{community}: {len(edge_files)} monthly snapshots")

        for edge_file in edge_files:
            try:
                row = compute_month_ei(edge_file, first_seen_map, tenure)
            except Exception as e:
                logger.warning(f"{community}: failed {edge_file.name}: {e}")
                continue
            if row:
                rows.append(row)

        rolling_df = pd.DataFrame(rows)
        rolling_df = filter_months(rolling_df, args.min_month, args.max_month)
        rolling_df = rolling_df.sort_values("month").reset_index(drop=True)

        event_df = load_event_ei(args.results_dir, community)
        merged = rolling_df.merge(event_df, on="month", how="left")

        out_path = out_dir / f"c2_ei_rolling_tenure{tenure}_{community}.csv"
        merged.to_csv(out_path, index=False)
        all_frames.append(merged.assign(community=community))

        # Summary stats
        overlap = merged.dropna(subset=["ei_index_rolling", "ei_index_event"])
        if not overlap.empty:
            corr = float(overlap["ei_index_rolling"].corr(overlap["ei_index_event"]))
        else:
            corr = float("nan")

        merged["month_dt"] = pd.to_datetime(merged["month"] + "-01", errors="coerce")
        pre = merged[merged["month_dt"] < ga_cutoff]
        post = merged[merged["month_dt"] >= ga_cutoff]
        pre_mean = float(pd.to_numeric(pre["ei_index_rolling"], errors="coerce").mean()) if not pre.empty else float("nan")
        post_mean = float(pd.to_numeric(post["ei_index_rolling"], errors="coerce").mean()) if not post.empty else float("nan")

        summary_lines.append(f"{community}: corr(event, rolling)={corr:.3f}, pre‑GA mean={pre_mean:.3f}, post‑GA mean={post_mean:.3f}")

    # Global unweighted mean across communities by month
    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        global_df = (
            combined.groupby("month", as_index=False)
            .mean(numeric_only=True)
            .sort_values("month")
        )
        global_path = out_dir / f"c2_ei_rolling_tenure{tenure}_global.csv"
        global_df.to_csv(global_path, index=False)

        overlap = global_df.dropna(subset=["ei_index_rolling", "ei_index_event"])
        corr_global = float(overlap["ei_index_rolling"].corr(overlap["ei_index_event"])) if not overlap.empty else float("nan")
        global_df["month_dt"] = pd.to_datetime(global_df["month"] + "-01", errors="coerce")
        pre = global_df[global_df["month_dt"] < ga_cutoff]
        post = global_df[global_df["month_dt"] >= ga_cutoff]
        pre_mean = float(pd.to_numeric(pre["ei_index_rolling"], errors="coerce").mean()) if not pre.empty else float("nan")
        post_mean = float(pd.to_numeric(post["ei_index_rolling"], errors="coerce").mean()) if not post.empty else float("nan")

        summary_lines.append("")
        summary_lines.append(f"Global: corr(event, rolling)={corr_global:.3f}, pre‑GA mean={pre_mean:.3f}, post‑GA mean={post_mean:.3f}")

    summary_path = out_dir / f"c2_ei_rolling_tenure{tenure}_summary.txt"
    summary_path.write_text("\n".join(summary_lines))
    logger.info(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
