#!/usr/bin/env python3
"""Summarize monthly core-periphery reputation differences.

This utility reads the monthly reputation aggregates produced by
`mean_monthly_reputation_cp.py` and reports descriptive statistics for the
core minus periphery mean reputation (`core_mean_rep_active` -
`periphery_mean_rep_active`).

Example:

    pyenv activate python13
    python scripts/dynamical_reputation/summarize_cp_reputation_diff.py \
        --platform voat \
        --communities pics gifs videos funny gaming

Outputs a formatted block of statistics for each community, including
quartiles, IQR, coefficient of variation, geometric mean (if all differences
are positive), and several supplementary metrics.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


def _load_monthly_df(base_dir: Path, platform: str, community: str) -> pd.DataFrame:
    """Load the monthly reputation CSV for a given platform/community."""

    plat = platform.lower()
    comm = community.lower()
    csv_path = base_dir / plat / "results" / f"{plat}_{comm}_cp_monthly_reputation.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"Missing monthly reputation file: {csv_path}")
    return pd.read_csv(csv_path)


def _get_core_peri_series(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (core_mean_rep, periphery_mean_rep) columns, preferring *_active variants."""

    if {
        "core_mean_rep_active",
        "periphery_mean_rep_active",
    }.issubset(df.columns):
        return df["core_mean_rep_active"], df["periphery_mean_rep_active"]

    if {"core_mean_rep", "periphery_mean_rep"}.issubset(df.columns):
        return df["core_mean_rep"], df["periphery_mean_rep"]

    raise ValueError(
        "Monthly reputation file missing expected columns: "
        "need either *_mean_rep_active or *_mean_rep"
    )


def _geometric_mean(values: pd.Series) -> float | float("nan"):
    """Return the geometric mean, or NaN if values are non-positive."""

    clean = values.dropna()
    if clean.empty:
        return float("nan")

    if (clean <= 0).any():
        return float("nan")

    return float(np.exp(np.log(clean).mean()))


def describe_difference(series: pd.Series) -> pd.Series:
    """Compute descriptive statistics for the provided Series."""

    clean = series.dropna()
    if clean.empty:
        return pd.Series(dtype=float)

    q1, q2, q3 = clean.quantile([0.25, 0.5, 0.75])
    mean = clean.mean()
    std = clean.std(ddof=1)
    cv = float("nan")
    if not math.isclose(mean, 0.0, abs_tol=1e-12):
        cv = std / mean

    stats = {
        "count": float(clean.count()),
        "mean": mean,
        "std": std,
        "coef_variation": cv,
        "min": clean.min(),
        "q1": q1,
        "median": q2,
        "q3": q3,
        "iqr": q3 - q1,
        "max": clean.max(),
        "range": clean.max() - clean.min(),
        "geometric_mean": _geometric_mean(clean),
        "skew": clean.skew(),
        "kurtosis": clean.kurtosis(),
        "positive_share": (clean > 0).mean(),
        "negative_share": (clean < 0).mean(),
    }

    return pd.Series(stats)


def format_stats(stats: pd.Series) -> str:
    """Format the statistics for pretty printing."""

    lines: list[str] = []
    for key, value in stats.items():
        if pd.isna(value):
            disp = "nan"
        elif key in {"count"}:
            disp = f"{value:.0f}"
        elif key in {"positive_share", "negative_share"}:
            disp = f"{value * 100:.1f}%"
        else:
            disp = f"{value:.4f}"
        lines.append(f"  {key:>16}: {disp}")
    return "\n".join(lines)


def process_communities(base_dir: Path, platform: str, communities: Iterable[str]) -> None:
    for community in communities:
        df = _load_monthly_df(base_dir, platform, community)
        core, periphery = _get_core_peri_series(df)
        diff = core - periphery
        stats = describe_difference(diff)
        if stats.empty:
            print(f"\n{community}: no data available")
            continue
        header = f"{community} (months={int(stats['count'])})"
        print("\n" + header)
        print("-" * len(header))
        print(format_stats(stats))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize monthly core-periphery reputation differences."
    )
    parser.add_argument(
        "--platform",
        default="voat",
        help="Platform key (default: voat)",
    )
    parser.add_argument(
        "--base-dir",
        default=Path("results") / "reputation",
        type=Path,
        help="Base directory containing reputation results (default: results/reputation)",
    )
    parser.add_argument(
        "--communities",
        nargs="+",
        required=True,
        help="List of communities to summarize",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    process_communities(args.base_dir, args.platform, args.communities)


if __name__ == "__main__":
    main()
