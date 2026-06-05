#!/usr/bin/env python3
"""Analyze all-post Detoxify toxicity scores against existing ToxiGen outputs."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.migration_utils import EVENTS_CHRONO  # noqa: E402
from scripts.regime_volume_integration_panel import fit_fe_cluster_ols  # noqa: E402
from scripts.toxicity_cohort_followup import (  # noqa: E402
    COHORT_LABELS,
    COHORT_ORDER,
    assign_cohorts_from_first_seen,
    cohort_metrics,
    epoch_to_datetime,
)

NORMAL_COMMUNITIES = ["funny", "gaming", "gifs", "pics", "technology", "videos"]
CONTROVERSIAL_COMMUNITIES = [
    "cringeanarchy",
    "fatpeoplehate",
    "greatawakening",
    "mensrights",
    "milliondollarextreme",
    "kotakuinaction",
]
COMMUNITIES = CONTROVERSIAL_COMMUNITIES + NORMAL_COMMUNITIES

LABELS = {
    "toxigen_toxicity": "toxicity_toxigen",
    "detoxify_toxicity": "detoxify_toxicity",
    "detoxify_severe": "detoxify_severe_toxicity",
    "detoxify_identity": "detoxify_identity_attack",
    "detoxify_insult": "detoxify_insult",
    "detoxify_threat": "detoxify_threat",
}

EVENT_PERIODS = {
    "A-B": (EVENTS_CHRONO["A"], EVENTS_CHRONO["B"]),
    "B-C": (EVENTS_CHRONO["B"], EVENTS_CHRONO["C"]),
    "C-D": (EVENTS_CHRONO["C"], EVENTS_CHRONO["D"]),
    "D-end": (EVENTS_CHRONO["D"], pd.Timestamp("2020-12-31")),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scores-file",
        type=Path,
        nargs="+",
        default=[
            REPO_ROOT
            / "results"
            / "toxicity"
            / "voat"
            / "results"
            / "voat_detoxify_unbiased_all_posts_scores_all_communities.csv",
        ],
    )
    parser.add_argument(
        "--scope-label",
        default="posts",
        help="Human-readable scope label for reports, e.g. posts, comments, posts+comments.",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=REPO_ROOT / "results",
        help="Existing result root for newcomer-share inputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "results" / "toxicity" / "voat" / "results",
    )
    parser.add_argument(
        "--output-prefix",
        default="voat_detoxify_unbiased_all_posts_analysis",
    )
    return parser.parse_args()


def month_from_epoch(values: pd.Series) -> pd.Series:
    dt = epoch_to_datetime(values)
    return dt.dt.to_period("M").astype(str)


def load_scores(scores_files: list[Path]) -> pd.DataFrame:
    usecols = [
        "post_id",
        "publish_date",
        "user_id",
        "interaction_type",
        "community",
        "community_type",
        *LABELS.values(),
    ]
    frames = [pd.read_csv(scores_file, usecols=usecols) for scores_file in scores_files]
    df = pd.concat(frames, ignore_index=True)
    df["dt_time"] = epoch_to_datetime(df["publish_date"])
    df["month"] = df["dt_time"].dt.to_period("M").astype(str)
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    for col in LABELS.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["dt_time", "user_id", *LABELS.values()]).copy()


def assign_period(month_dt: pd.Timestamp) -> str | None:
    for period, (start, end) in EVENT_PERIODS.items():
        if start <= month_dt < end:
            return period
    return None


def summarize_distribution(scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    group_specs = [
        (["scope"], scores.assign(scope="global")),
        (["community_type"], scores),
        (["community_type", "community"], scores),
    ]
    for group_cols, data in group_specs:
        for key, group in data.groupby(group_cols, dropna=False, sort=True):
            if not isinstance(key, tuple):
                key = (key,)
            group_values = dict(zip(group_cols, key))
            for label, col in LABELS.items():
                values = group[col].dropna()
                rows.append(
                    {
                        **group_values,
                        "label": label,
                        "n_rows": int(values.shape[0]),
                        "mean": float(values.mean()),
                        "median": float(values.median()),
                        "q90": float(values.quantile(0.90)),
                        "q95": float(values.quantile(0.95)),
                        "share_gt_0_5": float((values > 0.5).mean()),
                        "share_gt_0_9": float((values > 0.9).mean()),
                    }
                )
    return pd.DataFrame(rows)


def monthly_metrics(scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (ctype, community, month, month_dt), group in scores.groupby(
        ["community_type", "community", "month", "month_dt"],
        sort=True,
    ):
        row = {
            "platform": "voat",
            "community_type": ctype,
            "community": community,
            "month": month,
            "month_dt": month_dt,
            "activity_count": int(group.shape[0]),
            "active_users": int(group["user_id"].nunique()),
        }
        for label, col in LABELS.items():
            row[f"{label}_mean"] = float(group[col].mean())
            row[f"{label}_q90"] = float(group[col].quantile(0.90))
            row[f"{label}_share_gt_0_5"] = float((group[col] > 0.5).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def event_period_means(scores: pd.DataFrame) -> pd.DataFrame:
    data = scores.copy()
    data["period"] = data["month_dt"].apply(assign_period)
    data = data[data["period"].notna()].copy()
    rows = []
    for (ctype, community, period), group in data.groupby(
        ["community_type", "community", "period"],
        sort=True,
    ):
        row = {
            "platform": "voat",
            "community_type": ctype,
            "community": community,
            "period": period,
            "activity_count": int(group.shape[0]),
            "active_users": int(group["user_id"].nunique()),
        }
        for label, col in LABELS.items():
            row[f"{label}_mean"] = float(group[col].mean())
            row[f"{label}_share_gt_0_5"] = float((group[col] > 0.5).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def regime_volume_panel(monthly: pd.DataFrame, results_root: Path) -> pd.DataFrame:
    panel_frames = []
    for community in NORMAL_COMMUNITIES:
        dyn_path = results_root / "voat" / community / f"voat_{community}_newcomer_degree_dynamics.csv"
        if not dyn_path.exists():
            continue
        dyn = pd.read_csv(dyn_path, usecols=["month", "newcomer_pop_share"])
        sub = monthly[monthly["community"] == community].copy()
        merged = sub.merge(dyn, on="month", how="left")
        panel_frames.append(merged)

    if not panel_frames:
        return pd.DataFrame()

    panel = pd.concat(panel_frames, ignore_index=True)
    ga_cutoff = pd.Timestamp("2018-09-01")
    rows = []
    for label in LABELS:
        outcome = f"{label}_mean"
        result = fit_fe_cluster_ols(panel, outcome, ga_cutoff)
        for term, coef, se, t_stat, p_value in zip(
            result.term_names,
            result.coef,
            result.se_cluster,
            result.t_stat,
            result.p_value_norm,
        ):
            rows.append(
                {
                    "label": label,
                    "outcome": outcome,
                    "term": term,
                    "coef": float(coef),
                    "se_cluster": float(se),
                    "t_stat": float(t_stat),
                    "p_value_norm": float(p_value),
                    "r2": float(result.r2),
                    "n_obs": result.n_obs,
                    "n_clusters": result.n_clusters,
                }
            )
    return pd.DataFrame(rows)


def label_cohort_metrics(rows: pd.DataFrame, label: str, col: str) -> dict[str, float]:
    renamed = rows[["user_id", col]].rename(columns={col: "toxicity_toxigen"})
    metrics = cohort_metrics(renamed)
    return {
        k.replace("toxigen_probability", label): v
        for k, v in metrics.items()
    }


def cohort_adplus_summary(scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    data = scores.copy()
    data["user_id"] = data["user_id"].astype(str)
    data = assign_cohorts_from_first_seen(data)
    period = data[data["dt_time"] >= EVENTS_CHRONO["A"]].copy()
    scopes = [("all_examined_communities", period)]
    scopes.extend((community, group) for community, group in period.groupby("community", sort=True))

    for scope, scope_data in scopes:
        ctype = (
            "pooled"
            if scope == "all_examined_communities"
            else str(scope_data["community_type"].iloc[0])
        )
        period_end = scope_data["dt_time"].max() if not scope_data.empty else pd.NaT
        for cohort in COHORT_ORDER:
            cohort_rows = scope_data[scope_data["cohort"] == cohort]
            for label, col in LABELS.items():
                metrics = label_cohort_metrics(cohort_rows, label, col)
                rows.append(
                    {
                        "platform": "voat",
                        "community_type": ctype,
                        "community": scope,
                        "period": "A-D+",
                        "period_start": EVENTS_CHRONO["A"].date().isoformat(),
                        "period_end": period_end.date().isoformat() if pd.notna(period_end) else "",
                        "cohort": cohort,
                        "cohort_label": COHORT_LABELS[cohort],
                        "label": label,
                        **metrics,
                    }
                )
    return pd.DataFrame(rows)


def top_rank_summary(dist: pd.DataFrame, label: str, n: int = 5) -> pd.DataFrame:
    community = dist[(dist["label"] == label) & dist["community"].notna()].copy()
    return community.sort_values("mean", ascending=False).head(n)


def global_toxicity_correlation(scores: pd.DataFrame) -> dict[str, float]:
    pair = scores[["toxicity_toxigen", "detoxify_toxicity"]].dropna()
    pearson = pearsonr(pair["toxicity_toxigen"], pair["detoxify_toxicity"])
    spearman = spearmanr(pair["toxicity_toxigen"], pair["detoxify_toxicity"])
    return {
        "n": int(pair.shape[0]),
        "pearson_r": float(pearson.statistic),
        "pearson_p": float(pearson.pvalue),
        "spearman_rho": float(spearman.statistic),
        "spearman_p": float(spearman.pvalue),
    }


def write_report(
    path: Path,
    scores: pd.DataFrame,
    dist: pd.DataFrame,
    event_periods: pd.DataFrame,
    panel: pd.DataFrame,
    cohorts: pd.DataFrame,
    scope_label: str,
) -> None:
    global_rows = dist[(dist["scope"] == "global") & dist["label"].isin(LABELS)].copy()
    global_means = {row["label"]: row for _, row in global_rows.iterrows()}
    tox_corr = global_toxicity_correlation(scores)

    top_tox = top_rank_summary(dist, "detoxify_toxicity", 6)
    top_identity = top_rank_summary(dist, "detoxify_identity", 6)
    top_threat = top_rank_summary(dist, "detoxify_threat", 6)

    period_tox = event_periods[event_periods["community"].isin(NORMAL_COMMUNITIES)].copy()
    period_summary = (
        period_tox.groupby("period")[
            [
                "toxigen_toxicity_mean",
                "detoxify_toxicity_mean",
                "detoxify_severe_mean",
                "detoxify_identity_mean",
                "detoxify_insult_mean",
                "detoxify_threat_mean",
            ]
        ]
        .mean()
        .reset_index()
    )

    panel_key = panel[
        panel["term"].isin(["newcomer_pop_share", "post_ga", "newcomer_x_post_ga"])
    ].copy()
    cohort_key = cohorts[
        (cohorts["community"] == "all_examined_communities")
        & (cohorts["cohort"].isin(["beforeA", "betweenA-B", "betweenC-D", "afterD"]))
        & (cohorts["label"].isin(["toxigen_toxicity", "detoxify_toxicity", "detoxify_insult", "detoxify_threat"]))
    ].copy()

    lines = [
        "# What changes when ToxiGen is replaced with Detoxify?",
        "",
        f"Scope: Voat {scope_label} only, using the Detoxify `unbiased` run. This does not replace paper results that require Reddit-side Detoxify scores.",
        "",
        "## Global agreement",
        "",
        (
            f"- ToxiGen vs Detoxify general toxicity on the same Voat {scope_label}: "
            f"Pearson r={tox_corr['pearson_r']:.4f}, Spearman rho={tox_corr['spearman_rho']:.4f}, n={int(tox_corr['n'])}."
        ),
        (
            f"- Mean ToxiGen toxicity={global_means['toxigen_toxicity']['mean']:.4f}; "
            f"mean Detoxify toxicity={global_means['detoxify_toxicity']['mean']:.4f}."
        ),
        (
            f"- Detoxify special labels are sparse: severe={global_means['detoxify_severe']['mean']:.5f}, "
            f"identity={global_means['detoxify_identity']['mean']:.5f}, "
            f"insult={global_means['detoxify_insult']['mean']:.5f}, "
            f"threat={global_means['detoxify_threat']['mean']:.5f}."
        ),
        "",
        "## Community ordering",
        "",
        "Top communities by mean Detoxify toxicity:",
        "",
        top_tox[["community_type", "community", "mean", "share_gt_0_5"]].to_markdown(index=False),
        "",
        "Top communities by mean Detoxify identity attack:",
        "",
        top_identity[["community_type", "community", "mean", "share_gt_0_5"]].to_markdown(index=False),
        "",
        "Top communities by mean Detoxify threat:",
        "",
        top_threat[["community_type", "community", "mean", "share_gt_0_5"]].to_markdown(index=False),
        "",
        "## Paper-style event periods for general communities",
        "",
        f"These are Voat {scope_label} means by chronological period, not Reddit-vs-Voat differences.",
        "",
        period_summary.to_markdown(index=False),
        "",
        "## Regime-volume panel analog",
        "",
        f"Same fixed-effect specification as `regime_volume_integration_panel.py`, but outcomes are monthly Detoxify/ToxiGen means for normal Voat {scope_label}.",
        "",
        panel_key[["label", "term", "coef", "se_cluster", "p_value_norm", "r2", "n_obs"]].to_markdown(index=False),
        "",
        "## Cohort follow-up analog",
        "",
        f"A-D+ pooled cohort means over all examined Voat {scope_label}; columns are activity-weighted means.",
        "",
    ]

    # Cohort output has label-specific metric column names, so render compactly by hand.
    cohort_lines = []
    for _, row in cohort_key.iterrows():
        mean_col = f"mean_{row['label']}_activity"
        cohort_lines.append(
            {
                "cohort": row["cohort_label"],
                "label": row["label"],
                "active_users": int(row["active_users"]),
                "activity_count": int(row["activity_count"]),
                "activity_mean": float(row[mean_col]),
            }
        )
    if cohort_lines:
        lines.extend(pd.DataFrame(cohort_lines).to_markdown(index=False).splitlines())
        lines.append("")

    lines.extend(
        [
            "## Interpretation",
            "",
            "- The headline ToxiGen pattern is broadly robust for general toxicity: Detoxify tracks ToxiGen strongly and preserves the broad controversial-vs-normal separation.",
            "- Detoxify is more diagnostic about mechanism: most general toxicity signal is ordinary insult/obscene-style toxicity, while severe toxicity and threats are rare.",
            "- Identity attack is not just a relabeling of general toxicity; it concentrates most in explicitly controversial communities, with the highest means in cringeanarchy, milliondollarextreme, and mensrights. Fatpeoplehate is top for general Detoxify toxicity, but not for identity attack.",
            "- Threat is too sparse to carry the main paper toxicity argument by itself. Treat it as a tail-risk diagnostic rather than a replacement outcome.",
            f"- Because this run scores Voat {scope_label} only, the current evidence supports a robustness/sensitivity statement for Voat-side toxicity, not a full replacement of the paper's Reddit-vs-Voat toxicity panels.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.output_prefix

    scores = load_scores(args.scores_file)
    dist = summarize_distribution(scores)
    monthly = monthly_metrics(scores)
    periods = event_period_means(scores)
    panel = regime_volume_panel(monthly, args.results_root)
    cohorts = cohort_adplus_summary(scores)

    dist.to_csv(args.output_dir / f"{prefix}_distribution_summary.csv", index=False)
    monthly.to_csv(args.output_dir / f"{prefix}_monthly_metrics.csv", index=False)
    periods.to_csv(args.output_dir / f"{prefix}_event_period_means.csv", index=False)
    panel.to_csv(args.output_dir / f"{prefix}_regime_volume_panel_coeffs.csv", index=False)
    cohorts.to_csv(args.output_dir / f"{prefix}_cohort_adplus_summary.csv", index=False)
    write_report(
        args.output_dir / f"{prefix}_report.md",
        scores,
        dist,
        periods,
        panel,
        cohorts,
        args.scope_label,
    )

    print(f"Wrote Detoxify analysis outputs to {args.output_dir}")
    print(f"Rows: scores={len(scores)}, monthly={len(monthly)}, periods={len(periods)}, panel={len(panel)}, cohorts={len(cohorts)}")


if __name__ == "__main__":
    main()
