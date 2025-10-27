#!/usr/bin/env python3
"""Compute monthly core/periphery toxicity and sentiment metrics for Reddit communities."""

import argparse
import logging
import os
from typing import Tuple

import pandas as pd
import pyarrow.parquet as pq

LABEL_TO_GROUP = {0: "core", 1: "periphery"}

REQUIRED_COLUMNS = [
    "publish_date",
    "user_id",
    "platform",
    "community",
    "interaction_type",
    "sentiment_vader",
    "sentiment_textblob",
    "subjectivity_textblob",
    "toxicity_toxigen",
]


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def _locate_cp_file(base_dir: str, community: str, suffix: str) -> Tuple[str, str]:
    """Return (path, canonical_community) for the requested CP output file."""
    plat = "reddit"
    res_dir = os.path.join(base_dir, plat, "results")
    if not os.path.isdir(res_dir):
        raise FileNotFoundError(f"Missing core-periphery results directory: {res_dir}")
    target = community.lower()
    for name in os.listdir(res_dir):
        if not name.startswith(f"{plat}_") or not name.endswith(suffix):
            continue
        comm_token = name[len(plat) + 1 : -len(suffix)]
        if comm_token.lower() == target:
            return os.path.join(res_dir, name), comm_token
    raise FileNotFoundError(
        f"Unable to locate file ending with '{suffix}' for community '{community}' under {res_dir}"
    )


def _locate_data_file(data_dir: str, community: str) -> Tuple[str, str]:
    plat = "reddit"
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"Missing data directory: {data_dir}")
    target = f"{plat}_{community.lower()}_madoc.parquet"
    for name in os.listdir(data_dir):
        if not name.lower().endswith("_madoc.parquet"):
            continue
        if name.lower() == target:
            return os.path.join(data_dir, name), name[len(plat) + 1 : -len("_madoc.parquet")]
    raise FileNotFoundError(
        f"Unable to locate Parquet file matching '{target}' under {data_dir}"
    )


def _load_cp_labels(cp_dir: str, community: str) -> Tuple[pd.DataFrame, str]:
    path, canon_comm = _locate_cp_file(cp_dir, community, "_cp_labels.csv")
    logging.debug("Reading labels from %s", path)
    labels = pd.read_csv(path, dtype={"label": "int64"})
    labels = labels.rename(columns={"window": "month", "node_id": "user_id"})[
        ["month", "user_id", "label"]
    ].copy()
    labels["month"] = labels["month"].astype(str)
    labels["label"] = labels["label"].astype(int)
    if not set(labels["label"].unique()).issubset(LABEL_TO_GROUP):
        raise ValueError("Unexpected label values in CP labels file")
    labels["group"] = labels["label"].map(LABEL_TO_GROUP)
    return labels, canon_comm


def _load_block_stats(cp_dir: str, community: str) -> pd.DataFrame:
    path, _ = _locate_cp_file(cp_dir, community, "_cp_block_stats.csv")
    logging.debug("Reading block stats from %s", path)
    block = pd.read_csv(path)
    block = block.rename(columns={"window": "month"})
    block["month"] = block["month"].astype(str)
    return block


def _load_interactions(data_dir: str, community: str) -> Tuple[pd.DataFrame, str]:
    path, canon_comm = _locate_data_file(data_dir, community)
    logging.debug("Reading interactions from %s", path)
    table = pq.read_table(path, columns=REQUIRED_COLUMNS)
    df = table.to_pandas()
    df.columns = [c.lower() for c in df.columns]
    df = df[df["interaction_type"].astype(str).str.lower().isin(["post", "comment"])]
    df["platform"] = df["platform"].astype(str).str.lower()
    df["community"] = df["community"].astype(str).str.lower()
    series = pd.to_numeric(df["publish_date"], errors="coerce")
    unit = "ms" if series.dropna().median() > 1e11 else "s"
    dates = pd.to_datetime(series, unit=unit, errors="coerce", utc=True)
    df = df.assign(month=dates.dt.strftime("%Y-%m"))
    df = df[df["month"].notna()].copy()
    return df, canon_comm


