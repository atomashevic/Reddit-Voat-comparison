#!/usr/bin/env python3
r"""Create Reddit/Voat core–periphery structural comparison panels.

For each community present in the core-periphery results folders, this script
produces a two-row figure of derived core metrics:
    - mean core edges per member (`m_cc / ns_core`)
    - internal edge share (`m_cc / (m_cc + m_cp)`)
    - core retention (`|core_t ∩ core_{t+1}| / |core_t|`)
    - normalized clustering (observed clustering / ER expectation)

Reddit panels are on the left column, Voat on the right column.
Figures land in ``results/core-periphery/compare/figures/<community>_core_metrics.png``.
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


METRICS_ORDER: List[tuple[str, str]] = [
    ("mean_core_edges", "mean core edges"),
    ("internal_edge_share", "internal edge share"),
    ("retention_rate", "retention rate"),
    ("normalized_clustering", "normalized clustering"),
]

DEFAULT_LIMITS: Dict[str, tuple[float, float]] = {
    "mean_core_edges": (0.0, 20.0),
    "internal_edge_share": (0.0, 1.0),
    "retention_rate": (0.0, 1.0),
    "normalized_clustering": (0.0, 5.0),
}


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#333333",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "axes.grid": False,
            "legend.frameon": False,
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "lines.linewidth": 1.6,
        }
    )


def discover_communities(cp_dir: Path, platform: str) -> Dict[str, str]:
    """Return mapping from canonical community key -> filename stem."""
    base = cp_dir / platform / "results"
    if not base.exists():
        logger.warning("Platform directory not found: %s", base)
        return {}
    prefix = f"{platform}_"
    suffix = "_cp_block_stats.csv"
    mapping: Dict[str, str] = {}
    for path in base.glob(f"{prefix}*{suffix}"):
        stem = path.name[len(prefix) : -len(suffix)]
        key = stem.lower()
        mapping[key] = stem
    return mapping


def filter_keys(all_keys: Iterable[str], requested: Optional[Iterable[str]]) -> List[str]:
    if not requested:
        return sorted(set(all_keys))
    requested_lower = {c.lower() for c in requested}
    return sorted({k for k in all_keys if k in requested_lower})


def load_block_stats(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["month"] = pd.to_datetime(df["window"] + "-01", errors="coerce")
    df["ns_core"] = pd.to_numeric(df.get("ns_core"), errors="coerce")
    df["m_cc"] = pd.to_numeric(df.get("m_cc"), errors="coerce")
    df["m_cp"] = pd.to_numeric(df.get("m_cp"), errors="coerce")
    df["p_cc"] = pd.to_numeric(df.get("p_cc"), errors="coerce")
    df["n_nodes"] = pd.to_numeric(df.get("n_nodes"), errors="coerce")
    df["n_edges"] = pd.to_numeric(df.get("n_edges"), errors="coerce")
    # Derived metrics
    df["mean_core_edges"] = df["m_cc"] / df["ns_core"].replace(0, np.nan)
    df["internal_edge_share"] = df["m_cc"] / (df["m_cc"] + df["m_cp"])

    df = df.sort_values("month")
    return df[["month", "mean_core_edges", "internal_edge_share"]]


def load_summary(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["window"] = df["window"].astype(str)
    df["month"] = pd.to_datetime(df["window"] + "-01", errors="coerce")
    df["core_size"] = pd.to_numeric(df.get("core_size"), errors="coerce")
    df["n_nodes"] = pd.to_numeric(df.get("n_nodes"), errors="coerce")
    return df[["window", "month", "core_size", "n_nodes"]]


def load_clustering_metrics(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["month"] = pd.to_datetime(df["month"].astype(str) + "-01", errors="coerce")
    df["normalized_clustering"] = pd.to_numeric(df.get("normalized_clustering"), errors="coerce")
    return df[["month", "normalized_clustering"]]


def load_stability_metrics(path: Path, summary_df: pd.DataFrame) -> pd.DataFrame:
    if not path.exists() or summary_df.empty:
        return pd.DataFrame()

    df = pd.read_csv(path)
    if df.empty:
        return df

    df["window_prev"] = df["window_prev"].astype(str)
    df["window_curr"] = df["window_curr"].astype(str)
    df["month"] = pd.to_datetime(df["window_curr"] + "-01", errors="coerce")
    df["jaccard_core"] = pd.to_numeric(df.get("jaccard_core"), errors="coerce")
    df["common_nodes"] = pd.to_numeric(df.get("common_nodes"), errors="coerce")

    summary = summary_df

    prev_summary = summary.rename(
        columns={"window": "window_prev", "core_size": "core_size_prev", "n_nodes": "n_nodes_prev"}
    )
    curr_summary = summary.rename(
        columns={"window": "window_curr", "core_size": "core_size_curr", "n_nodes": "n_nodes_curr"}
    )

    df = df.merge(prev_summary, on="window_prev", how="left")
    df = df.merge(curr_summary, on="window_curr", how="left")

    df = df.sort_values("month")

    prev_core = df["core_size_prev"].replace(0, np.nan)
    curr_core = df["core_size_curr"].replace(0, np.nan)
    intersection = df["common_nodes"]

    retention = intersection / prev_core
    df["retention_rate"] = retention

    return df[["month", "retention_rate"]]


def load_key_events(notes_path: Path) -> List[Dict[str, object]]:
    """Load A/B/C events (fatpeoplehate, pizzagate, GreatAwakening) from notes."""
    if not notes_path.exists():
        logger.warning("Notes file not found for events: %s", notes_path)
        return []

    try:
        text = notes_path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Unable to read notes file %s: %s", notes_path, exc)
        return []

    targets = [
        ("A", "/r/fatpeoplehate"),
        ("B", "/r/pizzagate"),
        ("C", "/r/GreatAwakening"),
    ]

    sep = r"[-‑‒–-−]"
    date_line = re.compile(rf"^\s*[-*]?\s*(\d{{4}}){sep}(\d{{2}})(?:{sep}(\d{{2}}))?:.*$", re.MULTILINE)
    events: List[Dict[str, object]] = []

    for label, marker in targets:
        match_found = False
        for match in date_line.finditer(text):
            line = match.group(0)
            if marker not in line:
                continue
            year, month, day = match.groups()
            day = day or "01"
            ts = pd.to_datetime(f"{year}-{month}-{day}", errors="coerce")
            if pd.isna(ts):
                continue
            events.append({"label": label, "month_dt": ts, "desc": line.strip()})
            match_found = True
            break
        if not match_found:
            logger.debug("Event marker not found for %s", marker)

    events.sort(key=lambda item: item.get("month_dt", pd.Timestamp.max))
    return events


def compute_limits(series_list: List[pd.Series], default: tuple[float, float]) -> tuple[float, float]:
    """Compute shared y-axis limits with padding."""
    if not series_list:
        return default
    combined = pd.concat(series_list, ignore_index=True).dropna()
    if combined.empty:
        return default
    min_val = float(combined.min())
    max_val = float(combined.max())
    if min_val == max_val:
        if min_val == 0.0:
            return 0.0, 1.0
        delta = abs(min_val) * 0.1
        return min_val - delta, max_val + delta
    padding = (max_val - min_val) * 0.05
    return min_val - padding, max_val + padding


def combine_metrics(*dfs: pd.DataFrame) -> pd.DataFrame:
    valid = [df for df in dfs if not df.empty]
    if not valid:
        return pd.DataFrame()
    merged = valid[0].copy()
    for df in valid[1:]:
        merged = pd.merge(merged, df, on="month", how="outer")
    return merged.sort_values("month")


def add_event_markers(ax: plt.Axes, events: List[Dict[str, object]]) -> None:
    if not events:
        return
    for event in events:
        month = event.get("month_dt")
        label = str(event.get("label", ""))
        if not isinstance(month, pd.Timestamp) or pd.isna(month):
            continue
        ax.axvline(month, color="#555555", linestyle="--", linewidth=1.0, alpha=0.6)
        ax.text(
            month,
            0.98,
            label,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=9,
            fontweight="bold",
            color="#555555",
            backgroundcolor="white",
        )


def build_plot(
    community_label: str,
    reddit_metrics: pd.DataFrame,
    voat_metrics: pd.DataFrame,
    output_path: Path,
    dpi: int,
    show: bool,
    events: List[Dict[str, object]],
) -> None:
    if reddit_metrics.empty and voat_metrics.empty:
        logger.info("No data available for %s, skipping figure.", community_label)
        return

    n_rows = len(METRICS_ORDER)
    fig, axes = plt.subplots(
        nrows=n_rows,
        ncols=2,
        figsize=(12, 2.4 * n_rows),
        sharex="col",
    )
    if n_rows == 1:
        axes = np.array([axes])

    def _format_time_axis(ax: plt.Axes) -> None:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=(1, 7)))
        ax.tick_params(axis="x", rotation=45)

    for row_idx, (metric, ylabel) in enumerate(METRICS_ORDER):
        series_to_compare: List[pd.Series] = []
        if not reddit_metrics.empty and metric in reddit_metrics:
            series_to_compare.append(reddit_metrics[metric])
        if not voat_metrics.empty and metric in voat_metrics:
            series_to_compare.append(voat_metrics[metric])
        limits = compute_limits(series_to_compare, DEFAULT_LIMITS.get(metric, (0.0, 1.0)))

        for col_idx, (platform_label, data, color) in enumerate(
            [
                (f"{community_label} — Reddit", reddit_metrics, "#1f77b4"),
                (f"{community_label} — Voat", voat_metrics, "#9467bd"),
            ]
        ):
            ax = axes[row_idx, col_idx]
            if data.empty or metric not in data:
                ax.text(
                    0.5,
                    0.5,
                    "no data",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                    color="#777777",
                )
            else:
                ax.plot(data["month"], data[metric], color=color)
            ax.set_ylim(limits)
            add_event_markers(ax, events)
            _format_time_axis(ax)

            if row_idx == 0:
                ax.set_title(platform_label)
            if col_idx == 0:
                ax.set_ylabel(ylabel)
            if row_idx == n_rows - 1:
                ax.set_xlabel("month")

    fig.suptitle(f"{community_label} — Core metrics comparison", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.985))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    logger.info("Saved %s", output_path)

    if show:
        plt.show()
    plt.close(fig)


def pick_display_name(reddit_name: Optional[str], voat_name: Optional[str]) -> str:
    if reddit_name:
        return reddit_name
    if voat_name:
        return voat_name
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Reddit/Voat core metric panels (mean internal edges, retention, clustering)."
    )
    parser.add_argument(
        "--cp-dir",
        default="results/core-periphery",
        type=Path,
        help="Base directory containing platform subfolders.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write figures (default: <cp-dir>/compare/figures).",
    )
    parser.add_argument(
        "--communities",
        nargs="*",
        help="Subset of communities (case-insensitive) to plot. Defaults to all common keys.",
    )
    parser.add_argument("--dpi", type=int, default=200, help="Figure DPI (default: 200).")
    parser.add_argument("--show", action="store_true", help="Display figures instead of saving only.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    parser.add_argument(
        "--events-notes",
        type=Path,
        default=Path("notes/notes.md"),
        help="Markdown file containing key events (default: notes/notes.md).",
    )
    parser.add_argument(
        "--networks-dir",
        type=Path,
        default=Path("results/networks"),
        help="Base directory for clustering CSV outputs (default: results/networks).",
    )
    args = parser.parse_args()

    configure_logging(args.verbose)
    configure_matplotlib()

    cp_dir: Path = args.cp_dir
    output_dir: Path = args.output_dir or (cp_dir / "compare" / "figures")
    networks_dir: Path = args.networks_dir

    reddit_map = discover_communities(cp_dir, "reddit")
    voat_map = discover_communities(cp_dir, "voat")
    all_keys = set(reddit_map) | set(voat_map)
    selected_keys = filter_keys(all_keys, args.communities)

    events = load_key_events(args.events_notes)

    if not selected_keys:
        logger.error("No communities found. Check --cp-dir and filenames.")
        return

    for key in selected_keys:
        reddit_name = reddit_map.get(key)
        voat_name = voat_map.get(key)

        reddit_block = (
            load_block_stats(cp_dir / "reddit" / "results" / f"reddit_{reddit_name}_cp_block_stats.csv")
            if reddit_name
            else pd.DataFrame()
        )
        reddit_summary = (
            load_summary(cp_dir / "reddit" / "results" / f"reddit_{reddit_name}_cp_summary.csv")
            if reddit_name
            else pd.DataFrame()
        )
        reddit_stability = (
            load_stability_metrics(
                cp_dir / "reddit" / "results" / f"reddit_{reddit_name}_cp_stability.csv", reddit_summary
            )
            if reddit_name
            else pd.DataFrame()
        )
        reddit_clustering = (
            load_clustering_metrics(
                networks_dir / "reddit" / "results" / f"reddit_{reddit_name}_clustering.csv"
            )
            if reddit_name
            else pd.DataFrame()
        )
        reddit_metrics = combine_metrics(reddit_block, reddit_stability, reddit_clustering)

        voat_block = (
            load_block_stats(cp_dir / "voat" / "results" / f"voat_{voat_name}_cp_block_stats.csv")
            if voat_name
            else pd.DataFrame()
        )
        voat_summary = (
            load_summary(cp_dir / "voat" / "results" / f"voat_{voat_name}_cp_summary.csv")
            if voat_name
            else pd.DataFrame()
        )
        voat_stability = (
            load_stability_metrics(
                cp_dir / "voat" / "results" / f"voat_{voat_name}_cp_stability.csv", voat_summary
            )
            if voat_name
            else pd.DataFrame()
        )
        voat_clustering = (
            load_clustering_metrics(
                networks_dir / "voat" / "results" / f"voat_{voat_name}_clustering.csv"
            )
            if voat_name
            else pd.DataFrame()
        )
        voat_metrics = combine_metrics(voat_block, voat_stability, voat_clustering)

        label = pick_display_name(reddit_name, voat_name)
        safe_slug = label.lower().replace(" ", "_")
        output_path = output_dir / f"{safe_slug}_core_metrics.png"
        build_plot(
            label,
            reddit_metrics,
            voat_metrics,
            output_path,
            args.dpi,
            args.show,
            events,
        )


if __name__ == "__main__":
    main()
