#!/usr/bin/env python3
"""Summarize Detoxify/ToxiGen source correlation CSVs for reviewer response."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class SourceSpec:
    filename: str
    source_group_column: str
    source_group_value: str
    scope: str
    stratum: str
    interaction_scope: str


SOURCE_SPECS = [
    SourceSpec(
        filename="voat_detoxify_unbiased_all_posts_correlations_global.csv",
        source_group_column="scope",
        source_group_value="global",
        scope="global",
        stratum="all",
        interaction_scope="all_posts",
    ),
    SourceSpec(
        filename="voat_detoxify_unbiased_all_comments_correlations_global.csv",
        source_group_column="scope",
        source_group_value="global",
        scope="global",
        stratum="all",
        interaction_scope="all_comments",
    ),
    SourceSpec(
        filename="voat_detoxify_unbiased_1k_post_sample_correlations_global.csv",
        source_group_column="scope",
        source_group_value="global",
        scope="global",
        stratum="all",
        interaction_scope="stratified_1k_post_sample",
    ),
    SourceSpec(
        filename="voat_detoxify_unbiased_all_posts_correlations_by_type.csv",
        source_group_column="community_type",
        source_group_value="controversial",
        scope="community_type",
        stratum="controversial",
        interaction_scope="all_posts",
    ),
    SourceSpec(
        filename="voat_detoxify_unbiased_all_posts_correlations_by_type.csv",
        source_group_column="community_type",
        source_group_value="normal",
        scope="community_type",
        stratum="normal",
        interaction_scope="all_posts",
    ),
    SourceSpec(
        filename="voat_detoxify_unbiased_all_comments_correlations_by_type.csv",
        source_group_column="community_type",
        source_group_value="controversial",
        scope="community_type",
        stratum="controversial",
        interaction_scope="all_comments",
    ),
    SourceSpec(
        filename="voat_detoxify_unbiased_all_comments_correlations_by_type.csv",
        source_group_column="community_type",
        source_group_value="normal",
        scope="community_type",
        stratum="normal",
        interaction_scope="all_comments",
    ),
]

SOURCE_REQUIRED_COLUMNS = [
    "toxigen_col",
    "detoxify_col",
    "n",
    "toxigen_mean",
    "detoxify_mean",
    "pearson_r",
    "spearman_rho",
]


def read_source_row(source_dir: Path, spec: SourceSpec) -> dict[str, object]:
    path = source_dir / spec.filename
    if not path.exists():
        raise FileNotFoundError(f"Missing Detoxify/ToxiGen source correlation file: {path}")

    df = pd.read_csv(path)
    missing = [
        col
        for col in SOURCE_REQUIRED_COLUMNS + [spec.source_group_column]
        if col not in df.columns
    ]
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")

    subset = df[
        (df[spec.source_group_column].astype(str) == spec.source_group_value)
        & (df["detoxify_col"] == "detoxify_toxicity")
    ].copy()
    if subset.empty:
        raise ValueError(
            f"{path} has no detoxify_toxicity row for "
            f"{spec.source_group_column}={spec.source_group_value}"
        )

    row = subset.iloc[0]
    return {
        "scope": spec.scope,
        "stratum": spec.stratum,
        "interaction_scope": spec.interaction_scope,
        "n": int(row["n"]),
        "toxigen_mean": float(row["toxigen_mean"]),
        "detoxify_toxicity_mean": float(row["detoxify_mean"]),
        "pearson_correlation": float(row["pearson_r"]),
        "spearman_correlation": float(row["spearman_rho"]),
        "source_file": spec.filename,
        "source_group_column": spec.source_group_column,
        "source_group_value": spec.source_group_value,
        "source_toxigen_col": row["toxigen_col"],
        "source_detoxify_col": row["detoxify_col"],
    }


def summarize_sources(source_dir: Path) -> pd.DataFrame:
    return pd.DataFrame(read_source_row(source_dir, spec) for spec in SOURCE_SPECS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        required=True,
        help="Directory containing Detoxify/ToxiGen correlation source CSVs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output compact reviewer-response summary CSV.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = summarize_sources(args.source_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output, index=False)


if __name__ == "__main__":
    main()
