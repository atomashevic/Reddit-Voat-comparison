#!/usr/bin/env python3
"""Build a LaTeX lab report for Voat-side Detoxify/ToxiGen comparison."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

REPO_ROOT = Path(__file__).resolve().parents[1]

RESULTS_DIR = REPO_ROOT / "results" / "toxicity" / "voat" / "results"
REPORT_DIR = REPO_ROOT / "results" / "toxicity" / "voat" / "report"

COMMUNITIES = [
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

NORMAL_COMMUNITIES = ["funny", "gaming", "gifs", "pics", "technology", "videos"]

LABELS = {
    "ToxiGen": "toxicity_toxigen",
    "Detoxify toxicity": "detoxify_toxicity",
    "Severe": "detoxify_severe_toxicity",
    "Identity": "detoxify_identity_attack",
    "Insult": "detoxify_insult",
    "Threat": "detoxify_threat",
}

SHORT_LABELS = {
    "toxigen_toxicity": "ToxiGen",
    "detoxify_toxicity": "Detoxify",
    "detoxify_severe": "Severe",
    "detoxify_identity": "Identity",
    "detoxify_insult": "Insult",
    "detoxify_threat": "Threat",
}

COLORS = {
    "post": "#4C78A8",
    "comment": "#F58518",
    "posts+comments": "#54A24B",
    "controversial": "#B279A2",
    "normal": "#59A14F",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--compile", action="store_true", help="Compile the LaTeX report with latexmk or pdflatex.")
    return parser.parse_args()


def ensure_dirs(report_dir: Path) -> tuple[Path, Path]:
    fig_dir = report_dir / "figures"
    table_dir = report_dir / "tables"
    fig_dir.mkdir(parents=True, exist_ok=True)
    table_dir.mkdir(parents=True, exist_ok=True)
    return fig_dir, table_dir


def read_scores(results_dir: Path, stem: str) -> pd.DataFrame:
    path = results_dir / f"voat_detoxify_unbiased_all_{stem}_scores_all_communities.csv"
    usecols = [
        "post_id",
        "publish_date",
        "user_id",
        "interaction_type",
        "community",
        "community_type",
        "toxicity_toxigen",
        "detoxify_toxicity",
        "detoxify_severe_toxicity",
        "detoxify_identity_attack",
        "detoxify_insult",
        "detoxify_threat",
    ]
    df = pd.read_csv(path, usecols=usecols)
    df["scope"] = stem[:-1] if stem.endswith("s") else stem
    return df


def read_analysis(results_dir: Path, stem: str) -> dict[str, pd.DataFrame]:
    prefix = f"voat_detoxify_unbiased_all_{stem}_analysis"
    return {
        "dist": pd.read_csv(results_dir / f"{prefix}_distribution_summary.csv"),
        "monthly": pd.read_csv(results_dir / f"{prefix}_monthly_metrics.csv"),
        "periods": pd.read_csv(results_dir / f"{prefix}_event_period_means.csv"),
        "panel": pd.read_csv(results_dir / f"{prefix}_regime_volume_panel_coeffs.csv"),
        "cohort": pd.read_csv(results_dir / f"{prefix}_cohort_adplus_summary.csv"),
    }


def fmt_num(value: float, digits: int = 3) -> str:
    if pd.isna(value):
        return "--"
    if abs(value) < 0.001 and value != 0:
        return f"{value:.2e}"
    return f"{value:.{digits}f}"


def escape_latex(text: object) -> str:
    out = str(text)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for key, value in replacements.items():
        out = out.replace(key, value)
    return out


def latex_table(
    df: pd.DataFrame,
    caption: str,
    label: str,
    align: str | None = None,
    fit_width: bool = False,
) -> str:
    align = align or ("l" * len(df.columns))
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\scriptsize" if fit_width else r"\small",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
    ]
    if fit_width:
        lines.append(r"\resizebox{\textwidth}{!}{%")
    lines.extend([
        rf"\begin{{tabular}}{{{align}}}",
        r"\toprule",
        " & ".join(escape_latex(c) for c in df.columns) + r" \\",
        r"\midrule",
    ])
    for _, row in df.iterrows():
        lines.append(" & ".join(escape_latex(v) for v in row.tolist()) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    if fit_width:
        lines.append(r"}")
    lines.extend([r"\end{table}", ""])
    return "\n".join(lines)


def global_summary_tables(analyses: dict[str, dict[str, pd.DataFrame]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    corr_rows = []
    for scope, parts in analyses.items():
        dist = parts["dist"]
        glob = dist[dist["scope"] == "global"].set_index("label")
        rows.append(
            {
                "Scope": scope,
                "N": int(glob.loc["toxigen_toxicity", "n_rows"]),
                "ToxiGen mean": fmt_num(glob.loc["toxigen_toxicity", "mean"], 4),
                "Detoxify mean": fmt_num(glob.loc["detoxify_toxicity", "mean"], 4),
                "Severe mean": fmt_num(glob.loc["detoxify_severe", "mean"], 5),
                "Identity mean": fmt_num(glob.loc["detoxify_identity", "mean"], 5),
                "Insult mean": fmt_num(glob.loc["detoxify_insult", "mean"], 5),
                "Threat mean": fmt_num(glob.loc["detoxify_threat", "mean"], 5),
                "Detoxify > .5": fmt_num(glob.loc["detoxify_toxicity", "share_gt_0_5"], 4),
            }
        )
        corr_path = RESULTS_DIR / f"voat_detoxify_unbiased_all_{'activity' if scope == 'posts+comments' else scope + 's'}_correlations_global.csv"
        if corr_path.exists():
            corr = pd.read_csv(corr_path)
            tox = corr[corr["detoxify_col"] == "detoxify_toxicity"].iloc[0]
            pear = tox["pearson_r"]
            spear = tox["spearman_rho"]
        else:
            scores = parts["scores"]
            pear = pearsonr(scores["toxicity_toxigen"], scores["detoxify_toxicity"]).statistic
            spear = spearmanr(scores["toxicity_toxigen"], scores["detoxify_toxicity"]).statistic
        corr_rows.append(
            {
                "Scope": scope,
                "N": rows[-1]["N"],
                "Pearson r": fmt_num(float(pear), 4),
                "Spearman rho": fmt_num(float(spear), 4),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(corr_rows)


def build_activity_analysis(scores: pd.DataFrame) -> dict[str, pd.DataFrame]:
    rows = []
    for (interaction, ctype, community), group in scores.groupby(
        ["interaction_type", "community_type", "community"], sort=True
    ):
        row = {
            "interaction_type": interaction,
            "community_type": ctype,
            "community": community,
            "n_rows": int(group.shape[0]),
        }
        for name, col in LABELS.items():
            row[f"{name}_mean"] = float(group[col].mean())
        rows.append(row)
    return {"community_interaction": pd.DataFrame(rows)}


def create_figures(
    analyses: dict[str, dict[str, pd.DataFrame]],
    scores: pd.DataFrame,
    fig_dir: Path,
) -> None:
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 160,
    })

    # Figure 1: calibration density.
    fig, ax = plt.subplots(figsize=(4.8, 4.1))
    sample = scores[["toxicity_toxigen", "detoxify_toxicity"]].dropna()
    hb = ax.hexbin(
        sample["toxicity_toxigen"],
        sample["detoxify_toxicity"],
        gridsize=55,
        mincnt=1,
        bins="log",
        cmap="Greys",
    )
    ax.plot([0, 1], [0, 1], color="black", lw=0.8, ls="--")
    ax.set_xlabel("ToxiGen toxicity")
    ax.set_ylabel("Detoxify toxicity")
    ax.set_title("Same-message calibration, Voat posts and comments")
    cb = fig.colorbar(hb, ax=ax)
    cb.set_label("log10(count)")
    fig.tight_layout()
    fig.savefig(fig_dir / "fig01_toxigen_detoxify_hexbin.pdf")
    plt.close(fig)

    # Figure 2: global means by scope.
    scopes = ["post", "comment", "posts+comments"]
    x = np.arange(len(scopes))
    width = 0.13
    labels = [
        ("ToxiGen", "toxigen_toxicity"),
        ("Detoxify", "detoxify_toxicity"),
        ("Identity", "detoxify_identity"),
        ("Insult", "detoxify_insult"),
        ("Threat", "detoxify_threat"),
    ]
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    for i, (display, key) in enumerate(labels):
        means = []
        for scope in scopes:
            dist = analyses[scope]["dist"]
            means.append(float(dist[(dist["scope"] == "global") & (dist["label"] == key)]["mean"].iloc[0]))
        ax.bar(x + (i - 2) * width, means, width, label=display)
    ax.set_xticks(x)
    ax.set_xticklabels(["Posts", "Comments", "Posts+comments"])
    ax.set_ylabel("Mean score")
    ax.set_title("Global Voat toxicity means by detector and message type")
    ax.legend(ncol=3, frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig02_global_means_by_scope.pdf")
    plt.close(fig)

    # Figure 3: community means for general toxicity, posts and comments.
    ci = analyses["posts+comments"]["activity"]["community_interaction"].copy()
    order = (
        ci.groupby("community")["Detoxify toxicity_mean"]
        .mean()
        .sort_values()
        .index.tolist()
    )
    fig, ax = plt.subplots(figsize=(7.3, 5.0))
    y = np.arange(len(order))
    for offset, interaction in [(-0.18, "post"), (0.18, "comment")]:
        vals = (
            ci[ci["interaction_type"] == interaction]
            .set_index("community")
            .loc[order]["Detoxify toxicity_mean"]
        )
        ax.barh(y + offset, vals, height=0.32, label=interaction.title(), color=COLORS[interaction])
    ax.set_yticks(y)
    ax.set_yticklabels(order)
    ax.set_xlabel("Mean Detoxify toxicity")
    ax.set_title("Community ordering under Detoxify general toxicity")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig03_community_detoxify_general.pdf")
    plt.close(fig)

    # Figure 4: special-label heatmap for total activity.
    dist = analyses["posts+comments"]["dist"]
    heat = dist[(dist["community"].notna()) & dist["label"].isin([
        "detoxify_severe",
        "detoxify_identity",
        "detoxify_insult",
        "detoxify_threat",
    ])].pivot(index="community", columns="label", values="mean")
    heat = heat.loc[order[::-1]]
    fig, ax = plt.subplots(figsize=(5.8, 5.5))
    im = ax.imshow(heat.values, aspect="auto", cmap="magma")
    ax.set_yticks(np.arange(len(heat.index)))
    ax.set_yticklabels(heat.index)
    ax.set_xticks(np.arange(len(heat.columns)))
    ax.set_xticklabels([SHORT_LABELS[c] for c in heat.columns], rotation=30, ha="right")
    for i in range(heat.shape[0]):
        for j in range(heat.shape[1]):
            ax.text(j, i, fmt_num(float(heat.values[i, j]), 3), ha="center", va="center", color="white", fontsize=6)
    ax.set_title("Detoxify special-label means, posts and comments")
    cb = fig.colorbar(im, ax=ax, fraction=0.046)
    cb.set_label("Mean score")
    fig.tight_layout()
    fig.savefig(fig_dir / "fig04_special_label_heatmap.pdf")
    plt.close(fig)

    # Figure 5: event period trajectories in normal communities.
    periods = analyses["posts+comments"]["periods"]
    period_summary = (
        periods[periods["community"].isin(NORMAL_COMMUNITIES)]
        .groupby("period")[
            [
                "toxigen_toxicity_mean",
                "detoxify_toxicity_mean",
                "detoxify_identity_mean",
                "detoxify_insult_mean",
                "detoxify_threat_mean",
            ]
        ]
        .mean()
        .reindex(["A-B", "B-C", "C-D", "D-end"])
    )
    fig, ax = plt.subplots(figsize=(6.7, 4.2))
    for col, label in [
        ("toxigen_toxicity_mean", "ToxiGen"),
        ("detoxify_toxicity_mean", "Detoxify"),
        ("detoxify_insult_mean", "Insult"),
        ("detoxify_identity_mean", "Identity"),
        ("detoxify_threat_mean", "Threat"),
    ]:
        ax.plot(period_summary.index, period_summary[col], marker="o", lw=1.5, label=label)
    ax.set_ylabel("Mean score")
    ax.set_xlabel("Chronological period")
    ax.set_title("Normal-community Voat toxicity by event period")
    ax.legend(frameon=False, ncol=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig05_event_period_trajectories.pdf")
    plt.close(fig)

    # Figure 6: cohort means.
    cohort = analyses["posts+comments"]["cohort"]
    key = cohort[
        (cohort["community"] == "all_examined_communities")
        & (cohort["label"].isin(["toxigen_toxicity", "detoxify_toxicity", "detoxify_insult", "detoxify_threat"]))
    ].copy()
    rows = []
    for _, row in key.iterrows():
        rows.append(
            {
                "cohort": row["cohort_label"],
                "label": SHORT_LABELS[row["label"]],
                "mean": row[f"mean_{row['label']}_activity"],
            }
        )
    cohort_plot = pd.DataFrame(rows)
    cohort_order = ["Before A", "A-B", "B-C", "C-D", "D+"]
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    x = np.arange(len(cohort_order))
    bar_w = 0.18
    plot_labels = ["ToxiGen", "Detoxify", "Insult", "Threat"]
    for i, label in enumerate(plot_labels):
        vals = (
            cohort_plot[cohort_plot["label"] == label]
            .set_index("cohort")
            .reindex(cohort_order)["mean"]
            .to_numpy()
        )
        ax.bar(x + (i - 1.5) * bar_w, vals, bar_w, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels(cohort_order)
    ax.set_ylabel("Activity-weighted mean")
    ax.set_title("Pooled A-D+ cohort means, posts and comments")
    ax.legend(frameon=False, ncol=4, fontsize=8)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig06_cohort_means.pdf")
    plt.close(fig)


def write_tables(
    analyses: dict[str, dict[str, pd.DataFrame]],
    table_dir: Path,
) -> dict[str, str]:
    tables: dict[str, str] = {}
    global_df, corr_df = global_summary_tables(analyses)
    tables["global"] = latex_table(
        global_df,
        "Global Voat-side toxicity means by message scope. The rows compare the older ToxiGen score to Detoxify's general and diagnostic outputs on identical Voat messages.",
        "tab:global-means",
        "lrrrrrrrr",
        fit_width=True,
    )
    tables["corr"] = latex_table(
        corr_df,
        "Same-message association between ToxiGen toxicity and Detoxify general toxicity.",
        "tab:calibration",
        "lrrr",
    )

    dist = analyses["posts+comments"]["dist"]
    community = dist[(dist["community"].notna()) & (dist["label"].isin(["toxigen_toxicity", "detoxify_toxicity", "detoxify_identity", "detoxify_insult", "detoxify_threat"]))].copy()
    pivot = community.pivot(index=["community_type", "community"], columns="label", values="mean").reset_index()
    pivot = pivot.sort_values("detoxify_toxicity", ascending=False)
    table = pd.DataFrame({
        "Type": pivot["community_type"],
        "Community": pivot["community"],
        "ToxiGen": pivot["toxigen_toxicity"].map(lambda x: fmt_num(x, 3)),
        "Detoxify": pivot["detoxify_toxicity"].map(lambda x: fmt_num(x, 3)),
        "Identity": pivot["detoxify_identity"].map(lambda x: fmt_num(x, 3)),
        "Insult": pivot["detoxify_insult"].map(lambda x: fmt_num(x, 3)),
        "Threat": pivot["detoxify_threat"].map(lambda x: fmt_num(x, 3)),
    })
    tables["community"] = latex_table(
        table,
        "Community-level mean scores for all Voat posts and comments, sorted by Detoxify general toxicity.",
        "tab:community-means",
        "llrrrrr",
        fit_width=True,
    )

    periods = analyses["posts+comments"]["periods"]
    period_summary = (
        periods[periods["community"].isin(NORMAL_COMMUNITIES)]
        .groupby("period")[
            [
                "toxigen_toxicity_mean",
                "detoxify_toxicity_mean",
                "detoxify_identity_mean",
                "detoxify_insult_mean",
                "detoxify_threat_mean",
            ]
        ]
        .mean()
        .reindex(["A-B", "B-C", "C-D", "D-end"])
        .reset_index()
    )
    table = pd.DataFrame({
        "Period": period_summary["period"],
        "ToxiGen": period_summary["toxigen_toxicity_mean"].map(lambda x: fmt_num(x, 3)),
        "Detoxify": period_summary["detoxify_toxicity_mean"].map(lambda x: fmt_num(x, 3)),
        "Identity": period_summary["detoxify_identity_mean"].map(lambda x: fmt_num(x, 3)),
        "Insult": period_summary["detoxify_insult_mean"].map(lambda x: fmt_num(x, 3)),
        "Threat": period_summary["detoxify_threat_mean"].map(lambda x: fmt_num(x, 3)),
    })
    tables["period"] = latex_table(
        table,
        "Paper-style chronological period means for the six normal Voat communities, using all posts and comments.",
        "tab:period-means",
        "lrrrrr",
    )

    panel = analyses["posts+comments"]["panel"]
    panel_key = panel[panel["term"].isin(["newcomer_pop_share", "post_ga", "newcomer_x_post_ga"])].copy()
    table = pd.DataFrame({
        "Outcome": panel_key["label"].map(SHORT_LABELS),
        "Term": panel_key["term"],
        "Coef.": panel_key["coef"].map(lambda x: fmt_num(x, 4)),
        "SE": panel_key["se_cluster"].map(lambda x: fmt_num(x, 4)),
        "p": panel_key["p_value_norm"].map(lambda x: fmt_num(x, 3)),
        "$R^2$": panel_key["r2"].map(lambda x: fmt_num(x, 3)),
    })
    tables["panel"] = latex_table(
        table,
        "Regime-volume fixed-effect analog for normal Voat communities, replacing the ToxiGen outcome with Detoxify outcomes.",
        "tab:panel",
        "llrrrr",
        fit_width=True,
    )

    cohort = analyses["posts+comments"]["cohort"]
    key = cohort[
        (cohort["community"] == "all_examined_communities")
        & (cohort["label"].isin(["toxigen_toxicity", "detoxify_toxicity", "detoxify_identity", "detoxify_insult", "detoxify_threat"]))
    ].copy()
    rows = []
    for _, row in key.iterrows():
        rows.append({
            "Cohort": row["cohort_label"],
            "Outcome": SHORT_LABELS[row["label"]],
            "Users": int(row["active_users"]),
            "Activities": int(row["activity_count"]),
            "Mean": fmt_num(row[f"mean_{row['label']}_activity"], 4),
        })
    tables["cohort"] = latex_table(
        pd.DataFrame(rows),
        "Pooled A-D+ cohort means for all examined Voat communities; means are activity-weighted over posts and comments.",
        "tab:cohort",
        "llrrr",
        fit_width=True,
    )

    for name, content in tables.items():
        (table_dir / f"{name}.tex").write_text(content)
    return tables


def manuscript_text(analyses: dict[str, dict[str, pd.DataFrame]]) -> str:
    global_df, corr_df = global_summary_tables(analyses)
    glob = global_df.set_index("Scope")
    corr = corr_df.set_index("Scope")
    total_n = glob.loc["posts+comments", "N"]
    post_n = glob.loc["post", "N"]
    comment_n = glob.loc["comment", "N"]
    total_n_fmt = f"{int(total_n):,}"
    post_n_fmt = f"{int(post_n):,}"
    comment_n_fmt = f"{int(comment_n):,}"
    total_detox = glob.loc["posts+comments", "Detoxify mean"]
    comment_detox = glob.loc["comment", "Detoxify mean"]
    post_detox = glob.loc["post", "Detoxify mean"]
    total_r = corr.loc["posts+comments", "Pearson r"]
    total_rho = corr.loc["posts+comments", "Spearman rho"]

    return rf"""\documentclass[11pt,letterpaper]{{article}}
