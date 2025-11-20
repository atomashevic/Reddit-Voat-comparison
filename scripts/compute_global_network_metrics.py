#!/usr/bin/env python3
"""Compute global network metrics for monthly snapshots.

For each monthly network snapshot (stored as whitespace-separated edge lists),
this script computes comprehensive structural metrics:
    - Degree distribution statistics (mean, median, std, heterogeneity)
    - Global clustering coefficient
    - Path length metrics (average shortest path, diameter)
    - Density
    - Degree assortativity
    - Giant component statistics

Results are written to ``results/networks/<platform>/results`` as CSV files.
"""

import argparse
import logging
import os
import re
from pathlib import Path
from typing import Dict, List

import networkx as nx
import pandas as pd

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

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
    """Extract YYYY-MM from filename."""
    match = re.search(r"(19|20)\d{2}-\d{2}$", path.stem)
    if not match:
        raise ValueError(f"Unable to parse month from filename: {path}")
    return match.group(0)


def read_edges(path: Path) -> pd.DataFrame:
    """Read edge list from whitespace-separated file."""
    if path.stat().st_size == 0:
        return pd.DataFrame(columns=["source", "target"])
    df = pd.read_csv(
        path, sep=r"\s+", header=None, names=["source", "target"],
        comment="#", dtype=str, engine="python",
    )
    return df.dropna(subset=["source", "target"])


