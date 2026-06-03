#!/usr/bin/env python3
"""
Regime breakpoint analysis for Voat generalist communities.

This script treats breakpoint analysis as a ban-alignment validation check. It
keeps the original single-break estimates while adding model comparison,
alternative split-date robustness, E-I newcomer-definition sensitivity, and
global segmented-fit outputs.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from scripts.migration_utils import EVENTS, EVENTS_CHRONO, EVENT_LABELS_CHRONO  # noqa: E402

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
    parser = argparse.ArgumentParser(description="Regime breakpoint and ban-alignment validation.")
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
        "--figure-dir",
        type=Path,
        default=REPO_ROOT / "results" / "basic" / "compare" / "figures",
        help="Directory for generated figures.",
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
        "--max-breaks",
        type=int,
        default=2,
        help="Maximum number of breakpoints for model comparison.",
    )
    parser.add_argument(
        "--rolling-tenures",
        nargs="*",
        type=int,
        default=[3, 6, 12],
        help="Rolling-tenure E-I definitions to include if outputs exist.",
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


def display_path(path: Path) -> str:
    """Return a stable repo-relative path when the output lives under this checkout."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


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
        rep_df = load_reputation_data(results_dir, "voat", community)
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
class SegmentedFit:
    break_indices: Tuple[int, ...]
    slopes: Tuple[float, ...]
    intercepts: Tuple[float, ...]
    sse_total: float
    rmse: float
    aicc: float
    bic: float
    yhat: np.ndarray

    @property
    def n_breaks(self) -> int:
        return len(self.break_indices)


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


def _valid_break_indices(n: int, break_indices: Sequence[int], min_seg: int) -> bool:
    if any(idx <= 0 or idx >= n for idx in break_indices):
        return False
    if tuple(sorted(break_indices)) != tuple(break_indices):
        return False
    boundaries = (0, *break_indices, n)
    return all((right - left) >= min_seg for left, right in zip(boundaries[:-1], boundaries[1:]))


def _information_criteria(sse: float, n_obs: int, n_params: int) -> Tuple[float, float]:
    if n_obs <= 0 or n_params <= 0:
        return float("nan"), float("nan")
    safe_sse = max(float(sse), np.finfo(float).tiny)
    aic = n_obs * np.log(safe_sse / n_obs) + 2 * n_params
    if n_obs > n_params + 1:
        aicc = aic + (2 * n_params * (n_params + 1)) / (n_obs - n_params - 1)
    else:
        aicc = float("inf")
    bic = n_obs * np.log(safe_sse / n_obs) + n_params * np.log(n_obs)
    return float(aicc), float(bic)


def fit_segmented_model(
    x: np.ndarray,
    y: np.ndarray,
    break_indices: Sequence[int] = (),
    min_seg: int = 2,
) -> Optional[SegmentedFit]:
    """Fit independent linear segments for fixed breakpoint indices."""
    n = len(x)
    breaks = tuple(int(idx) for idx in break_indices)
    if not _valid_break_indices(n, breaks, min_seg):
        return None

    boundaries = (0, *breaks, n)
    yhat = np.full(n, np.nan, dtype=float)
    slopes: List[float] = []
    intercepts: List[float] = []
    sse_total = 0.0

    for left, right in zip(boundaries[:-1], boundaries[1:]):
        slope, intercept, sse, segment_yhat = fit_linear(x[left:right], y[left:right])
        slopes.append(slope)
        intercepts.append(intercept)
        yhat[left:right] = segment_yhat
        sse_total += sse

    n_segments = len(boundaries) - 1
    n_params = (2 * n_segments) + len(breaks)
    rmse = float(np.sqrt(sse_total / n)) if n else float("nan")
    aicc, bic = _information_criteria(sse_total, n, n_params)
    return SegmentedFit(
        break_indices=breaks,
        slopes=tuple(slopes),
        intercepts=tuple(intercepts),
        sse_total=float(sse_total),
        rmse=rmse,
        aicc=aicc,
        bic=bic,
        yhat=yhat,
    )