\usepackage[T1]{{fontenc}}
\usepackage[utf8]{{inputenc}}
\usepackage{{lmodern}}
\usepackage[margin=1in]{{geometry}}
\usepackage{{setspace}}
\usepackage{{microtype}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{longtable}}
\usepackage{{caption}}
\usepackage{{subcaption}}
\usepackage{{float}}
\usepackage{{fancyhdr}}
\usepackage{{hyperref}}
\hypersetup{{colorlinks=true, linkcolor=black, citecolor=black, urlcolor=black}}
\newcommand{{\cref}}[1]{{\ref{{#1}}}}
\onehalfspacing
\pagestyle{{fancy}}
\fancyhf{{}}
\setlength{{\headheight}}{{14pt}}
\emergencystretch=2em
\lhead{{Voat toxicity calibration}}
\rhead{{Detoxify--ToxiGen comparison}}
\cfoot{{\thepage}}

\title{{A Voat-Side Calibration Report on Detoxify and ToxiGen Toxicity Scores}}
\author{{Computational Social Dynamics Laboratory}}
\date{{2 June 2026}}

\begin{{document}}
\maketitle

\begin{{abstract}}
This report records a Voat-side sensitivity analysis of the manuscript toxicity results after re-scoring the examined Voat communities with Detoxify.  The analysis covers {total_n_fmt} eligible Voat messages: {post_n_fmt} submissions and {comment_n_fmt} comments from the twelve investigated communities.  Detoxify's general toxicity score agrees strongly with the older ToxiGen score on the same messages (Pearson $r={total_r}$; Spearman $\rho={total_rho}$), but it also separates the broad toxicity signal into severe toxicity, identity attack, insult, and threat.  The principal conclusion is conservative: the older ToxiGen findings are not overturned on the Voat side.  They are sharpened.  Comments are more toxic than submissions; the broad signal is largely insult-like rather than severe or threatening; identity attack is concentrated but not identical to the general toxicity ordering; and threat is too sparse to support the main narrative by itself.
\end{{abstract}}

\section{{Purpose and Scope}}
The paper and subsequent revision analyses used ToxiGen-derived toxicity as the operational measure of toxic expression.  The present report asks whether the Voat-side conclusions change when the same corpus is evaluated by Detoxify's \texttt{{unbiased}} RoBERTa model.  It is written as a calibration memorandum rather than a replacement manuscript.  Its evidentiary domain is deliberately narrow: Voat submissions and comments in the twelve examined communities, scored on the same message rows that carry the older ToxiGen score.  Reddit-side Detoxify scores have not yet been generated, so the original Reddit--Voat heatmap and any strict cross-platform statements remain ToxiGen-based until the Reddit side is also rescored.

The report has three comparisons.  First, it compares ToxiGen toxicity with Detoxify general toxicity on identical Voat messages.  Second, it decomposes the Detoxify signal into severe toxicity, identity attack, insult, and threat.  Third, it repeats the Voat-side forms of the paper and revision analyses: event-period summaries for the normal communities, the regime-volume panel analog, and the A--D+ cohort follow-up.

\section{{Materials}}
The corpus consists of all eligible Voat rows from the communities CringeAnarchy, fatpeoplehate, GreatAwakening, MensRights, milliondollarextreme, KotakuInAction, funny, gaming, gifs, pics, technology, and videos.  Eligibility required an interaction type of submission or comment, non-empty content, and a non-missing ToxiGen score.  The scoring files were produced by \texttt{{scripts/compare\_detoxify\_toxigen\_sample.py}} using \texttt{{Detoxify('unbiased', device='cuda')}}.  The submission run and the comment run both report \texttt{{cuda:0}} on an NVIDIA A30.  The analytic tables were produced by \texttt{{scripts/analyze\_detoxify\_toxicity\_results.py}} and the present report by \texttt{{scripts/build\_detoxify\_lab\_report.py}}.

\input{{tables/global.tex}}
\input{{tables/corr.tex}}

\section{{Calibration of the General Toxicity Score}}
The general Detoxify score is not a foreign measurement of the corpus.  It is strongly associated with ToxiGen on the same messages, with the total Voat-side association shown in \cref{{tab:calibration}} and \cref{{fig:calibration}}.  Detoxify is, however, lower in mean level: for all posts and comments together the mean Detoxify toxicity is {total_detox}, compared with the higher ToxiGen mean shown in \cref{{tab:global-means}}.  The difference is not a contradiction.  It indicates a change of scale and thresholding behavior, not a reversal of rank structure.

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=0.72\textwidth]{{figures/fig01_toxigen_detoxify_hexbin.pdf}}
  \caption{{Message-level association between the older ToxiGen toxicity score and Detoxify general toxicity for Voat posts and comments.  The dashed line is equality.}}
  \label{{fig:calibration}}
\end{{figure}}

Comments carry much of the corpus-level toxic expression.  The mean Detoxify toxicity is {post_detox} for submissions and {comment_detox} for comments.  This difference matters for interpreting the earlier post-only Detoxify check: it was a useful first calibration but it understated the total Voat-side level because the comment stream is both larger and more toxic.

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=0.82\textwidth]{{figures/fig02_global_means_by_scope.pdf}}
  \caption{{Global mean scores for submissions, comments, and the combined Voat-side corpus.  Detoxify's diagnostic labels show that severe toxicity and threat are rare compared with general toxicity and insult.}}
  \label{{fig:globalmeans}}
\end{{figure}}

\section{{Community Ordering and Diagnostic Content}}
The community ordering under Detoxify general toxicity is consistent with the manuscript's substantive use of toxicity: controversial communities are generally higher, and fatpeoplehate remains the most toxic large community by the general Detoxify score.  Yet the diagnostic labels prevent an over-simple reading.  Identity attack does not merely reproduce the general-toxicity ranking, and threat is sparse across all communities.

\input{{tables/community.tex}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=0.86\textwidth]{{figures/fig03_community_detoxify_general.pdf}}
  \caption{{Mean Detoxify general toxicity by community and interaction type.  Comments are usually higher than submissions, making the total Voat-side comparison more severe than the post-only comparison.}}
  \label{{fig:communitygeneral}}
\end{{figure}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=0.78\textwidth]{{figures/fig04_special_label_heatmap.pdf}}
  \caption{{Mean Detoxify special-label scores for all Voat posts and comments.  Insult is the largest diagnostic component; severe toxicity and threat remain tail phenomena.}}
  \label{{fig:specialheat}}
\end{{figure}}

\section{{Relation to the Paper Results}}
The paper's global figure uses ToxiGen to compare Reddit and Voat toxicity by event period.  Detoxify cannot yet replace that full panel because Reddit has not been rescored.  It can, however, test whether the Voat side of the finding is fragile.  It is not.  In the six normal communities, the combined Voat-side Detoxify means rise across the chronological event periods, matching the direction of the ToxiGen summaries in \cref{{tab:period-means}} and \cref{{fig:periods}}.  The diagnostic labels show that the increase is not driven by threats or severe toxicity.  It is primarily broad toxicity and insult, with identity attack rising as a smaller but visible component.

\input{{tables/period.tex}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=0.82\textwidth]{{figures/fig05_event_period_trajectories.pdf}}
  \caption{{Chronological event-period means for the six normal Voat communities, using posts and comments together.  These are Voat-side means, not Reddit--Voat differences.}}
  \label{{fig:periods}}
\end{{figure}}

\section{{Relation to the Revision Analyses}}
The revision analyses added mechanism checks around volume, integration, and cohort composition.  The Detoxify analog of the regime-volume panel does not produce a strong newcomer-share interaction for general Detoxify toxicity or for severe, identity, insult, or threat.  This is consistent with a cautious interpretation: Detoxify supports the presence and ordering of Voat-side toxicity, but it does not turn the volume-integration model into a strong causal mechanism.

\input{{tables/panel.tex}}

The cohort follow-up is more informative descriptively.  The pooled A--D+ cohort table shows the same broad pattern under ToxiGen and Detoxify general toxicity, while again showing that threat is extremely small.  This supports the revision's restrained language: cohort structure is relevant to observed toxicity, but the toxic signal is mostly ordinary hostile or insulting language rather than explicit threat.

\input{{tables/cohort.tex}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=0.82\textwidth]{{figures/fig06_cohort_means.pdf}}
  \caption{{Pooled A--D+ cohort means over all examined Voat communities, using activity-weighted means for posts and comments.}}
  \label{{fig:cohorts}}
\end{{figure}}

\section{{Interpretive Conclusions}}
Four conclusions follow.  First, Detoxify validates the older Voat-side ToxiGen signal at the level required for a robustness check: the two scores are strongly associated and preserve the major substantive ordering.  Second, comments must be included for a total Voat-side comparison.  They are more numerous and more toxic than submissions, so a submission-only Detoxify check is conservative with respect to the total Voat-side level.  Third, Detoxify sharpens the interpretation of toxicity.  The signal is dominated by broad toxicity and insult; identity attack is meaningful but differently distributed; severe toxicity and threat are rare.  Fourth, the paper should not claim that Detoxify independently reproduces the full Reddit--Voat comparison until Reddit is scored.  The correct statement is narrower and stronger: on the Voat side, including comments, the manuscript's ToxiGen-based toxicity conclusions are robust in direction and community ordering, while Detoxify shows that the mechanism is chiefly insultive and hostile expression rather than severe threat.

\section{{Records and Reproducibility}}
The principal generated files are:
\begin{{itemize}}
  \item \path{{results/toxicity/voat/results/voat_detoxify_unbiased_all_posts_scores_all_communities.csv}}
  \item \path{{results/toxicity/voat/results/voat_detoxify_unbiased_all_comments_scores_all_communities.csv}}
  \item \path{{results/toxicity/voat/results/voat_detoxify_unbiased_all_activity_analysis_*.csv}}
  \item \path{{results/toxicity/voat/report/detoxify_voat_lab_report.tex}}
\end{{itemize}}
All counts in this report are derived from those files.  The total analyzed Voat-side corpus contains {total_n_fmt} scored messages.

\end{{document}}
"""


def compile_report(report_dir: Path, tex_name: str) -> None:
    latexmk = subprocess.run(["which", "latexmk"], capture_output=True, text=True)
    if latexmk.returncode == 0:
        subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", tex_name], cwd=report_dir, check=True)
        return
    for _ in range(2):
        subprocess.run(["pdflatex", "-interaction=nonstopmode", tex_name], cwd=report_dir, check=True)


def main() -> None:
    args = parse_args()
    fig_dir, table_dir = ensure_dirs(args.report_dir)

    analyses = {
        "post": read_analysis(args.results_dir, "posts"),
        "comment": read_analysis(args.results_dir, "comments"),
        "posts+comments": read_analysis(args.results_dir, "activity"),
    }
    post_scores = read_scores(args.results_dir, "posts")
    comment_scores = read_scores(args.results_dir, "comments")
    scores = pd.concat([post_scores, comment_scores], ignore_index=True)
    analyses["posts+comments"]["scores"] = scores
    analyses["posts+comments"]["activity"] = build_activity_analysis(scores)
    analyses["post"]["scores"] = post_scores
    analyses["comment"]["scores"] = comment_scores

    create_figures(analyses, scores, fig_dir)
    write_tables(analyses, table_dir)

    tex_name = "detoxify_voat_lab_report.tex"
    tex_path = args.report_dir / tex_name
    tex_path.write_text(manuscript_text(analyses))
    if args.compile:
        compile_report(args.report_dir, tex_name)
    print(f"Wrote {tex_path}")
    print(f"Figures: {fig_dir}")
    print(f"Tables: {table_dir}")


if __name__ == "__main__":
    main()
