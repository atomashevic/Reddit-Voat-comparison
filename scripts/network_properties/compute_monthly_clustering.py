#!/usr/bin/env python3
"""Compute monthly clustering coefficients for Reddit and Voat networks.

For each monthly network snapshot (stored as whitespace-separated edge lists),
this script computes:
    - node clustering coefficients (c_i) via NetworkX
    - mean clustering coefficient C = average c_i over all nodes
    - expected clustering for an Erdős–Rényi network with identical N, L
    - normalized clustering = C / c_er

Results are written to ``results/networks/<platform>/results`` as CSV files,
one per community, named ``<platform>_<community>_clustering.csv``.
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List

import networkx as nx
import pandas as pd

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def list_communities(base: Path) -> Dict[str, Path]:
    """Return mapping of community key -> monthly directory path."""
    mapping: Dict[str, Path] = {}
    for child in base.iterdir():
        if child.is_dir() and child.name.endswith("_monthly"):
            community = child.name[: -len("_monthly")]
            mapping[community.lower()] = child
    return mapping


def parse_month_from_filename(path: Path) -> str:
    match = re.search(r"(19|20)\d{2}-\d{2}$", path.stem)
    if not match:
        raise ValueError(f"Unable to parse month from filename: {path}")
    return match.group(0)


def read_edges(path: Path) -> pd.DataFrame:
    if path.stat().st_size == 0:
        return pd.DataFrame(columns=["source", "target"])
    df = pd.read_csv(
        path,
        sep=r"\s+",
        header=None,
        names=["source", "target"],
        comment="#",
        dtype=str,
        engine="python",
    )
    df = df.dropna(subset=["source", "target"])
    return df


def compute_snapshot_metrics(df: pd.DataFrame) -> Dict[str, float]:
    g = nx.Graph()
    if not df.empty:
        edges = list(zip(df["source"].astype(str), df["target"].astype(str)))
        g.add_edges_from(edges)
    n_nodes = g.number_of_nodes()
    n_edges = g.number_of_edges()

    if n_nodes == 0:
        return {
            "n_nodes": 0,
            "n_edges": 0,
            "mean_clustering": float("nan"),
            "er_expected_clustering": float("nan"),
            "normalized_clustering": float("nan"),
        }

    node_clustering = nx.clustering(g)
    mean_clustering = float(sum(node_clustering.values()) / len(node_clustering)) if node_clustering else 0.0

    er_expected = 0.0
    if n_nodes > 1:
        # Expected clustering for G(n, p) with p = 2L / (N(N-1)).
        er_expected = (2.0 * n_edges) / (n_nodes * (n_nodes - 1))
    normalized = float("nan")
    if er_expected > 0:
        normalized = mean_clustering / er_expected

    return {
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "mean_clustering": mean_clustering,
        "er_expected_clustering": er_expected,
        "normalized_clustering": normalized,
    }


def process_community(platform: str, name: str, directory: Path, output_dir: Path) -> None:
    rows: List[Dict[str, object]] = []
    for edge_file in sorted(directory.glob("*.txt")):
        if edge_file.name.endswith(".log"):
            continue
        try:
            month = parse_month_from_filename(edge_file)
        except ValueError:
            logger.debug("Skipping non-month file: %s", edge_file)
            continue
        df = read_edges(edge_file)
        metrics = compute_snapshot_metrics(df)
        rows.append(
            {
                "platform": platform,
                "community": name,
                "month": month,
                **metrics,
            }
        )

    if not rows:
        logger.info("No monthly data for %s/%s", platform, name)
        return

    out_path = output_dir / f"{platform}_{name}_clustering.csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).sort_values("month").to_csv(out_path, index=False)
    logger.info("Wrote %s", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute normalized monthly clustering coefficients.")
    parser.add_argument("--networks-dir", type=Path, default=Path("results/networks"), help="Network base directory.")
    parser.add_argument(
        "--platforms",
        nargs="*",
        default=["reddit", "voat"],
        choices=["reddit", "voat"],
        help="Platforms to process (default: both).",
    )
    parser.add_argument(
        "--communities",
        nargs="*",
        help="Case-insensitive community names to include (default: all).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    configure_logging(args.verbose)

    requested = {c.lower() for c in (args.communities or [])}

    for platform in args.platforms:
        base = args.networks_dir / platform
        if not base.exists():
            logger.warning("Platform directory missing: %s", base)
            continue
        community_map = list_communities(base)
        if not community_map:
            logger.warning("No community directories found under %s", base)
            continue

        output_dir = base / "results"
        for key, directory in sorted(community_map.items()):
            if requested and key not in requested:
                continue
            community_name = directory.name[: -len("_monthly")]
            process_community(platform, community_name, directory, output_dir)


if __name__ == "__main__":
    main()