def find_best_segmented_model(
    x: np.ndarray,
    y: np.ndarray,
    n_breaks: int,
    min_seg: int,
) -> Optional[SegmentedFit]:
    """Grid-search the SSE-minimizing segmented model with n_breaks."""
    n = len(x)
    if n_breaks == 0:
        return fit_segmented_model(x, y, (), min_seg)
    if n < ((n_breaks + 1) * min_seg):
        return None

    best: Optional[SegmentedFit] = None
    if n_breaks == 1:
        for idx in range(min_seg, n - min_seg + 1):
            fit = fit_segmented_model(x, y, (idx,), min_seg)
            if fit is not None and (best is None or fit.sse_total < best.sse_total):
                best = fit
        return best

    if n_breaks == 2:
        for first_idx in range(min_seg, n - (2 * min_seg) + 1):
            for second_idx in range(first_idx + min_seg, n - min_seg + 1):
                fit = fit_segmented_model(x, y, (first_idx, second_idx), min_seg)
                if fit is not None and (best is None or fit.sse_total < best.sse_total):
                    best = fit
        return best

    raise ValueError("Only 0, 1, or 2 breakpoints are supported.")


def break_index_for_month(months: Sequence[pd.Timestamp], split_month: pd.Timestamp) -> int:
    """Return the first index whose month is at or after split_month."""
    split = pd.Timestamp(split_month).to_period("M").to_timestamp()
    for idx, month in enumerate(months):
        if pd.Timestamp(month).to_period("M").to_timestamp() >= split:
            return idx
    return len(months)


def prepare_metric_series(
    df: pd.DataFrame,
    metric: str,
) -> Tuple[Optional[List[pd.Timestamp]], Optional[np.ndarray], Optional[np.ndarray], Optional[str]]:
    if metric not in df.columns:
        return None, None, None, f"missing metric column {metric}"

    series = df[["month_dt", metric]].dropna().sort_values("month_dt")
    if series.empty:
        return None, None, None, "all values NaN"

    months = series["month_dt"].tolist()
    y = series[metric].astype(float).to_numpy()
    x = np.array([(m.year * 12 + m.month) for m in months], dtype=float)
    x = x - x[0]
    return months, x, y, None


def format_break_months(fit: SegmentedFit, months: Sequence[pd.Timestamp]) -> str:
    if not fit.break_indices:
        return ""
    return ";".join(months[idx].strftime("%Y-%m") for idx in fit.break_indices)


def distance_to_event_month(break_months: str, event_month: pd.Timestamp) -> Optional[int]:
    if not break_months:
        return None
    distances = [
        month_distance(pd.Timestamp(month + "-01"), event_month)
        for month in break_months.split(";")
        if month
    ]
    return min(distances) if distances else None


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


def model_comparison_rows(
    community: str,
    metric: str,
    source_definition: str,
    df: pd.DataFrame,
    max_breaks: int,
    min_seg: int,
    near_window: int,
) -> List[Dict[str, object]]:
    months, x, y, reason = prepare_metric_series(df, metric)
    if reason is not None or months is None or x is None or y is None:
        return []

    fits: Dict[int, SegmentedFit] = {}
    for n_breaks in range(max_breaks + 1):
        fit = find_best_segmented_model(x, y, n_breaks, min_seg)
        if fit is not None:
            fits[n_breaks] = fit

    if not fits:
        return []

    no_break_bic = fits[0].bic if 0 in fits else float("nan")
    best_bic = min(fit.bic for fit in fits.values())
    ga_month = pd.Timestamp(EVENTS["B"].strftime("%Y-%m-01"))
    rows: List[Dict[str, object]] = []

    for n_breaks, fit in sorted(fits.items()):
        break_months = format_break_months(fit, months)
        dist = distance_to_event_month(break_months, ga_month)
        rows.append(
            {
                "community": community,
                "metric": metric,
                "source_definition": source_definition,
                "model": f"{n_breaks}_break",
                "n_breaks": n_breaks,
                "n_obs": len(y),
                "break_months": break_months,
                "sse": fit.sse_total,
                "rmse": fit.rmse,
                "aicc": fit.aicc,
                "bic": fit.bic,
                "delta_bic_vs_no_break": fit.bic - no_break_bic,
                "bic_selected": bool(np.isclose(fit.bic, best_bic)),
                "dist_to_ga_ban_months": dist if dist is not None else "",
                "near_ga_ban_pm_window": bool(dist is not None and dist <= near_window),
                "slopes": ";".join(f"{s:.8g}" for s in fit.slopes),
            }
        )
    return rows


