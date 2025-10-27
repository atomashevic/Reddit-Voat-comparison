#!/usr/bin/env python3
"""Plot monthly core/periphery toxicity and sentiment panels for Reddit communities."""

import argparse
import logging
import os
import re
from typing import Callable, List, Optional, Tuple

import pandas as pd

LABEL_ORDER = ["core", "periphery"]


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def _load_key_events(notes_path: str) -> List[Tuple[str, pd.Timestamp]]:
    events = {
        "A": "/r/beatingwomen",
        "B": "/r/TheFappening",
        "C": "/r/nigger",
        "D": "/r/fatpeoplehate",
        "E": "/r/pizzagate",
        "F": "/r/incel",
        "G": "/r/GreatAwakening",
    }
    if not os.path.isfile(notes_path):
        return []
    with open(notes_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    sep = r"[-‑‒–-−]"
    pat = re.compile(rf"^\s*[-*]?\s*(\d{{4}}){sep}(\d{{2}})(?:{sep}(\d{{2}}))?:.*$", re.MULTILINE)
    out: List[Tuple[str, pd.Timestamp]] = []
    for label, marker in events.items():
        for line in text.splitlines():
            if marker in line:
                m = pat.match(line)
                if m:
                    year, month = m.group(1), m.group(2)
                    dt = pd.to_datetime(f"{year}-{month}-01", errors="coerce")
                    out.append((label, dt))
                    break
    out.sort(key=lambda kv: (kv[1] if pd.notna(kv[1]) else pd.Timestamp.max))
    return out


def _locate_metrics_file(results_dir: str, community: str) -> Tuple[str, str]:
    plat = "reddit"
    if not os.path.isdir(results_dir):
        raise FileNotFoundError(f"Missing metrics directory: {results_dir}")
    target = community.lower()
    for name in os.listdir(results_dir):
        if not name.startswith(f"{plat}_") or not name.endswith("_cp_monthly_group_metrics.csv"):
            continue
        comm_token = name[len(plat) + 1 : -len("_cp_monthly_group_metrics.csv")]
        if comm_token.lower() == target:
            return os.path.join(results_dir, name), comm_token
    raise FileNotFoundError(
        f"Unable to locate monthly metrics CSV for community '{community}' under {results_dir}"
    )


def _locate_block_stats(cp_dir: str, community: str) -> Tuple[str, str]:
    plat = "reddit"
    res_dir = os.path.join(cp_dir, plat, "results")
    if not os.path.isdir(res_dir):
        raise FileNotFoundError(f"Missing CP results directory: {res_dir}")
    target = community.lower()
    for name in os.listdir(res_dir):
        if not name.startswith(f"{plat}_") or not name.endswith("_cp_block_stats.csv"):
            continue
        comm_token = name[len(plat) + 1 : -len("_cp_block_stats.csv")]
        if comm_token.lower() == target:
            return os.path.join(res_dir, name), comm_token
    raise FileNotFoundError(
        f"Unable to locate block stats for community '{community}' under {res_dir}"
    )


def _prepare_metric_frames(metrics: pd.DataFrame) -> pd.DataFrame:
    df = metrics.copy()
    df["group"] = df["group"].astype(str).str.lower()
    df = df[df["group"].isin(LABEL_ORDER)]
    df["month_dt"] = pd.to_datetime(df["month"] + "-01", errors="coerce")
    df = df.sort_values(["month_dt", "group"])
    return df


def _prepare_block_stats(block: pd.DataFrame) -> pd.DataFrame:
    df = block.copy()
    col = "month"
    if col not in df.columns and "window" in df.columns:
        df[col] = df["window"].astype(str)
    if col not in df.columns:
        raise KeyError("Block stats dataframe is missing 'month' or 'window' column")
    df["month_dt"] = pd.to_datetime(df[col].astype(str) + "-01", errors="coerce")
    df = df.sort_values("month_dt")
    return df


def _locate_reputation_file(reputation_dir: str, community: str) -> Optional[str]:
    plat = "reddit"
    if not reputation_dir:
        return None
    target = community.lower()
    fname = f"{plat}_{target}_cp_monthly_reputation.csv"
    candidates = [
        os.path.join(reputation_dir, target, plat, "results", fname),
        os.path.join(reputation_dir, plat, target, "results", fname),
        os.path.join(reputation_dir, plat, "results", fname),
        os.path.join(reputation_dir, fname),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _prepare_reputation_frame(rep_wide: pd.DataFrame) -> Optional[pd.DataFrame]:
    if rep_wide is None or rep_wide.empty:
        return None
    df = rep_wide.copy()
    df.columns = [c.strip() for c in df.columns]
    core_cols = ["core_mean_rep_active", "core_mean_rep"]
    peri_cols = ["periphery_mean_rep_active", "periphery_mean_rep"]
    core_col = next((c for c in core_cols if c in df.columns), None)
    peri_col = next((c for c in peri_cols if c in df.columns), None)
    if core_col is None or peri_col is None or "month" not in df.columns:
        return None
    core = df[["month", core_col]].rename(columns={core_col: "mean_reputation"})
    core["group"] = "core"
    peri = df[["month", peri_col]].rename(columns={peri_col: "mean_reputation"})
    peri["group"] = "periphery"
    out = pd.concat([core, peri], ignore_index=True)
    out["month_dt"] = pd.to_datetime(out["month"] + "-01", errors="coerce")
    out = out.sort_values(["month_dt", "group"])
    return out


def _load_reputation_metrics(reputation_dir: str, community: str) -> Optional[pd.DataFrame]:
    rep_path = _locate_reputation_file(reputation_dir, community)
    if not rep_path:
        logging.debug("No reputation file found for community %s under %s", community, reputation_dir)
        return None
    try:
        rep_wide = pd.read_csv(rep_path)
    except Exception as exc:
        logging.warning("Failed to read reputation CSV %s: %s", rep_path, exc)
        return None
    rep_long = _prepare_reputation_frame(rep_wide)
    if rep_long is None:
        logging.warning("Reputation CSV %s missing expected columns; skipping reputation panel", rep_path)
        return None
    return rep_long


def plot_panels(
    community: str,
    metrics_df: pd.DataFrame,
    block_df: pd.DataFrame,
    out_dir: str,
    notes_path: str,
    reputation_df: Optional[pd.DataFrame] = None,
) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - matplotlib optional
        raise RuntimeError(f"matplotlib is required to plot panels: {exc}") from exc

    os.makedirs(out_dir, exist_ok=True)
    ev_months = _load_key_events(notes_path)

    metrics_df = _prepare_metric_frames(metrics_df)
    block_df = _prepare_block_stats(block_df)
    if reputation_df is not None:
        rep_df = reputation_df.copy()
    else:
        rep_df = None

    panels: List[Tuple[str, Callable]] = []

    def _plot_sizes(ax):
        ax.plot(block_df["month_dt"], pd.to_numeric(block_df["ns_core"], errors="coerce"), label="core size")
        ax.plot(block_df["month_dt"], pd.to_numeric(block_df["ns_peri"], errors="coerce"), label="periphery size")
        ax.set_title(f"{community} - Core/Periphery size")
        ax.legend(loc="upper left")

    panels.append(("sizes", _plot_sizes))

    if rep_df is not None and not rep_df.empty:
        def _plot_reputation(ax):
            for group_name in LABEL_ORDER:
                subset = rep_df[rep_df["group"] == group_name]
                if subset.empty:
                    continue
                ax.plot(subset["month_dt"], subset["mean_reputation"], label=group_name)
            ax.set_title(f"{community} - Mean reputation (per user/month)")
            ax.legend(loc="upper left")

        panels.append(("reputation", _plot_reputation))

    def _plot_metric(ax, column: str, title: str) -> None:
        for group_name in LABEL_ORDER:
            subset = metrics_df[metrics_df["group"] == group_name]
            ax.plot(subset["month_dt"], subset[column], label=group_name)
        ax.set_title(title)
        ax.legend(loc="upper left")

    panels.append((
        "toxicity",
        lambda ax: _plot_metric(
            ax,
            "mean_toxicity_per_user",
            f"{community} - Mean toxicity (per user/month)",
        ),
    ))
    panels.append((
        "vader",
        lambda ax: _plot_metric(
            ax,
            "mean_sentiment_vader_per_user",
            f"{community} - Sentiment VADER (per user/month)",
        ),
    ))
    panels.append((
        "textblob",
        lambda ax: _plot_metric(
            ax,
            "mean_sentiment_textblob_per_user",
            f"{community} - Sentiment TextBlob (per user/month)",
        ),
    ))
    panels.append((
        "subjectivity",
        lambda ax: _plot_metric(
            ax,
            "mean_subjectivity_textblob_per_user",
            f"{community} - Subjectivity (per user/month)",
        ),
    ))

    n = len(panels)
    ncols = 2
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, max(3 * nrows, 4)), sharex=True)
    if nrows == 1:
        axes = axes.reshape(1, -1)
    axes_flat = axes.ravel().tolist()

    for idx, (_, plot_fn) in enumerate(panels):
        ax = axes_flat[idx]
        plot_fn(ax)
        for ev_label, ev_dt in ev_months:
            if pd.notna(ev_dt):
                ax.axvline(ev_dt, ls="--", lw=1, color="k", alpha=0.5)
                ax.text(ev_dt, ax.get_ylim()[1], ev_label, fontsize=8, ha="center", va="top", rotation=90)

    for j in range(n, nrows * ncols):
        axes_flat[j].axis("off")

    for c in range(ncols):
        axes[nrows - 1, c].set_xlabel("month")

    fig.autofmt_xdate()
    plt.tight_layout()
    out_path = os.path.join(out_dir, f"reddit_{community}_cp_metrics_panels.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logging.info("Wrote panel figure to %s", out_path)
    return out_path


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--community", required=True, help="Community name (case-insensitive)")
    ap.add_argument(
        "--metrics-dir",
        default=os.path.join("results", "core-periphery", "reddit", "results"),
        help="Directory containing monthly metrics CSVs",
    )
    ap.add_argument(
        "--cp-output-dir",
        default=os.path.join("results", "core-periphery"),
        help="Base directory where core-periphery block stats live",
    )
    ap.add_argument(
        "--fig-dir",
        default=os.path.join("results", "core-periphery", "reddit", "figures"),
        help="Directory for output figures",
    )
    ap.add_argument(
        "--reputation-dir",
        default=os.path.join("results", "reputation"),
        help="Directory containing monthly reputation CSVs",
    )
    ap.add_argument(
        "--notes-path",
        default=os.path.join("notes", "notes.md"),
        help="Path to notes for overlaying key event markers",
    )
    ap.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    _setup_logging(args.verbose)

    metrics_path, canon_comm_metrics = _locate_metrics_file(args.metrics_dir, args.community)
    block_path, canon_comm_block = _locate_block_stats(args.cp_output_dir, args.community)

    if canon_comm_metrics.lower() != canon_comm_block.lower():
        logging.warning(
            "Community mismatch between metrics (%s) and block stats (%s)",
            canon_comm_metrics,
            canon_comm_block,
        )

    metrics = pd.read_csv(metrics_path)
    block_stats = pd.read_csv(block_path)
    reputation = _load_reputation_metrics(args.reputation_dir, canon_comm_metrics)
    if reputation is None:
        logging.info("No monthly reputation data available for %s; skipping reputation panel", canon_comm_metrics)

    plot_panels(
        canon_comm_metrics,
        metrics,
        block_stats,
        args.fig_dir,
        args.notes_path,
        reputation_df=reputation,
    )


if __name__ == "__main__":
    main()