def compute_degree_metrics(g: nx.Graph) -> Dict[str, float]:
    """Compute degree distribution statistics."""
    if g.number_of_nodes() == 0:
        return {"mean_degree": float("nan"), "median_degree": float("nan"),
                "std_degree": float("nan"), "degree_heterogeneity": float("nan")}

    degrees = [d for n, d in g.degree()]
    mean_deg = sum(degrees) / len(degrees) if degrees else 0.0
    sorted_deg = sorted(degrees)
    n = len(sorted_deg)
    median_deg = sorted_deg[n // 2] if n % 2 == 1 else (sorted_deg[n // 2 - 1] + sorted_deg[n // 2]) / 2.0

    if len(degrees) > 1:
        variance = sum((d - mean_deg) ** 2 for d in degrees) / (len(degrees) - 1)
        std_deg = variance**0.5
    else:
        std_deg = 0.0

    cv = std_deg / mean_deg if mean_deg > 0 else float("nan")

    return {"mean_degree": mean_deg, "median_degree": median_deg,
            "std_degree": std_deg, "degree_heterogeneity": cv}


def compute_clustering_metrics(g: nx.Graph) -> Dict[str, float]:
    """Compute clustering coefficient."""
    n_nodes = g.number_of_nodes()
    n_edges = g.number_of_edges()

    if n_nodes == 0:
        return {"mean_clustering": float("nan"), "er_expected_clustering": float("nan"),
                "normalized_clustering": float("nan")}

    node_clustering = nx.clustering(g)
    mean_clustering = float(sum(node_clustering.values()) / len(node_clustering)) if node_clustering else 0.0

    er_expected = 0.0
    if n_nodes > 1:
        er_expected = (2.0 * n_edges) / (n_nodes * (n_nodes - 1))

    normalized = mean_clustering / er_expected if er_expected > 0 else float("nan")

    return {"mean_clustering": mean_clustering, "er_expected_clustering": er_expected,
            "normalized_clustering": normalized}


def compute_path_metrics(g: nx.Graph) -> Dict[str, float]:
    """Compute path length metrics on giant component."""
    if g.number_of_nodes() == 0:
        return {"avg_shortest_path": float("nan"), "diameter": float("nan"),
                "giant_component_size": 0, "giant_component_fraction": 0.0}

    components = list(nx.connected_components(g))
    if not components:
        return {"avg_shortest_path": float("nan"), "diameter": float("nan"),
                "giant_component_size": 0, "giant_component_fraction": 0.0}

    giant = max(components, key=len)
    giant_size = len(giant)
    giant_frac = giant_size / g.number_of_nodes()

    # Optimization: Skip expensive path metrics for large graphs
    # Calculating average shortest path is O(V * (V + E)), which is intractable for V > ~5-10k in Python
    if giant_size > 5000:
        logger.info(f"Skipping path metrics for large component (size={giant_size} > 5000)")
        return {
            "avg_shortest_path": float("nan"),
            "diameter": float("nan"),
            "giant_component_size": giant_size,
            "giant_component_fraction": giant_frac,
        }

    gcc = g.subgraph(giant).copy()

    if gcc.number_of_edges() == 0 or giant_size == 1:
        return {"avg_shortest_path": float("nan"), "diameter": float("nan"),
                "giant_component_size": giant_size, "giant_component_fraction": giant_frac}

    try:
        avg_path = nx.average_shortest_path_length(gcc)
    except (nx.NetworkXError, ZeroDivisionError):
        avg_path = float("nan")

    try:
        diameter = nx.diameter(gcc)
    except (nx.NetworkXError, ValueError):
        diameter = float("nan")

    return {"avg_shortest_path": avg_path, "diameter": float(diameter),
            "giant_component_size": giant_size, "giant_component_fraction": giant_frac}


def compute_global_metrics(g: nx.Graph) -> Dict[str, float]:
    """Compute density and assortativity."""
    n_nodes = g.number_of_nodes()
    n_edges = g.number_of_edges()

    if n_nodes == 0:
        return {"density": float("nan"), "degree_assortativity": float("nan")}

    density = (2.0 * n_edges) / (n_nodes * (n_nodes - 1)) if n_nodes > 1 else 0.0

    assortativity = float("nan")
    if n_edges > 0:
        try:
            assortativity = nx.degree_assortativity_coefficient(g)
        except (nx.NetworkXError, ValueError, ZeroDivisionError):
            pass

    return {"density": density, "degree_assortativity": assortativity}


def compute_snapshot_metrics(df: pd.DataFrame) -> Dict[str, float]:
    """Compute all global network metrics for a single snapshot."""
    g = nx.Graph()
    if not df.empty:
        edges = list(zip(df["source"].astype(str), df["target"].astype(str)))
        g.add_edges_from(edges)

    metrics = {"n_nodes": g.number_of_nodes(), "n_edges": g.number_of_edges()}

    if g.number_of_nodes() == 0:
        metrics.update({"mean_degree": float("nan"), "median_degree": float("nan"),
                        "std_degree": float("nan"), "degree_heterogeneity": float("nan"),
                        "mean_clustering": float("nan"), "er_expected_clustering": float("nan"),
                        "normalized_clustering": float("nan"), "avg_shortest_path": float("nan"),
                        "diameter": float("nan"), "giant_component_size": 0,
                        "giant_component_fraction": 0.0, "density": float("nan"),
                        "degree_assortativity": float("nan")})
        return metrics

    metrics.update(compute_degree_metrics(g))
    metrics.update(compute_clustering_metrics(g))
    metrics.update(compute_path_metrics(g))
    metrics.update(compute_global_metrics(g))

    return metrics


def process_community(platform: str, name: str, directory: Path, output_dir: Path) -> None:
    """Process all monthly snapshots for a community."""
    rows: List[Dict[str, object]] = []
    edge_files = sorted(directory.glob("*.txt"))
    logger.info(f"Processing {len(edge_files)} snapshots for {platform}/{name}")

    for i, edge_file in enumerate(edge_files, 1):
        if edge_file.name.endswith(".log"):
            continue

        try:
            month = parse_month_from_filename(edge_file)
        except ValueError:
            logger.debug(f"Skipping non-month file: {edge_file}")
            continue

        logger.debug(f"  [{i}/{len(edge_files)}] {month}")

        df = read_edges(edge_file)
        metrics = compute_snapshot_metrics(df)

        rows.append({"platform": platform, "community": name, "month": month, **metrics})

    if not rows:
        logger.info(f"No monthly data for {platform}/{name}")
        return

    out_path = output_dir / f"{platform}_{name}_global_metrics.csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    result_df = pd.DataFrame(rows).sort_values("month")
    result_df.to_csv(out_path, index=False)

    logger.info(f"Wrote {out_path} ({len(result_df)} snapshots)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute comprehensive global network metrics.")
    parser.add_argument("--networks-dir", type=Path, default=Path("results/networks"))
    parser.add_argument("--platforms", nargs="*", default=["reddit", "voat"], choices=["reddit", "voat"])
    parser.add_argument("--communities", nargs="*", help="Communities to include (default: all).")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    configure_logging(args.verbose)

    requested = {c.lower() for c in (args.communities or [])}

    for platform in args.platforms:
        base = args.networks_dir / platform
        if not base.exists():
            logger.warning(f"Platform directory missing: {base}")
            continue

        community_map = list_communities(base)
        if not community_map:
            logger.warning(f"No community directories found under {base}")
            continue

        output_dir = base / "results"
        for key, directory in sorted(community_map.items()):
            if requested and key not in requested:
                continue
            community_name = directory.name[: -len("_monthly")]
            process_community(platform, community_name, directory, output_dir)


if __name__ == "__main__":
    main()