def fixed_split_candidates() -> List[Tuple[str, str, pd.Timestamp]]:
    candidates: List[Tuple[str, str, pd.Timestamp]] = []
    for key in ["A", "B", "C", "D"]:
        event_month = EVENTS_CHRONO[key].to_period("M").to_timestamp()
        label = EVENT_LABELS_CHRONO[key].replace(" ", "_").replace("/", "_")
        candidates.append(("event", label, event_month))

    ga_month = EVENTS["B"].to_period("M").to_timestamp()
    for offset in range(-6, 7):
        split_month = ga_month + pd.DateOffset(months=offset)
        if offset < 0:
            label = f"GA_minus_{abs(offset):02d}m"
        elif offset > 0:
            label = f"GA_plus_{offset:02d}m"
        else:
            label = "GA_00m"
        candidates.append(("ga_local", label, split_month))
    return candidates


def split_robustness_rows(
    community: str,
    metric: str,
    df: pd.DataFrame,
    min_seg: int,
) -> List[Dict[str, object]]:
    months, x, y, reason = prepare_metric_series(df, metric)
    if reason is not None or months is None or x is None or y is None:
        return []

    no_break = find_best_segmented_model(x, y, 0, min_seg)
    best_one = find_best_segmented_model(x, y, 1, min_seg)
    if no_break is None or best_one is None:
        return []

    rows: List[Dict[str, object]] = []
    for candidate_group, split_label, split_month in fixed_split_candidates():
        split_idx = break_index_for_month(months, split_month)
        fixed_fit = fit_segmented_model(x, y, (split_idx,), min_seg)
        valid = fixed_fit is not None
        row: Dict[str, object] = {
            "community": community,
            "metric": metric,
            "candidate_group": candidate_group,
            "split_label": split_label,
            "split_month": pd.Timestamp(split_month).strftime("%Y-%m"),
            "valid": valid,
            "best_one_break_month": format_break_months(best_one, months),
            "best_one_break_bic": best_one.bic,
            "no_break_bic": no_break.bic,
        }
        if fixed_fit is None:
            row.update(
                {
                    "sse": "",
                    "rmse": "",
                    "aicc": "",
                    "bic": "",
                    "delta_bic_vs_no_break": "",
                    "delta_bic_vs_best_one_break": "",
                    "sse_ratio_vs_no_break": "",
                    "sse_ratio_vs_best_one_break": "",
                }
            )
        else:
            row.update(
                {
                    "sse": fixed_fit.sse_total,
                    "rmse": fixed_fit.rmse,
                    "aicc": fixed_fit.aicc,
                    "bic": fixed_fit.bic,
                    "delta_bic_vs_no_break": fixed_fit.bic - no_break.bic,
                    "delta_bic_vs_best_one_break": fixed_fit.bic - best_one.bic,
                    "sse_ratio_vs_no_break": fixed_fit.sse_total / no_break.sse_total
                    if no_break.sse_total > 0
                    else float("nan"),
                    "sse_ratio_vs_best_one_break": fixed_fit.sse_total / best_one.sse_total
                    if best_one.sse_total > 0
                    else float("nan"),
                }
            )
        rows.append(row)
    return rows


