#!/usr/bin/env python3
"""
Regime breakpoint analysis for Voat generalist communities.

Package A script: formally validate the paper's two‑regime claim by
detecting a single structural break in key monthly time series.

The script:
  1) Loads per‑community Voat monthly metrics already produced by pipelines.
  2) For each metric, fits a single‑break segmented linear model via grid search
     and selects the breakpoint minimizing SSE.
  3) Uses a residual bootstrap to assess breakpoint stability and provide
     a rough confidence interval.
  4) Writes a CSV of breakpoint estimates and an informative text summary.

No external dependencies beyond numpy/pandas.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from scripts.migration_utils import EVENTS  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_COMMUNITIES = ["funny", "gaming", "gifs", "pics", "technology", "videos"]
DEFAULT_METRICS = [
    "toxicity_mean",
    "ei_index",
    "existing_gini",
    "reputation_mean",
    "degree_assortativity",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Single-break regime validation analysis.")
    parser.add_argument(
        "--communities",
        nargs="*",
        default=None,
        help="Communities to analyze (default: scan results/compare or NORMAL_COMMUNITIES).",
    )
    parser.add_argument(
        "--metrics",
        nargs="*",
        default=DEFAULT_METRICS,
        help=f"Metrics to analyze (default: {', '.join(DEFAULT_METRICS)}).",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=REPO_ROOT / "results",
        help="Base results directory.",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=REPO_ROOT / "backup",
        help="Backup root containing reputation CP outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "results" / "basic" / "compare" / "results",
        help="Directory for CSV and text summary outputs.",
    )
    parser.add_argument(
        "--min-segment-months",
        type=int,
        default=6,
        help="Minimum months in each segment when searching for a break.",
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=200,
        help="Residual bootstrap iterations for breakpoint CI/stability.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2025,
        help="Random seed for bootstrap.",
    )
    parser.add_argument(
        "--near-window-months",
        type=int,
        default=3,
        help="Window (months) to count breaks near the GA ban (2018-09).",
    )
    parser.add_argument(
        "--include-global",
        action="store_true",
        default=True,
        help="Also analyze an unweighted global mean across communities.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def month_distance(a: pd.Timestamp, b: pd.Timestamp) -> int:
    return abs((a.year - b.year) * 12 + (a.month - b.month))


def _load_first_existing(candidates: Iterable[Path]) -> Optional[pd.DataFrame]:
    for path in candidates:
        if path.exists():
            return pd.read_csv(path)
    return None


def load_community_frame(results_dir: Path, backup_root: Path, community: str) -> pd.DataFrame:
    """Load and merge per-community Voat monthly metrics into one frame."""
    community = community.lower()

    agg_candidates = [
        results_dir / "voat" / community / f"voat_{community}_monthly_aggregates.csv",
        results_dir / "voat" / "results" / f"voat_{community}_monthly_aggregates.csv",
        results_dir / "basic" / "voat" / "results" / f"voat_{community}_monthly_aggregates.csv",
    ]
    monthly = _load_first_existing(agg_candidates)
    if monthly is None:
        raise FileNotFoundError(f"Monthly aggregates not found for {community}. Tried: {agg_candidates}")

    monthly["month_dt"] = pd.to_datetime(monthly["month"] + "-01", errors="coerce")
    monthly = monthly.sort_values("month_dt").reset_index(drop=True)

    # E-I / partition metrics
    ei_candidates = [
        results_dir / "voat" / community / f"{community}_newcomer_partition.csv",
        results_dir / "basic" / "voat" / "results" / f"{community}_newcomer_partition.csv",
    ]
    ei_df = _load_first_existing(ei_candidates)
    if ei_df is not None and "ei_index" in ei_df.columns:
        ei_df["month_dt"] = pd.to_datetime(ei_df["month"] + "-01", errors="coerce")
        monthly = monthly.merge(ei_df[["month_dt", "ei_index"]], on="month_dt", how="left")
    else:
        monthly["ei_index"] = np.nan

    # Newcomer degree dynamics (existing_gini, newcomer share)
    dyn_candidates = [
        results_dir / "voat" / community / f"voat_{community}_newcomer_degree_dynamics.csv",
        results_dir / "basic" / "voat" / "results" / f"voat_{community}_newcomer_degree_dynamics.csv",
    ]
    dyn_df = _load_first_existing(dyn_candidates)
    if dyn_df is not None:
        dyn_df["month_dt"] = pd.to_datetime(dyn_df["month"] + "-01", errors="coerce")
        keep = [c for c in ["existing_gini", "newcomer_pop_share", "degree_share_ratio"] if c in dyn_df.columns]
        if keep:
            monthly = monthly.merge(dyn_df[["month_dt"] + keep], on="month_dt", how="left")
    else:
        monthly["existing_gini"] = np.nan

    # Reputation fallback: some monthly aggregates were built with --skip-reputation.
    if "reputation_mean" not in monthly.columns or monthly["reputation_mean"].notna().sum() == 0:
        rep_df = load_reputation_data(args.results_dir, "voat", community)
        if not rep_df.empty:
            rep_df["month_dt"] = pd.to_datetime(rep_df["month"] + "-01", errors="coerce")
            if "reputation_mean" not in monthly.columns:
                monthly = monthly.merge(rep_df[["month_dt", "reputation_mean"]], on="month_dt", how="left")
            else:
                monthly = monthly.merge(
                    rep_df[["month_dt", "reputation_mean"]].rename(columns={"reputation_mean": "reputation_mean_backup"}),
                    on="month_dt",
                    how="left",
                )
                monthly["reputation_mean"] = monthly["reputation_mean"].fillna(monthly["reputation_mean_backup"])
                monthly = monthly.drop(columns=["reputation_mean_backup"])

    monthly["community"] = community
    return monthly


def load_reputation_data(results_dir: Path, platform: str, community: str) -> pd.DataFrame:
    """Load and compute mean reputation from CP monthly reputation files in backup."""
    platform = platform.lower()
    community = community.lower()
    rep_path = (
        results_dir
        / "reputation"
        / platform
        / "results"
        / f"{platform}_{community}_cp_monthly_reputation.csv"
    )
    if not rep_path.exists():
        rep_path = (
            results_dir
            / "reputation"
            / community
            / platform
            / "results"
            / f"{platform}_{community}_cp_monthly_reputation.csv"
        )
    if not rep_path.exists():
        return pd.DataFrame()

    rep_df = pd.read_csv(rep_path)
    if rep_df.empty or "month" not in rep_df.columns:
        return pd.DataFrame()

    rep_df["month"] = rep_df["month"].astype(str)
    if {
        "core_mean_rep_active",
        "periphery_mean_rep_active",
        "core_active_users",
        "periphery_active_users",
    }.issubset(rep_df.columns):
        num = (
            rep_df["core_mean_rep_active"].fillna(0) * rep_df["core_active_users"].fillna(0)
            + rep_df["periphery_mean_rep_active"].fillna(0) * rep_df["periphery_active_users"].fillna(0)
        )
        den = rep_df["core_active_users"].fillna(0) + rep_df["periphery_active_users"].fillna(0)
        rep_df["reputation_mean"] = num / den.replace(0, np.nan)
    elif "reputation_mean" not in rep_df.columns:
        return pd.DataFrame()

    return rep_df[["month", "reputation_mean"]]


def infer_communities(results_dir: Path) -> List[str]:
    compare_dir = results_dir / "compare"
    if compare_dir.exists():
        names = sorted([p.name.lower() for p in compare_dir.iterdir() if p.is_dir()])
        if names:
            return names
    return DEFAULT_COMMUNITIES


def fit_linear(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float, np.ndarray]:
    """Return slope, intercept, SSE, fitted values."""
    if len(x) < 2:
        return float("nan"), float("nan"), float("inf"), np.full_like(y, np.nan, dtype=float)
    X = np.column_stack([np.ones_like(x, dtype=float), x.astype(float)])
    coef, *_ = np.linalg.lstsq(X, y.astype(float), rcond=None)
    intercept, slope = float(coef[0]), float(coef[1])
    yhat = intercept + slope * x
    resid = y - yhat
    sse = float(np.sum(resid**2))
    return slope, intercept, sse, yhat


@dataclass
class BreakFit:
    break_idx: int
    pre_slope: float
    post_slope: float
    pre_intercept: float
    post_intercept: float
    sse_total: float
    sse_single: float

    @property
    def sse_ratio(self) -> float:
        if self.sse_single <= 0 or not np.isfinite(self.sse_single):
            return float("nan")
        return self.sse_total / self.sse_single


def find_best_break(x: np.ndarray, y: np.ndarray, min_seg: int) -> Optional[BreakFit]:
    """Grid search for the single breakpoint minimizing total SSE."""
    n = len(x)
    if n < 2 * min_seg + 2:
        return None

    pre_slope_single, pre_intercept_single, sse_single, _ = fit_linear(x, y)
    best: Optional[BreakFit] = None

    for idx in range(min_seg, n - min_seg + 1):
        x_pre, y_pre = x[:idx], y[:idx]
        x_post, y_post = x[idx:], y[idx:]

        pre_slope, pre_intercept, sse_pre, _ = fit_linear(x_pre, y_pre)
        post_slope, post_intercept, sse_post, _ = fit_linear(x_post, y_post)
        sse_total = sse_pre + sse_post

        if best is None or sse_total < best.sse_total:
            best = BreakFit(
                break_idx=idx,
                pre_slope=pre_slope,
                post_slope=post_slope,
                pre_intercept=pre_intercept,
                post_intercept=post_intercept,
                sse_total=sse_total,
                sse_single=sse_single,
            )

    return best


def bootstrap_breaks(
    x: np.ndarray,
    y: np.ndarray,
    months: List[pd.Timestamp],
    best_fit: BreakFit,
    min_seg: int,
    iterations: int,
    rng: np.random.Generator,
) -> List[pd.Timestamp]:
    """Residual bootstrap to estimate breakpoint distribution."""
    idx = best_fit.break_idx
    pre_slope, pre_intercept, _, yhat_pre = fit_linear(x[:idx], y[:idx])
    post_slope, post_intercept, _, yhat_post = fit_linear(x[idx:], y[idx:])
    yhat = np.concatenate([yhat_pre, yhat_post])
    resid = y - yhat
    resid = resid - np.nanmean(resid)

    boot_months: List[pd.Timestamp] = []
    for _ in range(iterations):
        boot_resid = rng.choice(resid, size=len(resid), replace=True)
        y_boot = yhat + boot_resid
        boot_fit = find_best_break(x, y_boot, min_seg)
        if boot_fit is None:
            continue
        bidx = boot_fit.break_idx
        if 0 <= bidx < len(months):
            boot_months.append(months[bidx])
    return boot_months


def analyze_series(
    df: pd.DataFrame,
    metric: str,
    min_seg: int,
    bootstrap_iterations: int,
    rng: np.random.Generator,
) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    if metric not in df.columns:
        return None, f"missing metric column {metric}"

    series = df[["month_dt", metric]].dropna()
    if series.empty:
        return None, "all values NaN"

    series = series.sort_values("month_dt")
    months = series["month_dt"].tolist()
    y = series[metric].astype(float).to_numpy()
    x = np.array([(m.year * 12 + m.month) for m in months], dtype=float)
    x = x - x[0]

    best_fit = find_best_break(x, y, min_seg)
    if best_fit is None:
        return None, f"too few observations (n={len(y)})"

    best_month = months[best_fit.break_idx]
    sse_ratio = best_fit.sse_ratio

    ci_low = ci_high = stability = float("nan")
    boot_breaks: List[pd.Timestamp] = []
    if bootstrap_iterations > 0:
        boot_breaks = bootstrap_breaks(
            x, y, months, best_fit, min_seg, bootstrap_iterations, rng
        )
        if boot_breaks:
            diffs = [month_distance(best_month, b) for b in boot_breaks]
            stability = float(np.mean(np.array(diffs) <= 3))
            ci_months = sorted(boot_breaks)
            ci_low = ci_months[int(0.05 * (len(ci_months) - 1))]
            ci_high = ci_months[int(0.95 * (len(ci_months) - 1))]

    result = {
        "metric": metric,
        "n_obs": len(y),
        "best_break_month": best_month.strftime("%Y-%m"),
        "pre_slope": best_fit.pre_slope,
        "post_slope": best_fit.post_slope,
        "sse_ratio": sse_ratio,
        "ci_low_month": ci_low.strftime("%Y-%m") if isinstance(ci_low, pd.Timestamp) else "",
        "ci_high_month": ci_high.strftime("%Y-%m") if isinstance(ci_high, pd.Timestamp) else "",
        "bootstrap_stability_pm3": stability,
    }
    return result, None


def compute_global_frame(
    frames: Dict[str, pd.DataFrame], metrics: List[str]
) -> pd.DataFrame:
    """Unweighted global mean across communities by month."""
    long_frames = []
    for community, df in frames.items():
        cols = ["month_dt"] + [m for m in metrics if m in df.columns]
        long = df[cols].copy()
        long["community"] = community
        long_frames.append(long)

    if not long_frames:
        return pd.DataFrame(columns=["month_dt"])

    all_df = pd.concat(long_frames, ignore_index=True)
    rows: List[Dict[str, object]] = []
    for month_dt, group in all_df.groupby("month_dt", observed=True):
        row: Dict[str, object] = {"month_dt": month_dt}
        for metric in metrics:
            if metric in group.columns:
                row[metric] = float(pd.to_numeric(group[metric], errors="coerce").mean())
        rows.append(row)
    out = pd.DataFrame(rows).sort_values("month_dt")
    out["month"] = out["month_dt"].dt.strftime("%Y-%m")
    out["community"] = "global"
    return out


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    communities = args.communities or infer_communities(args.results_dir)
    metrics = [m for m in args.metrics]

    logger.info(f"Analyzing communities: {communities}")
    logger.info(f"Analyzing metrics: {metrics}")

    frames: Dict[str, pd.DataFrame] = {}
    skipped_load: Dict[str, str] = {}
    for community in communities:
        try:
            frames[community] = load_community_frame(args.results_dir, args.backup_root, community)
        except Exception as e:
            skipped_load[community] = str(e)

    if args.include_global and frames:
        frames["global"] = compute_global_frame(frames, metrics)

    rng = np.random.default_rng(args.seed)
    results: List[Dict[str, object]] = []
    skipped_series: List[Tuple[str, str, str]] = []

    for community, frame in frames.items():
        for metric in metrics:
            res, reason = analyze_series(
                frame,
                metric,
                args.min_segment_months,
                args.bootstrap_iterations,
                rng,
            )
            if res is None:
                skipped_series.append((community, metric, reason or "unknown"))
                continue
            res["community"] = community

            event_month = pd.Timestamp(EVENTS["B"].strftime("%Y-%m-01"))
            break_dt = pd.Timestamp(res["best_break_month"] + "-01")
            dist = month_distance(break_dt, event_month)
            res["dist_to_ga_ban_months"] = dist
            res["near_ga_ban_pm_window"] = dist <= args.near_window_months

            results.append(res)

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    results_df = pd.DataFrame(results)
    results_path = out_dir / "regime_breakpoints.csv"
    results_df.to_csv(results_path, index=False)

    # Text summary
    summary_lines: List[str] = []
    summary_lines.append("Regime Breakpoint Analysis (single-break segmented regression)")
    summary_lines.append("=" * 72)
    summary_lines.append(f"Communities analyzed: {', '.join(sorted(frames.keys()))}")
    summary_lines.append(f"Metrics analyzed: {', '.join(metrics)}")
    summary_lines.append(f"Min segment length: {args.min_segment_months} months")
    summary_lines.append(f"Bootstrap iterations: {args.bootstrap_iterations} (seed={args.seed})")
    summary_lines.append(
        f"Reference event (GA ban): {EVENTS['B'].date()} (month={EVENTS['B'].strftime('%Y-%m')})"
    )
    summary_lines.append("")

    if results_df.empty:
        summary_lines.append("No valid series to analyze. See skipped sections below.")
    else:
        total_series = len(results_df)
        near_total = int(results_df["near_ga_ban_pm_window"].sum())
        summary_lines.append(
            f"Breaks near GA ban (±{args.near_window_months} months): {near_total}/{total_series}"
        )
        summary_lines.append("")

        for metric in metrics:
            sub = results_df[results_df["metric"] == metric]
            if sub.empty:
                continue
            near = int(sub["near_ga_ban_pm_window"].sum())
            best_months = ", ".join(sorted(sub["best_break_month"].unique()))
            med_ratio = float(sub["sse_ratio"].median()) if sub["sse_ratio"].notna().any() else float("nan")
            summary_lines.append(
                f"- {metric}: {near}/{len(sub)} near GA; break months observed: {best_months}; median SSE ratio={med_ratio:.3f}"
            )

        summary_lines.append("")
        strong = results_df.sort_values("sse_ratio").head(8)
        summary_lines.append("Strongest breaks (lowest SSE ratio):")
        for row in strong.itertuples(index=False):
            ci_part = ""
            if getattr(row, "ci_low_month", "") and getattr(row, "ci_high_month", ""):
                ci_part = f", CI≈[{row.ci_low_month},{row.ci_high_month}], stab±3m={row.bootstrap_stability_pm3:.2f}"
            summary_lines.append(
                f"  {row.community}/{row.metric}: break={row.best_break_month}, "
                f"pre_slope={row.pre_slope:.4g}, post_slope={row.post_slope:.4g}, "
                f"SSE_ratio={row.sse_ratio:.3f}{ci_part}"
            )

    if skipped_load:
        summary_lines.append("")
        summary_lines.append("Communities skipped (missing inputs):")
        for community, reason in skipped_load.items():
            summary_lines.append(f"  {community}: {reason}")

    if skipped_series:
        summary_lines.append("")
        summary_lines.append("Series skipped (insufficient data or missing metric):")
        for community, metric, reason in skipped_series:
            summary_lines.append(f"  {community}/{metric}: {reason}")

    summary_path = out_dir / "regime_break_summary.txt"
    summary_path.write_text("\n".join(summary_lines))

    logger.info(f"Wrote breakpoint table to {results_path}")
    logger.info(f"Wrote text summary to {summary_path}")


if __name__ == "__main__":
    main()