def compute_monthly_metrics(labels: pd.DataFrame, interactions: pd.DataFrame) -> pd.DataFrame:
    """Return per-month, per-group metrics (per-user monthly averages)."""
    members = labels.drop_duplicates(subset=["month", "user_id", "group"])
    member_counts = (
        members.groupby(["month", "group"], as_index=False)
        .agg(member_count=("user_id", "nunique"))
        .sort_values(["month", "group"])
    )

    joined = interactions.merge(
        members[["month", "user_id", "group"]],
        on=["month", "user_id"],
        how="inner",
    )

    if joined.empty:
        metrics = member_counts.copy()
        metrics["mean_toxicity_per_user"] = pd.NA
        metrics["mean_sentiment_vader_per_user"] = pd.NA
        metrics["mean_sentiment_textblob_per_user"] = pd.NA
        metrics["mean_subjectivity_textblob_per_user"] = pd.NA
        return metrics

    for col in [
        "toxicity_toxigen",
        "sentiment_vader",
        "sentiment_textblob",
        "subjectivity_textblob",
    ]:
        joined[col] = pd.to_numeric(joined[col], errors="coerce")

    user_month = (
        joined.groupby(["month", "group", "user_id"], as_index=False)
        .agg(
            mean_toxicity=("toxicity_toxigen", "mean"),
            mean_vader=("sentiment_vader", "mean"),
            mean_tb=("sentiment_textblob", "mean"),
            mean_subj=("subjectivity_textblob", "mean"),
        )
    )

    group_metrics = (
        user_month.groupby(["month", "group"], as_index=False)
        .agg(
            mean_toxicity_per_user=("mean_toxicity", "mean"),
            mean_sentiment_vader_per_user=("mean_vader", "mean"),
            mean_sentiment_textblob_per_user=("mean_tb", "mean"),
            mean_subjectivity_textblob_per_user=("mean_subj", "mean"),
        )
    )

    metrics = member_counts.merge(group_metrics, on=["month", "group"], how="left")
    return metrics.sort_values(["month", "group"])


def write_metrics(
    community: str,
    platform: str,
    metrics: pd.DataFrame,
    output_dir: str,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    metrics = metrics.copy()
    metrics.insert(0, "community", community)
    metrics.insert(1, "platform", platform)
    metrics["month_dt"] = pd.to_datetime(metrics["month"] + "-01", errors="coerce")
    metrics = metrics.sort_values(["month_dt", "group"]).drop(columns=["month_dt"])
    fname = f"{platform}_{community}_cp_monthly_group_metrics.csv"
    fpath = os.path.join(output_dir, fname)
    metrics.to_csv(fpath, index=False)
    logging.info("Wrote metrics to %s", fpath)
    return fpath


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--community", required=True, help="Community name (case-insensitive)")
    ap.add_argument(
        "--cp-output-dir",
        default=os.path.join("results", "core-periphery"),
        help="Base directory where core-periphery outputs are stored",
    )
    ap.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing Reddit interaction Parquet files",
    )
    ap.add_argument(
        "--output-dir",
        default=os.path.join("results", "core-periphery", "reddit", "results"),
        help="Directory for the derived metrics CSV",
    )
    ap.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    _setup_logging(args.verbose)

    labels, canon_comm = _load_cp_labels(args.cp_output_dir, args.community)
    block_stats = _load_block_stats(args.cp_output_dir, args.community)
    interactions, canon_data_comm = _load_interactions(args.data_dir, args.community)

    if canon_comm.lower() != canon_data_comm.lower():
        logging.warning(
            "Community name mismatch between CP outputs (%s) and data file (%s)",
            canon_comm,
            canon_data_comm,
        )

    metrics = compute_monthly_metrics(labels, interactions)

    # Append size information from block stats if available (sanity check)
    if not block_stats.empty:
        sizes = block_stats[["month", "ns_core", "ns_peri"]].copy()
        sizes.columns = ["month", "core_size_block", "periphery_size_block"]
        metrics = metrics.merge(sizes, on="month", how="left")

    write_metrics(canon_comm, "reddit", metrics, args.output_dir)


if __name__ == "__main__":
    main()