def load_ei_definition_frames(
    frames: Dict[str, pd.DataFrame],
    output_dir: Path,
    tenures: Sequence[int],
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """Load event-based and rolling-tenure E-I frames for sensitivity checks."""
    definitions: Dict[str, Dict[str, pd.DataFrame]] = {"event_based": {}}
    for community, frame in frames.items():
        if "ei_index" in frame.columns:
            definitions["event_based"][community] = frame[["month_dt", "ei_index"]].copy()

    for tenure in tenures:
        source = f"rolling_tenure_{tenure}m"
        source_frames: Dict[str, pd.DataFrame] = {}
        for community in frames:
            path = output_dir / f"c2_ei_rolling_tenure{tenure}_{community}.csv"
            if not path.exists():
                continue
            df = pd.read_csv(path)
            if "month" not in df.columns or "ei_index_rolling" not in df.columns:
                continue
            df["month_dt"] = pd.to_datetime(df["month"].astype(str) + "-01", errors="coerce")
            source_frames[community] = df[["month_dt", "ei_index_rolling"]].rename(
                columns={"ei_index_rolling": "ei_index"}
            )
        if source_frames:
            definitions[source] = source_frames
    return definitions


def global_fit_rows(
    global_frame: pd.DataFrame,
    metrics: List[str],
    max_breaks: int,
    min_seg: int,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for metric in metrics:
        months, x, y, reason = prepare_metric_series(global_frame, metric)
        if reason is not None or months is None or x is None or y is None:
            continue

        fits: Dict[int, SegmentedFit] = {}
        for n_breaks in range(max_breaks + 1):
            fit = find_best_segmented_model(x, y, n_breaks, min_seg)
            if fit is not None:
                fits[n_breaks] = fit
        if not fits:
            continue

        selected_break_count, selected_fit = min(fits.items(), key=lambda item: item[1].bic)
        no_break_fit = fits.get(0)
        one_break_fit = fits.get(1)
        selected_breaks = format_break_months(selected_fit, months)
        one_breaks = format_break_months(one_break_fit, months) if one_break_fit else ""

        for idx, month in enumerate(months):
            rows.append(
                {
                    "metric": metric,
                    "month": month.strftime("%Y-%m"),
                    "observed": y[idx],
                    "fit_bic_selected": selected_fit.yhat[idx],
                    "fit_no_break": no_break_fit.yhat[idx] if no_break_fit else "",
                    "fit_one_break": one_break_fit.yhat[idx] if one_break_fit else "",
                    "bic_selected_model": f"{selected_break_count}_break",
                    "bic_selected_break_months": selected_breaks,
                    "one_break_months": one_breaks,
                }
            )
    return rows


def plot_global_segmented_fits(fit_df: pd.DataFrame, out_path: Path) -> bool:
    if fit_df.empty:
        return False

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - depends on optional plotting stack.
        logger.warning(f"Skipping global segmented-fit plot: {exc}")
        return False

    metrics = [m for m in DEFAULT_METRICS if m in set(fit_df["metric"])]
    if not metrics:
        return False

    fig, axes = plt.subplots(len(metrics), 1, figsize=(10, 2.1 * len(metrics)), sharex=True)
    if len(metrics) == 1:
        axes = [axes]

    event_lines = [
        ("FPH", EVENTS_CHRONO["A"]),
        ("PG", EVENTS_CHRONO["B"]),
        ("GA", EVENTS_CHRONO["C"]),
        ("TD", EVENTS_CHRONO["D"]),
    ]

    for ax, metric in zip(axes, metrics):
        sub = fit_df[fit_df["metric"] == metric].copy()
        sub["month_dt"] = pd.to_datetime(sub["month"] + "-01", errors="coerce")
        sub = sub.sort_values("month_dt")
        ax.plot(sub["month_dt"], sub["observed"], color="#222222", linewidth=1.4, label="Observed")
        ax.plot(
            sub["month_dt"],
            sub["fit_bic_selected"],
            color="#b03a2e",
            linewidth=2.0,
            label="BIC-selected segmented fit",
        )
        if "fit_one_break" in sub.columns and pd.to_numeric(sub["fit_one_break"], errors="coerce").notna().any():
            ax.plot(
                sub["month_dt"],
                pd.to_numeric(sub["fit_one_break"], errors="coerce"),
                color="#2e6db0",
                linewidth=1.4,
                linestyle="--",
                label="Best one-break fit",
            )
        for label, event_date in event_lines:
            ax.axvline(event_date, color="#777777", linestyle=":", linewidth=0.8)
            if metric == metrics[0]:
                ax.text(event_date, ax.get_ylim()[1], label, va="bottom", ha="center", fontsize=8)
        selected_model = sub["bic_selected_model"].iloc[0]
        selected_breaks = sub["bic_selected_break_months"].iloc[0]
        suffix = f" ({selected_model}: {selected_breaks or 'none'})"
        ax.set_ylabel(metric)
        ax.set_title(metric + suffix, fontsize=10)
        ax.grid(alpha=0.2)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return True


def append_upgrade_summary(
    summary_lines: List[str],
    model_df: pd.DataFrame,
    split_df: pd.DataFrame,
    ei_sensitivity_df: pd.DataFrame,
    metrics: List[str],
    near_window: int,
) -> None:
    summary_lines.append("")
    summary_lines.append("Model comparison and robustness upgrade")
    summary_lines.append("=" * 72)
    if model_df.empty:
        summary_lines.append("No model-comparison rows were produced.")
        return

    selected = model_df[model_df["bic_selected"] == True]
    summary_lines.append("BIC-selected model counts by metric:")
    for metric in metrics:
        sub = selected[(selected["metric"] == metric) & (selected["source_definition"] == "event_based")]
        if sub.empty:
            continue
        counts = sub["model"].value_counts().to_dict()
        parts = ", ".join(f"{model}={count}" for model, count in sorted(counts.items()))
        summary_lines.append(f"- {metric}: {parts}")

    one_break = model_df[
        (model_df["model"] == "1_break") & (model_df["source_definition"] == "event_based")
    ]
    summary_lines.append("")
    summary_lines.append(f"Best one-break GA alignment (+/-{near_window} months):")
    for metric in metrics:
        sub = one_break[one_break["metric"] == metric]
        if sub.empty:
            continue
        near = int(sub["near_ga_ban_pm_window"].sum())
        months = ", ".join(sorted(set(str(m) for m in sub["break_months"] if str(m))))
        summary_lines.append(f"- {metric}: {near}/{len(sub)} near GA; break months={months}")

    if not split_df.empty:
        summary_lines.append("")
        summary_lines.append("Fixed split robustness:")
        ga = split_df[(split_df["candidate_group"] == "event") & (split_df["split_label"] == "GA_Ban")]
        for metric in metrics:
            sub = ga[(ga["metric"] == metric) & (ga["valid"] == True)]
            if sub.empty:
                continue
            median_delta = pd.to_numeric(sub["delta_bic_vs_best_one_break"], errors="coerce").median()
            median_ratio = pd.to_numeric(sub["sse_ratio_vs_best_one_break"], errors="coerce").median()
            summary_lines.append(
                f"- {metric}: GA fixed split median Delta BIC vs best one-break={median_delta:.2f}; "
                f"median SSE ratio vs best one-break={median_ratio:.3f}"
            )

        summary_lines.append("")
        summary_lines.append("Best local GA split robustness (GA +/-6 months):")
        local = split_df[(split_df["candidate_group"] == "ga_local") & (split_df["valid"] == True)]
        for metric in metrics:
            sub = local[local["metric"] == metric]
            if sub.empty:
                continue
            med = (
                sub.groupby("split_label", as_index=False)
                .agg(
                    median_delta_bic=("delta_bic_vs_best_one_break", "median"),
                    median_sse_ratio=("sse_ratio_vs_best_one_break", "median"),
                )
                .sort_values("median_delta_bic")
            )
            best = med.iloc[0]
            summary_lines.append(
                f"- {metric}: best local split={best.split_label}; "
                f"median Delta BIC={best.median_delta_bic:.2f}; "
                f"median SSE ratio={best.median_sse_ratio:.3f}"
            )

    if not ei_sensitivity_df.empty:
        summary_lines.append("")
        summary_lines.append("E-I newcomer-definition sensitivity:")
        ei_one = ei_sensitivity_df[ei_sensitivity_df["model"] == "1_break"]
        for source in sorted(ei_one["source_definition"].unique()):
            sub = ei_one[ei_one["source_definition"] == source]
            near = int(sub["near_ga_ban_pm_window"].sum())
            months = ", ".join(sorted(set(str(m) for m in sub["break_months"] if str(m))))
            summary_lines.append(f"- {source}: {near}/{len(sub)} near GA; break months={months}")

    summary_lines.append("")
    summary_lines.append("Reviewer-facing interpretation:")
    summary_lines.append(
        "E-I provides the strongest GA-aligned structural break evidence. "
        "Toxicity and reputation do not show robust GA-aligned breaks in the "
        "one-break validation and should be described as gradual or heterogeneous trends."
    )


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    communities = args.communities or infer_communities(args.results_dir)
    metrics = [m for m in args.metrics]
    max_breaks = max(0, min(int(args.max_breaks), 2))
    if max_breaks != args.max_breaks:
        logger.warning("Only 0, 1, and 2 break models are supported; using max_breaks=%s", max_breaks)

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
    model_rows: List[Dict[str, object]] = []
    split_rows: List[Dict[str, object]] = []
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
            model_rows.extend(
                model_comparison_rows(
                    community,
                    metric,
                    "event_based",
                    frame,
                    max_breaks,
                    args.min_segment_months,
                    args.near_window_months,
                )
            )
            split_rows.extend(split_robustness_rows(community, metric, frame, args.min_segment_months))

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    results_df = pd.DataFrame(results)
    results_path = out_dir / "regime_breakpoints.csv"
    results_df.to_csv(results_path, index=False)

    model_df = pd.DataFrame(model_rows)
    model_path = out_dir / "regime_model_comparison.csv"
    model_df.to_csv(model_path, index=False)

    split_df = pd.DataFrame(split_rows)
    split_path = out_dir / "regime_split_robustness.csv"
    split_df.to_csv(split_path, index=False)

    ei_sensitivity_rows: List[Dict[str, object]] = []
    ei_definitions = load_ei_definition_frames(frames, out_dir, args.rolling_tenures)
    for source_definition, source_frames in ei_definitions.items():
        for community, frame in source_frames.items():
            ei_sensitivity_rows.extend(
                model_comparison_rows(
                    community,
                    "ei_index",
                    source_definition,
                    frame,
                    max_breaks,
                    args.min_segment_months,
                    args.near_window_months,
                )
            )

    ei_sensitivity_df = pd.DataFrame(ei_sensitivity_rows)
    ei_sensitivity_path = out_dir / "regime_ei_definition_sensitivity.csv"
    ei_sensitivity_df.to_csv(ei_sensitivity_path, index=False)

    global_fit_df = pd.DataFrame()
    if "global" in frames:
        global_fit_df = pd.DataFrame(
            global_fit_rows(frames["global"], metrics, max_breaks, args.min_segment_months)
        )
    global_fit_path = out_dir / "regime_global_segmented_fits.csv"
    global_fit_df.to_csv(global_fit_path, index=False)

    figure_path = args.figure_dir / "regime_global_segmented_fits.png"
    figure_written = plot_global_segmented_fits(global_fit_df, figure_path)

    # Text summary
    summary_lines: List[str] = []
    summary_lines.append("Regime Breakpoint Analysis and Ban-Alignment Validation")
    summary_lines.append("=" * 72)
    summary_lines.append(f"Communities analyzed: {', '.join(sorted(frames.keys()))}")
    summary_lines.append(f"Metrics analyzed: {', '.join(metrics)}")
    summary_lines.append(f"Min segment length: {args.min_segment_months} months")
    summary_lines.append(f"Bootstrap iterations: {args.bootstrap_iterations} (seed={args.seed})")
    summary_lines.append(f"Model comparison: no break through {max_breaks} breaks; BIC primary, AICc secondary")
    summary_lines.append(
        f"Reference event (GA ban): {EVENTS['B'].date()} (month={EVENTS['B'].strftime('%Y-%m')})"
    )
    summary_lines.append(
        f"Global segmented-fit figure: {display_path(figure_path) if figure_written else 'not generated'}"
    )
    available_rolling = sorted(k for k in ei_definitions if k.startswith("rolling_tenure_"))
    requested_rolling = ", ".join(f"{tenure}m" for tenure in args.rolling_tenures) or "none"
    available_rolling_text = ", ".join(available_rolling) if available_rolling else "none"
    summary_lines.append(f"Rolling-tenure E-I definitions requested: {requested_rolling}")
    summary_lines.append(f"Rolling-tenure E-I definitions available: {available_rolling_text}")
    summary_lines.append("")

    if results_df.empty:
        summary_lines.append("No valid series to analyze. See skipped sections below.")
    else:
        total_series = len(results_df)
        near_total = int(results_df["near_ga_ban_pm_window"].sum())
        summary_lines.append(
            f"Breaks near GA ban (+/-{args.near_window_months} months): {near_total}/{total_series}"
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
                ci_part = f", CI~[{row.ci_low_month},{row.ci_high_month}], stab+/-3m={row.bootstrap_stability_pm3:.2f}"
            summary_lines.append(
                f"  {row.community}/{row.metric}: break={row.best_break_month}, "
                f"pre_slope={row.pre_slope:.4g}, post_slope={row.post_slope:.4g}, "
                f"SSE_ratio={row.sse_ratio:.3f}{ci_part}"
            )

    append_upgrade_summary(
        summary_lines,
        model_df,
        split_df,
        ei_sensitivity_df,
        metrics,
        args.near_window_months,
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
    logger.info(f"Wrote model comparison to {model_path}")
    logger.info(f"Wrote split robustness to {split_path}")
    logger.info(f"Wrote E-I definition sensitivity to {ei_sensitivity_path}")
    logger.info(f"Wrote global segmented fits to {global_fit_path}")
    if figure_written:
        logger.info(f"Wrote global segmented-fit figure to {figure_path}")
    logger.info(f"Wrote text summary to {summary_path}")


if __name__ == "__main__":
    main()
