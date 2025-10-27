#!/usr/bin/env python3
import os
import sys
import argparse
import logging
import gc
from typing import List, Tuple, Dict, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
import networkx as nx

# Local imports
from core_periphery_sbm.core_periphery import HubSpokeCorePeriphery
from core_periphery_sbm import network_helper as nh


def _bytes_to_human(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024.0:
            return f"{f:.1f} {u}"
        f /= 1024.0
    return f"{f:.1f} PB"


def get_memory_status() -> dict:
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return {
            "total": int(vm.total),
            "available": int(vm.available),
            "used": int(vm.used),
            "percent": float(vm.percent),
            "source": "psutil",
        }
    except Exception:
        pass
    # Try /proc/meminfo
    try:
        meminfo = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    meminfo[key] = int(val) * 1024
        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable", 0)
        used = max(0, total - available)
        percent = (used / total * 100.0) if total > 0 else 0.0
        return {"total": total, "available": available, "used": used, "percent": percent, "source": "/proc/meminfo"}
    except Exception:
        return {"total": 0, "available": 0, "used": 0, "percent": 0.0, "source": "unknown"}


def parse_window_from_filename(path: str) -> Tuple[str, str]:
    """Return (community, window) from a filename like 'community_YYYY-MM.txt'
    or 'community_YYYY-MM_to_YYYY-MM.txt'.
    """
    base = os.path.basename(path)
    stem = os.path.splitext(base)[0]
    if "_to_" in stem:
        # community_YYYY-MM_to_YYYY-MM
        parts = stem.split("_")
        community = parts[0]
        window = "_".join(parts[1:])
    else:
        # community_YYYY-MM
        parts = stem.split("_")
        community = parts[0]
        window = parts[1] if len(parts) > 1 else stem
    return community, window


def read_edges(path: str) -> List[Tuple[str, str]]:
    edges: List[Tuple[str, str]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            u, v = parts[0], parts[1]
            if u == v:
                continue
            # enforce a stable order to avoid duplicates in undirected graph
            if v < u:
                u, v = v, u
            edges.append((u, v))
    # Deduplicate
    if not edges:
        return []
    edges = list(dict.fromkeys(edges))
    return edges


def build_graph_from_edges(edges: List[Tuple[str, str]]) -> nx.Graph:
    G = nx.Graph()
    if edges:
        G.add_edges_from(edges)
    return G


def run_hubspoke(G: nx.Graph, n_gibbs: int, n_mcmc_mult: int, last_n_samples: int, seed: int | None = None) -> Tuple[Dict[str, int], np.ndarray, np.ndarray, np.ndarray]:
    if seed is not None:
        np.random.seed(seed)
    n_mcmc = max(1, n_mcmc_mult * max(1, G.number_of_nodes()))
    model = HubSpokeCorePeriphery(n_gibbs=n_gibbs, n_mcmc=n_mcmc)
    model.infer(G)
    labels = model.get_labels(last_n_samples=last_n_samples, prob=False, return_dict=True)
    ns, ms, Ms = nh.get_block_stats(G, labels, n_blocks=2)
    return labels, ns, ms, Ms


def _total_cpus() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except Exception:
        return os.cpu_count() or 1


def _process_window(
    fpath: str,
    min_nodes: int,
    min_edges: int,
    n_gibbs: int,
    n_mcmc_mult: int,
    last_n_samples: int,
    seed: Optional[int],
) -> Tuple[str, List[Dict[str, object]], Dict[str, object], Dict[str, object]]:
    """Process a single edge-list window; return window id and rows.

    Returns: (window, labels_rows, block_row, summary_row). labels_rows may be
    empty if skipped due to size thresholds.
    """
    community, window = parse_window_from_filename(fpath)
    edges = read_edges(fpath)
    G = build_graph_from_edges(edges)
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()

    if n_nodes < min_nodes or n_edges < min_edges:
        return window, [], {}, {}

    # Derive per-window seed
    wseed = None
    if seed is not None:
        try:
            wseed = (seed ^ (abs(hash(window)) & 0x7FFFFFFF)) & 0x7FFFFFFF
        except Exception:
            wseed = seed

    labels, ns, ms, Ms = run_hubspoke(
        G,
        n_gibbs=n_gibbs,
        n_mcmc_mult=n_mcmc_mult,
        last_n_samples=last_n_samples,
        seed=wseed,
    )

    labels_rows = [
        {"community": community, "window": window, "node_id": node, "label": int(lab)}
        for node, lab in labels.items()
    ]

    def s_int(x):
        try:
            return int(x)
        except Exception:
            return 0

    def s_div(a, b):
        return float(a) / float(b) if b and b != 0 else np.nan

    block_row = {
        "community": community,
        "window": window,
        "n_nodes": int(n_nodes),
        "n_edges": int(n_edges),
        "ns_core": s_int(ns[0]) if np.size(ns) > 0 else 0,
        "ns_peri": s_int(ns[1]) if np.size(ns) > 1 else 0,
        "m_cc": s_int(ms[0, 0]) if np.size(ms) else 0,
        "m_cp": s_int(ms[0, 1]) if np.size(ms) else 0,
        "m_pp": s_int(ms[1, 1]) if np.size(ms) else 0,
        "M_cc": s_int(Ms[0, 0]) if np.size(Ms) else 0,
        "M_cp": s_int(Ms[0, 1]) if np.size(Ms) else 0,
        "M_pp": s_int(Ms[1, 1]) if np.size(Ms) else 0,
    }
    block_row["p_cc"] = s_div(block_row["m_cc"], block_row["M_cc"]) if block_row["M_cc"] else np.nan
    block_row["p_cp"] = s_div(block_row["m_cp"], block_row["M_cp"]) if block_row["M_cp"] else np.nan
    block_row["p_pp"] = s_div(block_row["m_pp"], block_row["M_pp"]) if block_row["M_pp"] else np.nan

    core_size = sum(1 for _, l in labels.items() if int(l) == 0)
    per_size = sum(1 for _, l in labels.items() if int(l) == 1)
    summary_row = {
        "community": community,
        "window": window,
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "core_size": core_size,
        "periphery_size": per_size,
    }

    # Cleanup
    del G, edges, labels, ns, ms, Ms
    gc.collect()
    return window, labels_rows, block_row, summary_row


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Run core–periphery (hub-spoke) on edge-list windows sequentially")
    ap.add_argument("--edges-dir", required=True, help="Directory with window edge lists (*.txt)")
    ap.add_argument("--platform", choices=["reddit", "voat", "compare"], required=True)
    ap.add_argument("--community", required=False, help="Community name; if omitted, derived from filenames")
    ap.add_argument("--output-dir", default="results/core-periphery", help="Base output directory (category root)")
    ap.add_argument("--min-nodes", type=int, default=10, help="Skip windows with fewer nodes")
    ap.add_argument("--min-edges", type=int, default=10, help="Skip windows with fewer edges")
    ap.add_argument("--n-gibbs", type=int, default=100, help="Gibbs iterations")
    ap.add_argument("--n-mcmc-mult", type=int, default=10, help="MCMC steps multiplier × |V|")
    ap.add_argument("--last-n-samples", type=int, default=50, help="Last N samples to aggregate labels")
    ap.add_argument("--seed", type=int, default=None, help="Random seed")
    ap.add_argument("--workers", type=int, default=0, help="Parallel windows to process (0=auto ~50% CPUs)")
    ap.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR"]) 
    args = ap.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.isdir(args.edges_dir):
        logging.error("--edges-dir not found: %s", args.edges_dir)
        return 2

    # Gather edge windows
    files = sorted([os.path.join(args.edges_dir, f) for f in os.listdir(args.edges_dir) if f.endswith(".txt")])
    if not files:
        logging.error("No .txt edge lists found in %s", args.edges_dir)
        return 2

    # Derive community if not provided
    if not args.community:
        first_comm, _ = parse_window_from_filename(files[0])
        community = first_comm
    else:
        community = args.community

    # Prepare outputs per repo guidelines
    plat_dir = os.path.join(args.output_dir, args.platform)
    results_dir = os.path.join(plat_dir, "results")
    figures_dir = os.path.join(plat_dir, "figures")
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)

    prefix = f"{args.platform}_{community}" if args.platform in ("voat","reddit") else f"compare_{community}"

    labels_rows: List[Dict[str, object]] = []
    block_rows: List[Dict[str, object]] = []
    summary_rows: List[Dict[str, object]] = []

    total = len(files)
    mem = get_memory_status()
    logging.info(
        "Starting CP on %d windows; mem %s/%s (%.1f%%)",
        total,
        _bytes_to_human(mem.get("used", 0)),
        _bytes_to_human(mem.get("total", 0)),
        mem.get("percent", 0.0),
    )

    # Select community-matching files (defensive, though edges-dir should be single community)
    file_list = []
    for f in files:
        comm_in_file, _ = parse_window_from_filename(f)
        if community and comm_in_file != community:
            continue
        file_list.append(f)

    if not file_list:
        logging.error("No window files match community=%s", community)
        return 2

    workers = args.workers if args.workers and args.workers > 0 else max(1, _total_cpus() // 2)
    logging.info("Using %d workers (CPUs=%d)", workers, _total_cpus())

    with ProcessPoolExecutor(max_workers=workers) as ex:
        fut_map = {
            ex.submit(
                _process_window,
                f,
                args.min_nodes,
                args.min_edges,
                args.n_gibbs,
                args.n_mcmc_mult,
                args.last_n_samples,
                args.seed,
            ): f
            for f in file_list
        }
        for i, fut in enumerate(as_completed(fut_map), start=1):
            fpath = fut_map[fut]
            try:
                window, lab_rows, blk_row, sum_row = fut.result()
            except Exception as e:
                logging.exception("Worker failed on %s: %s", fpath, e)
                continue
            if lab_rows:
                labels_rows.extend(lab_rows)
            if blk_row:
                block_rows.append(blk_row)
            if sum_row:
                summary_rows.append(sum_row)
            if i % max(1, max(1, len(file_list) // 10)) == 0:
                mem = get_memory_status()
                logging.info(
                    "Progress %d/%d | mem %s/%s (%.1f%%)",
                    i,
                    len(file_list),
                    _bytes_to_human(mem.get("used", 0)),
                    _bytes_to_human(mem.get("total", 0)),
                    mem.get("percent", 0.0),
                )

    # Stability across consecutive windows
    stability_rows: List[Dict[str, object]] = []
    if labels_rows:
        windows_sorted = sorted({r["window"] for r in labels_rows})
        # Build per-window maps
        label_maps = {w: {r["node_id"]: r["label"] for r in labels_rows if r["window"] == w} for w in windows_sorted}
        core_sets = {w: {n for n, l in label_maps[w].items() if int(l) == 0} for w in windows_sorted}
        node_sets = {w: set(label_maps[w].keys()) for w in windows_sorted}
        for w_prev, w_curr in zip(windows_sorted, windows_sorted[1:]):
            c_prev, c_curr = core_sets[w_prev], core_sets[w_curr]
            inter_nodes = node_sets[w_prev] & node_sets[w_curr]
            union_core = len(c_prev | c_curr)
            inter_core = len(c_prev & c_curr)
            jacc = (inter_core / union_core) if union_core > 0 else np.nan
            if inter_nodes:
                prev_map = label_maps[w_prev]
                curr_map = label_maps[w_curr]
                agree = sum(1 for n in inter_nodes if prev_map.get(n) == curr_map.get(n))
                stability_rows.append({
                    "community": community,
                    "window_prev": w_prev,
                    "window_curr": w_curr,
                    "jaccard_core": jacc,
                    "label_agreement_pct": (agree / len(inter_nodes)) * 100.0,
                    "common_nodes": len(inter_nodes),
                })

    # Write outputs
    labels_df = pd.DataFrame.from_records(labels_rows)
    blocks_df = pd.DataFrame.from_records(block_rows)
    summary_df = pd.DataFrame.from_records(summary_rows)
    stability_df = pd.DataFrame.from_records(stability_rows)

    labels_path = os.path.join(results_dir, f"{prefix}_cp_labels.csv")
    blocks_path = os.path.join(results_dir, f"{prefix}_cp_block_stats.csv")
    summary_path = os.path.join(results_dir, f"{prefix}_cp_summary.csv")
    stability_path = os.path.join(results_dir, f"{prefix}_cp_stability.csv")

    if not labels_df.empty:
        labels_df.to_csv(labels_path, index=False)
        logging.info("Wrote %s", labels_path)
    else:
        logging.info("No labels to write (all windows skipped?)")
    if not blocks_df.empty:
        blocks_df.to_csv(blocks_path, index=False)
        logging.info("Wrote %s", blocks_path)
    if not summary_df.empty:
        summary_df.to_csv(summary_path, index=False)
        logging.info("Wrote %s", summary_path)
    if not stability_df.empty:
        stability_df.to_csv(stability_path, index=False)
        logging.info("Wrote %s", stability_path)

    # Optional quick figures: time series of core_size and p_cc/p_cp/p_pp
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if not summary_df.empty:
            s = summary_df.copy()
            # Try to sort by YYYY-MM; keep non-month windows stable
            s["_order"] = s["window"].astype(str)
            s = s.sort_values("_order")
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(range(len(s)), s["core_size"], label="core_size")
            ax.plot(range(len(s)), s["periphery_size"], label="periphery_size")
            ax.set_title(f"{community} — Core/Periphery sizes over windows")
            ax.set_xlabel("window index")
            ax.legend(loc="upper left")
            fig.tight_layout()
            fig.savefig(os.path.join(figures_dir, f"{prefix}_sizes.png"), dpi=150)
            plt.close(fig)

        if not blocks_df.empty:
            b = blocks_df.copy()
            b["_order"] = b["window"].astype(str)
            b = b.sort_values("_order")
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(range(len(b)), b["p_cc"], label="p_cc")
            ax.plot(range(len(b)), b["p_cp"], label="p_cp")
            ax.plot(range(len(b)), b["p_pp"], label="p_pp")
            ax.set_title(f"{community} — Block densities over windows")
            ax.set_xlabel("window index")
            ax.legend(loc="upper left")
            fig.tight_layout()
            fig.savefig(os.path.join(figures_dir, f"{prefix}_densities.png"), dpi=150)
            plt.close(fig)
    except Exception as e:
        logging.warning("Figure generation skipped: %s", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
