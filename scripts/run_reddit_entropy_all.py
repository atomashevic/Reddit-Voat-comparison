#!/usr/bin/env python3
"""Run Reddit convergence-entropy analysis for all available communities."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass
class CommunityInfo:
    label: str
    slug: str


def discover_communities(cp_results_dir: Path) -> List[CommunityInfo]:
    found: dict[str, CommunityInfo] = {}
    for summary_path in cp_results_dir.glob("reddit_*_cp_summary.csv"):
        stem = summary_path.stem
        inner = stem[len("reddit_") : -len("_cp_summary")]
        if not inner:
            continue
        slug = inner.lower()
        if slug not in found:
            found[slug] = CommunityInfo(label=inner, slug=slug)
    return sorted(found.values(), key=lambda item: item.slug)


def build_command(
    community: CommunityInfo,
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
        "scripts/reddit_entropy_timeseries.py",
        "--community",
        community.label,
        "--parquet",
        str(data_path),
        "--cp-labels",
        str(cp_labels),
        "--cp-summary",
        str(cp_summary),
        "--cp-stability",
        str(cp_stability),
        "--outdir",
        str(outdir),
        "--sample-fraction",
        str(sample_fraction),
        "--min-thread-size",
        str(min_thread_size),
        "--seed",
        str(seed),
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
    parser.add_argument(
        "--cp-results",
        type=Path,
        default=Path("results/core-periphery/reddit/results"),
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out-base", type=Path, default=Path("results/entropy/reddit"))
    parser.add_argument("--sample-fraction", type=float, default=0.25)
    parser.add_argument("--min-thread-size", type=int, default=5)
    parser.add_argument("--max-thread-size", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sigma", type=float, default=0.3)
    parser.add_argument(
        "--communities",
        nargs="*",
        default=None,
        help="Optional subset of communities (case-insensitive)",
    )
    args = parser.parse_args()

    cp_results_dir = args.cp_results
    available = discover_communities(cp_results_dir)
    lookup = {info.slug: info for info in available}

    communities: Iterable[CommunityInfo]
    if args.communities:
        selected: List[CommunityInfo] = []
        for name in args.communities:
            slug = name.lower()
            info = lookup.get(slug)
            if info is None:
                print(f"[warn] /{name} not found in CP results; skipping")
                continue
            selected.append(info)
        communities = selected
    else:
        communities = available

    sample_fraction = args.sample_fraction
    min_thread_size = args.min_thread_size
    max_thread_size = args.max_thread_size if args.max_thread_size > 0 else None
    seed = args.seed
    sigma = args.sigma

    for community in communities:
        data_path = args.data_dir / f"reddit_{community.slug}_madoc.parquet"
        cp_labels = cp_results_dir / f"reddit_{community.label}_cp_labels.csv"
        cp_summary = cp_results_dir / f"reddit_{community.label}_cp_summary.csv"
        cp_stability = cp_results_dir / f"reddit_{community.label}_cp_stability.csv"
        if not data_path.exists():
            print(f"[skip] data not found for /{community.label}: {data_path}")
            continue
        if not cp_labels.exists() or not cp_summary.exists() or not cp_stability.exists():
            print(f"[skip] missing CP files for /{community.label}")
            continue

        outdir = args.out_base / community.slug
        out_results = outdir / "results"
        out_results.mkdir(parents=True, exist_ok=True)
        pairs_csv = out_results / f"reddit_{community.slug}_timeseries_pairs.csv"

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
        print(f"Running entropy analysis for /{community.label}")
        print("Command:", " ".join(cmd))
        print("=" * 80, flush=True)

        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"[warn] /{community.label} run exited with code {result.returncode}")
        else:
            print(f"[done] /{community.label} completed successfully")


if __name__ == "__main__":
    main()
