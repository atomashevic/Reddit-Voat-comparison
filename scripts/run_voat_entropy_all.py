#!/usr/bin/env python3
"""Run Voat convergence-entropy analysis for all available communities."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List


def discover_communities(cp_results_dir: Path) -> List[str]:
    communities = set()
    for summary_path in cp_results_dir.glob("voat_*_cp_summary.csv"):
        stem = summary_path.stem
        # stem looks like 'voat_<community>_cp_summary'
        inner = stem[len("voat_") : -len("_cp_summary")]
        if inner:
            communities.add(inner.lower())
    return sorted(communities)


def build_command(
    community: str,
    data_path: Path,
    cp_labels: Path,
    cp_summary: Path,
    cp_stability: Path,
    outdir: Path,
    pairs_csv: Path,
    sample_fraction: float,
    min_thread_size: int,
    max_thread_size: int | None,
    seed: int,
    sigma: float,
) -> List[str]:
    cmd = [
        sys.executable,
        "scripts/voat_entropy_timeseries.py",
        "--community",
        community,
        "--parquet",
        str(data_path),
        "--cp-labels",
        str(cp_labels),
        "--outdir",
        str(outdir),
        "--sample-fraction",
        str(sample_fraction),
        "--min-thread-size",
        str(min_thread_size),
        "--seed",
        str(seed),
        "--cp-summary",
        str(cp_summary),
        "--cp-stability",
        str(cp_stability),
        "--sigma",
        str(sigma),
    ]
    if max_thread_size is not None and max_thread_size > 0:
        cmd.extend(["--max-thread-size", str(max_thread_size)])
    if pairs_csv.exists():
        cmd.extend(["--pairs-csv", str(pairs_csv)])
    else:
        cmd.append("--save-pairs")
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cp-results", type=Path, default=Path("results/core-periphery/voat/results"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out-base", type=Path, default=Path("results/entropy/voat"))
    parser.add_argument("--sample-fraction", type=float, default=0.25)
    parser.add_argument("--min-thread-size", type=int, default=5)
    parser.add_argument("--max-thread-size", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sigma", type=float, default=0.3)
    parser.add_argument("--communities", nargs="*", default=None, help="Optional subset of communities")
    args = parser.parse_args()

    cp_results_dir = args.cp_results
    communities: Iterable[str]
    if args.communities:
        communities = [c.lower() for c in args.communities]
    else:
        communities = discover_communities(cp_results_dir)

    sample_fraction = args.sample_fraction
    min_thread_size = args.min_thread_size
    max_thread_size = args.max_thread_size if args.max_thread_size > 0 else None
    seed = args.seed
    sigma = args.sigma

    for community in communities:
        data_path = args.data_dir / f"voat_{community}_madoc.parquet"
        cp_labels = cp_results_dir / f"voat_{community}_cp_labels.csv"
        cp_summary = cp_results_dir / f"voat_{community}_cp_summary.csv"
        cp_stability = cp_results_dir / f"voat_{community}_cp_stability.csv"
        if not data_path.exists():
            print(f"[skip] data not found for /{community}: {data_path}")
            continue
        if not cp_labels.exists() or not cp_summary.exists() or not cp_stability.exists():
            print(f"[skip] missing CP files for /{community}")
            continue

        outdir = args.out_base / community
        out_results = outdir / "results"
        out_results.mkdir(parents=True, exist_ok=True)
        pairs_csv = out_results / f"voat_{community}_timeseries_pairs.csv"

        cmd = build_command(
            community=community,
            data_path=data_path,
            cp_labels=cp_labels,
            cp_summary=cp_summary,
            cp_stability=cp_stability,
            outdir=outdir,
            pairs_csv=pairs_csv,
            sample_fraction=sample_fraction,
            min_thread_size=min_thread_size,
            max_thread_size=max_thread_size,
            seed=seed,
            sigma=sigma,
        )

        print("=" * 80)
        print(f"Running entropy analysis for /{community}")
        print("Command:", " ".join(cmd))
        print("=" * 80, flush=True)

        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"[warn] /{community} run exited with code {result.returncode}")
        else:
            print(f"[done] /{community} completed successfully")


if __name__ == "__main__":
    main()
