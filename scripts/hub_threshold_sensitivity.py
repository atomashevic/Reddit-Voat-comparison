#!/usr/bin/env python3
"""
Package C1: Hub-threshold sensitivity for newcomer centrality.

Recomputes newcomer hub metrics using multiple hub cutoffs (top X% by degree)
to test robustness of the "no hub capture" finding.

For each month/community:
  - Build an undirected, unweighted interaction graph from the monthly edge list.
  - Label users as newcomer/existing using event-based cohort logic.
  - For each hub fraction f:
      * hub threshold = degree quantile (1-f) of all users
      * newcomer_hub_rate_f = fraction of newcomers in hubs
      * newcomer_hub_share_f = fraction of hubs that are newcomers

Outputs:
  - Per-community CSV: c1_hub_threshold_sensitivity_<community>.csv
  - Global mean CSV: c1_hub_threshold_sensitivity_global.csv
  - Text summary: c1_hub_threshold_sensitivity_summary.txt
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from scripts.migration_utils import newcomer_label_for_month  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_COMMUNITIES = ["funny", "gaming", "gifs", "pics", "technology", "videos"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="C1 hub-threshold sensitivity.")
    p.add_argument("--communities", nargs="*", default=None)
    p.add_argument(
        "--hub-fractions",
        nargs="*",
        type=float,
        default=[0.05, 0.10, 0.20],
        help="Hub cutoffs as top fractions by degree (default: 0.05 0.10 0.20).",
    )
    p.add_argument(
        "--networks-dir",
        type=Path,
        default=REPO_ROOT / "results" / "networks",
        help="Directory with monthly edge lists.",
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


def compute_month_metrics(
    edge_file: Path,
    first_seen_map: Dict[str, pd.Timestamp],
    hub_fractions: List[float],
) -> Optional[Dict[str, object]]:
    edges = pd.read_csv(edge_file, sep=r"\s+", names=["source", "target"], dtype=str, engine="python")
    edges = edges.dropna(subset=["source", "target"])
    if edges.empty:
        return None

    month = parse_month_from_filename(edge_file)
    month_dt = pd.to_datetime(month + "-01")

    # Collapse to unique undirected edges to match unweighted Graph degree.
    pairs = edges[["source", "target"]].astype(str)
    a = pairs.min(axis=1)
    b = pairs.max(axis=1)
    unique_pairs = pd.DataFrame({"a": a, "b": b}).drop_duplicates()
    if unique_pairs.empty:
        return None

    deg_counts = pd.concat([unique_pairs["a"], unique_pairs["b"]]).value_counts()
    degree_dict = deg_counts.to_dict()
    degrees = deg_counts.to_numpy(dtype=float)

    # Label nodes and split degrees by cohort.
    newcomer_degrees: List[float] = []
    existing_degrees: List[float] = []
    labels_map: Dict[str, str] = {}
    hub_rows: Dict[str, object] = {}

    for node, deg in degree_dict.items():
        first_seen = first_seen_map.get(str(node), pd.NaT)
        label = newcomer_label_for_month(first_seen, month_dt)
        labels_map[str(node)] = label
        if label == "newcomer":
            newcomer_degrees.append(float(deg))
        else:
            existing_degrees.append(float(deg))

    newcomer_degrees_arr = np.array(newcomer_degrees, dtype=float)
    existing_degrees_arr = np.array(existing_degrees, dtype=float)
    n_newcomers = len(newcomer_degrees_arr)
    n_nodes = len(degrees)

    hub_rows.update(
        {
            "month": month,
            "n_nodes": n_nodes,
            "n_edges": int(len(unique_pairs)),
            "n_newcomers": n_newcomers,
            "newcomer_pop_share": (n_newcomers / n_nodes) if n_nodes > 0 else float("nan"),
        }
    )

    for frac in hub_fractions:
        if frac <= 0 or frac >= 1:
            continue
        pct = int(round(frac * 100))
        q = 1.0 - frac
        threshold = float(np.quantile(degrees, q))
        hubs = [n for n, d in degree_dict.items() if d >= threshold]
        n_hubs = len(hubs)

        if n_hubs == 0:
            newcomer_hub_rate = float("nan")
            newcomer_hub_share = float("nan")
        else:
            newcomer_hub_count = sum(
                1 for n in hubs if labels_map.get(str(n)) == "newcomer"
            )

            newcomer_hub_share = newcomer_hub_count / n_hubs
            newcomer_hub_rate = newcomer_hub_count / n_newcomers if n_newcomers > 0 else float("nan")

        hub_rows[f"hub_threshold_deg_p{pct}"] = threshold
        hub_rows[f"n_hubs_p{pct}"] = n_hubs
        hub_rows[f"newcomer_hub_share_p{pct}"] = newcomer_hub_share
        hub_rows[f"newcomer_hub_rate_p{pct}"] = newcomer_hub_rate

        # Alternative (paper-aligned) definition: newcomer hub rate vs. existing PXX degree.
        if existing_degrees_arr.size > 0 and newcomer_degrees_arr.size > 0:
            existing_threshold = float(np.quantile(existing_degrees_arr, q))
            newcomer_vs_existing_rate = float(
                np.mean(newcomer_degrees_arr > existing_threshold)
            )
        else:
            existing_threshold = float("nan")
            newcomer_vs_existing_rate = float("nan")

        hub_rows[f"existing_threshold_deg_p{pct}"] = existing_threshold
        hub_rows[f"newcomer_hub_rate_vs_existing_p{pct}"] = newcomer_vs_existing_rate

    return hub_rows


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
    hub_fractions = sorted(args.hub_fractions)

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    all_frames: List[pd.DataFrame] = []
    summary_lines: List[str] = []
    summary_lines.append("Package C1: Hub-threshold sensitivity")
    summary_lines.append("=" * 72)
    summary_lines.append(f"Communities: {', '.join(communities)}")
    summary_lines.append(f"Hub fractions tested: {', '.join(str(f) for f in hub_fractions)}")
    summary_lines.append("")

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
                row = compute_month_metrics(edge_file, first_seen_map, hub_fractions)
            except Exception as e:
                logger.warning(f"{community}: failed {edge_file.name}: {e}")
                continue
            if row:
                rows.append(row)

        df = pd.DataFrame(rows)
        df = filter_months(df, args.min_month, args.max_month)
        df = df.sort_values("month").reset_index(drop=True)

        out_path = out_dir / f"c1_hub_threshold_sensitivity_{community}.csv"
        df.to_csv(out_path, index=False)
        all_frames.append(df.assign(community=community))

        summary_lines.append(f"{community}:")
        for frac in hub_fractions:
            pct = int(round(frac * 100))
            share_col = f"newcomer_hub_share_p{pct}"
            rate_col = f"newcomer_hub_rate_p{pct}"
            vs_col = f"newcomer_hub_rate_vs_existing_p{pct}"
            if share_col not in df.columns:
                continue
            max_share = float(pd.to_numeric(df[share_col], errors="coerce").max())
            med_share = float(pd.to_numeric(df[share_col], errors="coerce").median())
            max_rate = float(pd.to_numeric(df[rate_col], errors="coerce").max())
            med_vs = float(pd.to_numeric(df[vs_col], errors="coerce").median()) if vs_col in df.columns else float("nan")
            max_vs = float(pd.to_numeric(df[vs_col], errors="coerce").max()) if vs_col in df.columns else float("nan")
            summary_lines.append(
                f"  top {pct}% hubs: newcomer hub share max={max_share:.3f}, median={med_share:.3f}; "
                f"hub rate max={max_rate:.3f}; rate vs existing median={med_vs:.3f}, max={max_vs:.3f}"
            )
        summary_lines.append("")

    # Global unweighted mean across communities by month
    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        global_df = (
            combined.groupby("month", as_index=False)
            .mean(numeric_only=True)
            .sort_values("month")
        )
        global_path = out_dir / "c1_hub_threshold_sensitivity_global.csv"
        global_df.to_csv(global_path, index=False)

        summary_lines.append("Global (unweighted across communities):")
        for frac in hub_fractions:
            pct = int(round(frac * 100))
            share_col = f"newcomer_hub_share_p{pct}"
            rate_col = f"newcomer_hub_rate_p{pct}"
            vs_col = f"newcomer_hub_rate_vs_existing_p{pct}"
            if share_col not in global_df.columns:
                continue
            max_share = float(pd.to_numeric(global_df[share_col], errors="coerce").max())
            med_share = float(pd.to_numeric(global_df[share_col], errors="coerce").median())
            max_rate = float(pd.to_numeric(global_df[rate_col], errors="coerce").max())
            med_vs = float(pd.to_numeric(global_df[vs_col], errors="coerce").median()) if vs_col in global_df.columns else float("nan")
            max_vs = float(pd.to_numeric(global_df[vs_col], errors="coerce").max()) if vs_col in global_df.columns else float("nan")
            summary_lines.append(
                f"  top {pct}% hubs: newcomer hub share max={max_share:.3f}, median={med_share:.3f}; "
                f"hub rate max={max_rate:.3f}; rate vs existing median={med_vs:.3f}, max={max_vs:.3f}"
            )

    summary_path = out_dir / "c1_hub_threshold_sensitivity_summary.txt"
    summary_path.write_text("\n".join(summary_lines))
    logger.info(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
