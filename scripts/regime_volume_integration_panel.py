#!/usr/bin/env python3
"""
Package B: Panel regression for "volume vs integration" mechanism.

This script builds a monthly community panel for Voat generalist communities and
fits descriptive fixed‑effects models:

  (1) toxicity_mean ~ newcomer_pop_share + post_GA + newcomer_pop_share×post_GA
                      + linear time trend + community FE
  (2) ei_index       ~ newcomer_pop_share + post_GA + newcomer_pop_share×post_GA
                      + linear time trend + community FE

Standard errors are cluster‑robust by community (6 clusters).

Outputs (default to results/basic/compare/results):
  - regime_volume_panel_coeffs.csv
  - regime_volume_panel_summary.txt
"""

from __future__ import annotations

import argparse
import logging
import math
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Package B panel regression.")
    p.add_argument(
        "--communities",
        nargs="*",
        default=None,
        help="Communities to include (default: six generalist communities).",
    )
    p.add_argument(
        "--results-dir",
        type=Path,
        default=REPO_ROOT / "results",
        help="Base results directory.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "results" / "basic" / "compare" / "results",
        help="Directory for CSV and text summary outputs.",
    )
    p.add_argument(
        "--min-month",
        type=str,
        default=None,
        help="Optional earliest month to include (YYYY-MM).",
    )
    p.add_argument(
        "--max-month",
        type=str,
        default=None,
        help="Optional latest month to include (YYYY-MM).",
    )
    p.add_argument(
        "--ga-cutoff-month",
        type=str,
        default="2018-09",
        help="Month defining post-GA period (default 2018-09).",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def _load_first_existing(candidates: Iterable[Path]) -> Optional[pd.DataFrame]:
    for path in candidates:
        if path.exists():
            return pd.read_csv(path)
    return None


def load_community_panel(results_dir: Path, community: str) -> pd.DataFrame:
    """Load toxicity, E-I, and newcomer shares for one community."""
    community = community.lower()

    dyn_path = results_dir / "voat" / community / f"voat_{community}_newcomer_degree_dynamics.csv"
    part_path = results_dir / "voat" / community / f"{community}_newcomer_partition.csv"
    agg_path = results_dir / "voat" / community / f"voat_{community}_monthly_aggregates.csv"

    if not dyn_path.exists() or not agg_path.exists() or not part_path.exists():
        raise FileNotFoundError(
            f"Missing inputs for {community}: "
            f"dyn={dyn_path.exists()}, part={part_path.exists()}, agg={agg_path.exists()}"
        )

    dyn = pd.read_csv(dyn_path, usecols=["month", "newcomer_pop_share"])
    part = pd.read_csv(part_path, usecols=["month", "ei_index"])
    agg = pd.read_csv(agg_path, usecols=["month", "toxicity_mean"])

    df = agg.merge(dyn, on="month", how="left").merge(part, on="month", how="left")
    df["month"] = df["month"].astype(str)
    df["month_dt"] = pd.to_datetime(df["month"] + "-01", errors="coerce")
    df["community"] = community
    return df.sort_values("month_dt").reset_index(drop=True)


def normal_cdf(x: float) -> float:
    """Standard normal CDF using erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass
class OLSResult:
    term_names: List[str]
    coef: np.ndarray
    se_cluster: np.ndarray
    t_stat: np.ndarray
    p_value_norm: np.ndarray
    r2: float
    n_obs: int
    n_clusters: int


def fit_fe_cluster_ols(
    df: pd.DataFrame,
    outcome: str,
    ga_cutoff: pd.Timestamp,
    cluster_col: str = "community",
) -> OLSResult:
    """OLS with community fixed effects and cluster-robust SE."""
    work = df[["month_dt", cluster_col, outcome, "newcomer_pop_share"]].dropna()
    work = work.sort_values(["month_dt", cluster_col]).reset_index(drop=True)

    # Indicators / regressors
    work["post_ga"] = (work["month_dt"] >= ga_cutoff).astype(float)

    # Global time index (months since first observation in panel)
    month_num = work["month_dt"].dt.year * 12 + work["month_dt"].dt.month
    time0 = int(month_num.min())
    work["time_index"] = (month_num - time0).astype(float)

    # Fixed effects dummies
    clusters = sorted(work[cluster_col].unique().tolist())
    baseline = clusters[0]
    fe = pd.get_dummies(work[cluster_col], prefix="fe")
    fe = fe.drop(columns=[f"fe_{baseline}"], errors="ignore")

    main_terms = {
        "intercept": 1.0,
        "newcomer_pop_share": pd.to_numeric(work["newcomer_pop_share"], errors="coerce"),
        "post_ga": work["post_ga"],
        "newcomer_x_post_ga": work["newcomer_pop_share"] * work["post_ga"],
        "time_index": work["time_index"],
    }
    x_df = pd.DataFrame(main_terms).join(fe)
    x_df = x_df.fillna(0.0)

    y = pd.to_numeric(work[outcome], errors="coerce").to_numpy(dtype=float)
    X = x_df.to_numpy(dtype=float)

    # Coefficients
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    y_hat = X @ coef
    resid = y - y_hat

    # Cluster-robust variance
    XtX_inv = np.linalg.pinv(X.T @ X)
    meat = np.zeros((X.shape[1], X.shape[1]), dtype=float)
    for c in clusters:
        mask = (work[cluster_col] == c).to_numpy()
        Xg = X[mask]
        ug = resid[mask][:, None]
        meat += Xg.T @ (ug @ ug.T) @ Xg
    V = XtX_inv @ meat @ XtX_inv

    # Finite-sample correction (CR1)
    G = len(clusters)
    N = len(y)
    K = X.shape[1]
    if G > 1 and N > K + 1:
        V *= (G / (G - 1)) * ((N - 1) / (N - K))

    se = np.sqrt(np.maximum(np.diag(V), 0.0))
    t_stat = coef / se
    p_norm = 2.0 * (1.0 - np.array([normal_cdf(abs(t)) for t in t_stat]))

    # R2 (overall, descriptive)
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    return OLSResult(
        term_names=list(x_df.columns),
        coef=coef,
        se_cluster=se,
        t_stat=t_stat,
        p_value_norm=p_norm,
        r2=r2,
        n_obs=N,
        n_clusters=G,
    )


def summarize_model(result: OLSResult, title: str) -> List[str]:
    terms_show = [
        "newcomer_pop_share",
        "post_ga",
        "newcomer_x_post_ga",
        "time_index",
    ]
    idx = {t: i for i, t in enumerate(result.term_names)}
    lines: List[str] = [title]
    lines.append(f"  N={result.n_obs}, clusters={result.n_clusters}, R2={result.r2:.3f}")
    lines.append("  Coefficients (cluster-robust SE; normal-approx p):")
    for term in terms_show:
        if term not in idx:
            continue
        i = idx[term]
        lines.append(
            f"    {term}: {result.coef[i]: .4g} (SE {result.se_cluster[i]:.3g}), "
            f"t={result.t_stat[i]:.2f}, p≈{result.p_value_norm[i]:.3f}"
        )

    if "newcomer_pop_share" in idx and "newcomer_x_post_ga" in idx:
        b_pre = result.coef[idx["newcomer_pop_share"]]
        b_int = result.coef[idx["newcomer_x_post_ga"]]
        lines.append(
            f"  Implied newcomer effect pre‑GA: {b_pre:.4g}; post‑GA: {b_pre + b_int:.4g}"
        )
    return lines


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    communities = args.communities or DEFAULT_COMMUNITIES
    frames: List[pd.DataFrame] = []
    for comm in communities:
        frames.append(load_community_panel(args.results_dir, comm))

    panel = pd.concat(frames, ignore_index=True)

    if args.min_month:
        panel = panel[panel["month_dt"] >= pd.Timestamp(args.min_month + "-01")]
    if args.max_month:
        panel = panel[panel["month_dt"] <= pd.Timestamp(args.max_month + "-01")]

    ga_cutoff = pd.Timestamp(args.ga_cutoff_month + "-01")

    # Fit models
    tox_res = fit_fe_cluster_ols(panel, "toxicity_mean", ga_cutoff)
    ei_res = fit_fe_cluster_ols(panel, "ei_index", ga_cutoff)

    # Output directory
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Coefficient table
    def to_df(res: OLSResult, model_name: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "model": model_name,
                "term": res.term_names,
                "coef": res.coef,
                "se_cluster": res.se_cluster,
                "t_stat": res.t_stat,
                "p_value_norm": res.p_value_norm,
            }
        )

    coef_df = pd.concat(
        [to_df(tox_res, "toxicity_mean"), to_df(ei_res, "ei_index")],
        ignore_index=True,
    )
    coef_path = out_dir / "regime_volume_panel_coeffs.csv"
    coef_df.to_csv(coef_path, index=False)

    # Summary text
    summary_lines: List[str] = []
    summary_lines.append("Package B Panel Regression: Volume vs Integration")
    summary_lines.append("=" * 72)
    summary_lines.append(f"Communities: {', '.join(communities)}")
    summary_lines.append(
        f"Months included: {panel['month_dt'].min().strftime('%Y-%m')} to "
        f"{panel['month_dt'].max().strftime('%Y-%m')}"
    )
    summary_lines.append(f"GA cutoff month: {ga_cutoff.strftime('%Y-%m')} (EVENT B)")
    summary_lines.append(
        "Models are descriptive with community fixed effects and a linear time trend; "
        "they do not identify causal effects."
    )
    summary_lines.append("")

    summary_lines.extend(summarize_model(tox_res, "Model 1: toxicity_mean (Voat)"))
    summary_lines.append("")
    summary_lines.extend(summarize_model(ei_res, "Model 2: E-I index (Voat)"))

    # Simple descriptive stats
    pre = panel[panel["month_dt"] < ga_cutoff]
    post = panel[panel["month_dt"] >= ga_cutoff]
    if not pre.empty and not post.empty:
        summary_lines.append("")
        summary_lines.append("Descriptive means (unweighted across communities):")
        for col in ["newcomer_pop_share", "toxicity_mean", "ei_index"]:
            if col in panel.columns:
                pre_mean = float(pd.to_numeric(pre[col], errors="coerce").mean())
                post_mean = float(pd.to_numeric(post[col], errors="coerce").mean())
                summary_lines.append(f"  {col}: pre‑GA={pre_mean:.4g}, post‑GA={post_mean:.4g}")

    summary_path = out_dir / "regime_volume_panel_summary.txt"
    summary_path.write_text("\n".join(summary_lines))

    logger.info(f"Wrote coefficients to {coef_path}")
    logger.info(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()

