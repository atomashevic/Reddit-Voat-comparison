#!/usr/bin/env python3
"""Run hybrid reputation for Reddit communities missing outputs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List

import psutil

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
OUTPUT_ROOT = REPO_ROOT / "results" / "reputation"
HYBRID_SCRIPT = REPO_ROOT / "scripts" / "dynamical_reputation" / "dynamical_reputation_hybrid.py"
TMUX_SESSION = "reputation-hybrid"
MEMORY_THRESHOLD_PERCENT = 85.0

# Expected Reddit communities from project scope (lowercase for paths).
COMMUNITIES: List[str] = [
    "cringeanarchy",
    "fatpeoplehate",
    "greatawakening",
    "mensrights",
    "milliondollarextreme",
    "kotakuinaction",
    "funny",
    "gaming",
    "gifs",
    "pics",
    "technology",
    "videos",
]


def ensure_tmux_session(expected: str) -> None:
    """Ensure the script runs inside the requested tmux session."""
    if "TMUX" not in os.environ:
        raise RuntimeError("This script must be executed inside tmux (expected session 'reputation-hybrid').")

    session_name = (
        subprocess.check_output(["tmux", "display-message", "-p", "#S"], text=True)
        .strip()
    )
    if session_name != expected:
        raise RuntimeError(f"Run this script from tmux session '{expected}', not '{session_name}'.")


def current_memory_percent() -> float:
    mem = psutil.virtual_memory()
    return mem.percent


def check_memory_or_abort() -> None:
    usage = current_memory_percent()
    if usage >= MEMORY_THRESHOLD_PERCENT:
        raise SystemExit(
            f"Memory usage {usage:.1f}% >= {MEMORY_THRESHOLD_PERCENT:.1f}% threshold; aborting to keep load safe."
        )


def has_reddit_reputation(community: str) -> bool:
    results_dir = OUTPUT_ROOT / community / "reddit" / "results"
    if not results_dir.exists():
        return False
    return any(results_dir.iterdir())


def find_missing_communities() -> List[str]:
    missing: List[str] = []
    for community in COMMUNITIES:
        if not has_reddit_reputation(community):
            missing.append(community)
    return missing


def build_input_path(community: str) -> Path:
    return DATA_DIR / f"reddit_{community}_madoc.parquet"


def run_hybrid_for(community: str) -> None:
    input_path = build_input_path(community)
    if not input_path.exists():
        raise FileNotFoundError(f"Missing input file for {community}: {input_path}")

    cmd = [
        sys.executable,
        str(HYBRID_SCRIPT),
        "--input",
        str(input_path),
        "--platform",
        "reddit",
        "--community",
        community,
        "--output-dir",
        str(OUTPUT_ROOT),
        "--output-format",
        "parquet",
    ]
    print(f"\n→ Running hybrid reputation for {community}...")
    subprocess.run(cmd, check=True)


def main() -> None:
    ensure_tmux_session(TMUX_SESSION)

    missing = find_missing_communities()
    if not missing:
        print("All Reddit communities already have reputation outputs; nothing to do.")
        return

    print(f"Communities missing Reddit reputation: {', '.join(missing)}")
    check_memory_or_abort()

    for community in missing:
        check_memory_or_abort()
        run_hybrid_for(community)

    print("\nAll missing Reddit reputation runs completed.")


if __name__ == "__main__":
    main()
