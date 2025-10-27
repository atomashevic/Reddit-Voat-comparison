#!/usr/bin/env python3
"""Voat community post→comment convergence-entropy time series.

For a single Voat community, samples 25% of threads in each month (minimum one
thread), computes per-token convergence entropy between the root post and
first-level comments, aggregates by core/periphery pair type, and emits panel
plots plus summary tables. Outputs land beneath ``<outdir>/results`` and
``<outdir>/figures``.

Example::

    python scripts/voat_entropy_timeseries.py \
        --community funny \
        --parquet data/voat_funny_madoc.parquet \
        --cp-labels results/core-periphery/voat/results/voat_funny_cp_labels.csv \
        --outdir results/entropy/voat/funny \
        --sample-fraction 0.25 --min-thread-size 5
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from matplotlib.dates import MonthLocator
from transformers import AutoModel, AutoTokenizer


from entropy import entropy as LegacyEntropy


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


def _load_key_events(notes_path: str = "notes/notes.md") -> List[Dict[str, object]]:
    """Parse notes/notes.md for key Reddit/Voat migration event months."""

    import re

    events = {
        "A": "/r/beatingwomen",
        "B": "/r/TheFappening",
        "C": "/r/nigger",
        "D": "/r/fatpeoplehate",
        "E": "/r/pizzagate",
        "F": "/r/incel",
        "G": "/r/GreatAwakening",
    }
    try:
        text = Path(notes_path).read_text(encoding="utf-8")
    except Exception:
        return []

    sep = r"[-‑‒–-−]"
    pat = re.compile(rf"^\s*[-*]?\s*(\d{{4}}){sep}(\d{{2}})(?:{sep}(\d{{2}}))?:.*$", re.MULTILINE)
    found: List[Dict[str, object]] = []
    for line in text.splitlines():
        for label, sub in events.items():
            if sub in line:
                m = pat.match(line)
                if m:
                    y, mo = m.group(1), m.group(2)
                    month = f"{y}-{mo}"
                    dt = pd.to_datetime(month + "-01", errors="coerce")
                    found.append({"label": label, "month_str": month, "month_dt": dt, "desc": line.strip()})
                    break
    # deduplicate by label (keep first occurrence)
    uniq: Dict[str, Dict[str, object]] = {}
    for item in found:
        uniq.setdefault(item["label"], item)
    ordered = sorted(uniq.values(), key=lambda x: (x["month_dt"] if x["month_dt"] is not None else pd.Timestamp.max))
    return ordered


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class Post:
    post_id: str
    user_id: str
    content: str
    publish_ts: pd.Timestamp


@dataclass
class Comment:
    post_id: str
    user_id: str
    parent_id: Optional[str]
    parent_user_id: Optional[str]
    content: str
    publish_ts: pd.Timestamp


@dataclass
class Pair:
    month: str
    thread_id: str
    post_id: str
    comment_id: str
    post_user: str
    comment_user: str
    post_type: str
    comment_type: str
    pair_type: str
    pair_role: str


@dataclass
class EmbedItem:
    token_vecs: np.ndarray
    n_tokens: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def clean_text(text: str) -> str:
    text = (text or "").replace("\n", " ").strip()
    return " ".join(text.split())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--community", required=True, help="Voat community name (case-insensitive)")
    parser.add_argument("--parquet", required=True, type=Path)
    parser.add_argument("--cp-labels", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--sample-fraction", type=float, default=0.25)
    parser.add_argument("--min-thread-size", type=int, default=5)
    parser.add_argument("--max-thread-size", type=int, default=None)
    parser.add_argument("--model", default="bert-base-uncased")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--sigma", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save-pairs", action="store_true", help="Persist per-pair CSV (can be large)")
    parser.add_argument("--pairs-csv", type=Path, default=None, help="Reuse existing pair CSV instead of recomputing")
    parser.add_argument("--cp-summary", type=Path, required=True, help="Core-periphery summary CSV with core_size")
    parser.add_argument("--cp-stability", type=Path, required=True, help="Core-periphery stability CSV with jaccard_core")
    return parser.parse_args()


def load_voat_data(parquet_path: Path, community: str) -> pd.DataFrame:
    cols = [
        "post_id",
        "publish_date",
        "user_id",
        "parent_id",
        "parent_user_id",
        "content",
        "interaction_type",
        "community",
    ]
    df = pd.read_parquet(parquet_path, columns=cols)
    comm = community.lower()
    df = df[df["community"].astype(str).str.lower() == comm].copy()
    df["publish_dt"] = pd.to_datetime(df["publish_date"], unit="s", utc=True)
    df["month"] = df["publish_dt"].dt.to_period("M")
    df["post_id"] = df["post_id"].astype(str)
    df["user_id"] = df["user_id"].astype(str)
    df["parent_id"] = df["parent_id"].apply(lambda x: str(x) if pd.notna(x) else None)
    df["parent_user_id"] = df["parent_user_id"].apply(lambda x: str(x) if pd.notna(x) else None)
    df["interaction_type"] = df["interaction_type"].str.lower()
    return df


def compute_root_map(df: pd.DataFrame) -> pd.Series:
    parent_map = df.set_index("post_id")["parent_id"].to_dict()
    cache: Dict[str, str] = {}

    def find_root(pid: str) -> str:
        cur = pid
        visited: List[str] = []
        while True:
            cached = cache.get(cur)
            if cached is not None:
                root = cached
                break
            parent = parent_map.get(cur)
            if parent is None or parent not in parent_map:
                root = cur
                break
            visited.append(cur)
            cur = parent
        for node in visited:
            cache[node] = root
        cache[cur] = root
        return root

    return df["post_id"].map(find_root)


def select_month_threads(
    month_df: pd.DataFrame,
    month_period: pd.Period,
    min_size: int,
    max_size: Optional[int],
    fraction: float,
    rng: random.Random,
) -> pd.DataFrame:
    grouped = (
        month_df.groupby("root_id")
        .agg(root_publish=("publish_dt", "min"), thread_end=("publish_dt", "max"), n_items=("post_id", "count"))
        .reset_index()
    )
    grouped["start_month"] = grouped["root_publish"].dt.to_period("M")
    grouped["end_month"] = grouped["thread_end"].dt.to_period("M")
    eligible = grouped[
        (grouped["start_month"] == month_period)
        & (grouped["end_month"] == month_period)
        & (grouped["n_items"] >= min_size)
    ]
    if max_size is not None and max_size > 0:
        eligible = eligible[eligible["n_items"] <= max_size]
    if eligible.empty:
        return eligible

    n_threads = len(eligible)
    sample_count = max(1, math.ceil(n_threads * fraction))
    if sample_count >= n_threads:
        selected = eligible
    else:
        selected = eligible.sample(n=sample_count, random_state=rng.randrange(1, 10**9))
    return selected.sort_values("root_id").reset_index(drop=True)


def make_model(model_name: str) -> tuple[AutoTokenizer, AutoModel, str]:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()
    model.to(device)
    return tokenizer, model, device


def compute_embeddings(
    tokenizer: AutoTokenizer,
    model: AutoModel,
    device: str,
    texts: Dict[str, str],
    max_tokens: int,
) -> Dict[str, EmbedItem]:
    embeddings: Dict[str, EmbedItem] = {}
    batch_ids: List[str] = []
    batch_texts: List[str] = []

    def flush() -> None:
        if not batch_ids:
            return
        with torch.no_grad():
            enc = tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=max_tokens,
                return_tensors="pt",
            )
            enc = {k: v.to(device) for k, v in enc.items()}
            hidden = model(**enc).last_hidden_state
            special = {tokenizer.cls_token_id, tokenizer.sep_token_id, tokenizer.pad_token_id}
            for idx, uid in enumerate(batch_ids):
                input_ids = enc["input_ids"][idx]
                vecs = hidden[idx]
                mask = torch.ones_like(input_ids, dtype=torch.bool)
                for sid in special:
                    if sid is not None:
                        mask &= input_ids != sid
                kept = vecs[mask]
                if kept.shape[0] == 0:
                    kept = vecs
                embeddings[uid] = EmbedItem(
                    token_vecs=kept.detach().cpu().numpy().astype(np.float32),
                    n_tokens=int(kept.shape[0]),
                )
        batch_ids.clear()
        batch_texts.clear()

    for uid, text in texts.items():
        batch_ids.append(uid)
        batch_texts.append(text)
        if len(batch_ids) >= 32:
            flush()
    flush()
    return embeddings


def entropy_post_to_comment(ex: np.ndarray, ey: np.ndarray, sigma: float) -> float:
    ent = LegacyEntropy(sigma=sigma, dim=-1)
    val = ent.forward(torch.from_numpy(ex), torch.from_numpy(ey), dim=-1)
    return float(val.detach().cpu().numpy())


def collect_pairs(
    month: str,
    df_month: pd.DataFrame,
    selected_threads: pd.DataFrame,
    cp_map: Dict[str, str],
) -> tuple[List[Pair], Dict[str, str]]:
    pairs: List[Pair] = []
    texts: Dict[str, str] = {}

    for _, row in selected_threads.iterrows():
        root_id = row["root_id"]
        thread_rows = df_month[df_month["root_id"] == root_id]
        post_row = thread_rows[thread_rows["post_id"] == root_id]
        if post_row.empty:
            continue
        post_row = post_row.iloc[0]
        if post_row["interaction_type"] != "post":
            continue
        post_text = clean_text(post_row.get("content", ""))
        if not post_text:
            continue
        post = Post(
            post_id=root_id,
            user_id=post_row["user_id"],
            content=post_text,
            publish_ts=post_row["publish_dt"],
        )
        texts[post.post_id] = post.content

        comments = thread_rows[
            (thread_rows["interaction_type"] == "comment")
            & (thread_rows["parent_id"] == root_id)
        ]
        for _, c_row in comments.iterrows():
            comment_text = clean_text(c_row.get("content", ""))
            if not comment_text:
                continue
            comment = Comment(
                post_id=c_row["post_id"],
                user_id=c_row["user_id"],
                parent_id=c_row["parent_id"],
                parent_user_id=c_row.get("parent_user_id"),
                content=comment_text,
                publish_ts=c_row["publish_dt"],
            )
            texts[comment.post_id] = comment.content

            post_type = cp_map.get(post.user_id, "P")
            comment_type = cp_map.get(comment.user_id, "P")
            same_user = post.user_id == comment.user_id
            pairs.append(
                Pair(
                    month=month,
                    thread_id=root_id,
                    post_id=post.post_id,
                    comment_id=comment.post_id,
                    post_user=post.user_id,
                    comment_user=comment.user_id,
                    post_type=post_type,
                    comment_type=comment_type,
                    pair_type="AA" if same_user else "AB",
                    pair_role="intrapersonal" if same_user else "interpersonal",
                )
            )

    return pairs, texts


EXPECTED_COMBOS = [
    ("AA", "C-C"),
    ("AA", "P-P"),
    ("AB", "C-C"),
    ("AB", "P-P"),
    ("AB", "C-P"),
    ("AB", "P-C"),
]


def summarize_by_combo(
    pairs_df: pd.DataFrame,
    all_months: List[str],
) -> pd.DataFrame:
    pairs_df = pairs_df.copy()
    pairs_df["month"] = pairs_df["month"].astype(str)
    rows: List[Dict[str, object]] = []
    grouped = pairs_df.groupby(["month", "pair_type", "cp_combo"], dropna=False)
    for (month, pair_type, cp_combo), grp in grouped:
        hpt = grp["H_per_token"].dropna()
        rows.append(
            {
                "month": month,
                "pair_type": pair_type,
                "cp_combo": cp_combo,
                "n_pairs": len(grp),
                "mean_H_per_token": hpt.mean() if len(hpt) else float("nan"),
                "median_H_per_token": hpt.median() if len(hpt) else float("nan"),
            }
        )

    summary = pd.DataFrame(
        rows,
        columns=[
            "month",
            "pair_type",
            "cp_combo",
            "n_pairs",
            "mean_H_per_token",
            "median_H_per_token",
        ],
    )
    expected_map: Dict[str, List[str]] = {}
    for pt, combo in EXPECTED_COMBOS:
        expected_map.setdefault(pt, []).append(combo)
    tuples = []
    for month in all_months:
        for pt, combos in expected_map.items():
            for combo in combos:
                tuples.append((month, pt, combo))
    idx = pd.MultiIndex.from_tuples(tuples, names=["month", "pair_type", "cp_combo"])
    summary = summary.set_index(["month", "pair_type", "cp_combo"]).reindex(idx)
    summary["n_pairs"] = summary["n_pairs"].fillna(0)
    metrics = ["mean_H_per_token", "median_H_per_token"]
    for (_, _), idx_vals in summary.groupby(level=[1, 2]).groups.items():
        filled = summary.loc[idx_vals, metrics].ffill().bfill()
        summary.loc[idx_vals, metrics] = filled
    summary[metrics] = summary[metrics].fillna(0.0)
    summary.reset_index(inplace=True)
    return summary


def summarize_by_role(pairs_df: pd.DataFrame, all_months: List[str]) -> pd.DataFrame:
    pairs_df = pairs_df.copy()
    pairs_df["month"] = pairs_df["month"].astype(str)
    rows: List[Dict[str, object]] = []
    grouped = pairs_df.groupby(["month", "pair_role"], dropna=False)
    for (month, role), grp in grouped:
        hpt = grp["H_per_token"].dropna()
        rows.append(
            {
                "month": month,
                "pair_role": role,
                "n_pairs": len(grp),
                "mean_H_per_token": hpt.mean() if len(hpt) else float("nan"),
                "median_H_per_token": hpt.median() if len(hpt) else float("nan"),
            }
        )

    summary = pd.DataFrame(rows)
    roles = summary["pair_role"].dropna().unique().tolist()
    if not roles:
        roles = ["intrapersonal", "interpersonal"]
    tuples = [(month, role) for month in all_months for role in roles]
    idx = pd.MultiIndex.from_tuples(tuples, names=["month", "pair_role"])
    summary = summary.set_index(["month", "pair_role"]).reindex(idx)
    summary["n_pairs"] = summary["n_pairs"].fillna(0)
    metrics = ["mean_H_per_token", "median_H_per_token"]
    for _, idx_vals in summary.groupby(level=1).groups.items():
        filled = summary.loc[idx_vals, metrics].ffill().bfill()
        summary.loc[idx_vals, metrics] = filled
    summary[metrics] = summary[metrics].fillna(0.0)
    summary.reset_index(inplace=True)
    return summary


def month_order_key(period_str: str) -> pd.Timestamp:
    return pd.Period(period_str).to_timestamp()


def add_rolling_columns(
    df: pd.DataFrame,
    group_cols: Sequence[str],
    value_cols: Sequence[str],
    window: int = 3,
) -> pd.DataFrame:
    if df.empty:
        for col in value_cols:
            df[f"{col}_roll{window}"] = df[col]
        return df

    out = df.copy()
    out["timestamp"] = out["month"].apply(lambda x: pd.Period(x).to_timestamp())
    out.sort_values(list(group_cols) + ["timestamp"], inplace=True)
    for _, grp in out.groupby(list(group_cols), sort=False):
        grp_sorted = grp.sort_values("timestamp")
        for col in value_cols:
            roll = grp_sorted[col].rolling(window=window, min_periods=1).mean()
            out.loc[grp_sorted.index, f"{col}_roll{window}"] = roll
    out.drop(columns=["timestamp"], inplace=True)
    return out


def plot_panels(
    combo_df: pd.DataFrame,
    events: List[Dict[str, object]],
    community_title: str,
    out_path: Path,
) -> None:
    if combo_df.empty:
        return
    combo_df = combo_df.copy()
    combo_df["timestamp"] = combo_df["month"].apply(lambda x: pd.Period(x).to_timestamp())

    intrap = combo_df[combo_df["pair_type"] == "AA"]
    inter = combo_df[combo_df["pair_type"] == "AB"]
    inter_same = inter[inter["cp_combo"].isin(["C-C", "P-P"])]
    inter_cross = inter[inter["cp_combo"].isin(["C-P", "P-C"])]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, constrained_layout=True)

    def plot_lines(ax, data: pd.DataFrame, title: str) -> None:
        palette = {
            "C-C": "#1b9e77",
            "C-P": "#d95f02",
            "P-C": "#7570b3",
            "P-P": "#66a61e",
        }
        for combo, grp in data.groupby("cp_combo"):
            ax.plot(
                grp["timestamp"],
                grp["mean_H_per_token_roll3"],
                marker="o",
                label=combo,
                color=palette.get(combo, None),
            )
        ax.set_title(title)
        ax.set_ylabel("Mean per-token entropy")
        ax.yaxis.grid(True, linestyle="--", linewidth=0.7, alpha=0.5)
        ax.axhline(0.0, color="#444444", linewidth=0.8, alpha=0.6)
        ax.legend()

    plot_lines(axes[0], intrap[intrap["cp_combo"].isin(["C-C", "P-P"] )], "Intrapersonal (AA)")
    plot_lines(axes[1], inter_same, "Interpersonal (AB) – Same group (C-C, P-P)")
    plot_lines(axes[2], inter_cross, "Interpersonal (AB) – Cross group (C-P, P-C)")

    event_ts = [ev["month_dt"] for ev in events if ev.get("month_dt") is not None]
    for ax in axes:
        for ev_dt in event_ts:
            ax.axvline(ev_dt, ls="--", lw=1, color="k", alpha=0.5)

    axes[-1].set_xlabel("Month")
    axes[-1].xaxis.set_major_locator(MonthLocator(interval=3))
    fig.autofmt_xdate()
    fig.suptitle(
        f"Voat /{community_title} post→comment per-token convergence entropy",
        fontsize=14,
    )
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def load_core_metrics(
    cp_summary_path: Path,
    cp_stability_path: Path,
    all_months: List[str],
) -> pd.DataFrame:
    core_df = pd.read_csv(cp_summary_path).rename(columns={"window": "month"})
    core_df["month"] = core_df["month"].astype(str)
    core_df = core_df[["month", "core_size"]]

    stability_df = pd.read_csv(cp_stability_path).rename(columns={"window_curr": "month"})
    stability_df["month"] = stability_df["month"].astype(str)
    stability_df = stability_df[["month", "jaccard_core"]]

    merged = pd.merge(core_df, stability_df, on="month", how="outer")
    merged = merged.drop_duplicates("month", keep="last").set_index("month").reindex(all_months)
    merged["core_size"] = merged["core_size"].astype(float)
    merged["jaccard_core"] = merged["jaccard_core"].astype(float)
    merged["core_size"] = merged["core_size"].ffill().bfill()
    merged["jaccard_core"] = merged["jaccard_core"].ffill().bfill()
    merged["timestamp"] = merged.index.map(lambda m: pd.Period(m, freq="M").to_timestamp())
    merged.reset_index(inplace=True)
    return merged


def plot_interpersonal_core_rows(
    combo_df: pd.DataFrame,
    core_metrics: pd.DataFrame,
    events: List[Dict[str, object]],
    community_title: str,
    out_path: Path,
) -> None:
    if combo_df.empty or core_metrics.empty:
        return
    inter = combo_df[(combo_df["pair_type"] == "AB") & (combo_df["cp_combo"].isin(["C-C", "P-P"]))].copy()
    if inter.empty:
        return
    inter["timestamp"] = inter["month"].apply(lambda x: pd.Period(x).to_timestamp())
    plot_df = inter.pivot_table(
        index="timestamp",
        columns="cp_combo",
        values="median_H_per_token_roll3",
    )

    aligned_core = core_metrics.copy()
    aligned_core["timestamp"] = aligned_core["month"].apply(lambda m: pd.Period(m, freq="M").to_timestamp())
    aligned_core.sort_values("timestamp", inplace=True)
    plot_df = plot_df.reindex(aligned_core["timestamp"])
    plot_df = plot_df.ffill().bfill()

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, constrained_layout=True)

    # Panel 1: Entropy
    colors = {"C-C": "#1b9e77", "P-P": "#66a61e"}
    for combo in ["C-C", "P-P"]:
        if combo in plot_df.columns:
            axes[0].plot(
                plot_df.index,
                plot_df[combo],
                marker="o",
                label=f"Entropy {combo}",
                color=colors.get(combo, None),
            )
    axes[0].set_ylabel("Median per-token entropy (3-mo roll)")
    axes[0].set_title("Interpersonal per-token entropy (C-C, P-P)")
    axes[0].yaxis.grid(True, linestyle="--", linewidth=0.7, alpha=0.5)
    axes[0].legend(loc="upper right")

    # Panel 2: Core size
    axes[1].plot(
        aligned_core["timestamp"],
        aligned_core["core_size"],
        color="#2c7fb8",
        linewidth=2.0,
        marker="o",
    )
    axes[1].set_ylabel("Core size")
    axes[1].set_title("Core size (monthly)")
    axes[1].yaxis.grid(True, linestyle="--", linewidth=0.7, alpha=0.5)

    # Panel 3: Core stability
    axes[2].plot(
        aligned_core["timestamp"],
        aligned_core["jaccard_core"],
        color="#f03b20",
        linewidth=2.0,
        marker="o",
    )
    axes[2].set_ylabel("Jaccard stability")
    axes[2].set_title("Core stability (Jaccard vs previous month)")
    axes[2].yaxis.grid(True, linestyle="--", linewidth=0.7, alpha=0.5)

    event_ts = [ev["month_dt"] for ev in events if ev.get("month_dt") is not None]
    for ax in axes:
        for ev_dt in event_ts:
            ax.axvline(ev_dt, ls="--", lw=1, color="k", alpha=0.5)

    axes[-1].set_xlabel("Month")
    axes[-1].xaxis.set_major_locator(MonthLocator(interval=3))
    fig.autofmt_xdate()
    fig.suptitle(f"Voat /{community_title}: per-token entropy vs. core size/stability", fontsize=14)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main() -> None:
    args = parse_args()

    community = args.community.lower()
    community_title = args.community
    events = _load_key_events()

    cp_summary_df = pd.read_csv(args.cp_summary)
    all_months = sorted(pd.Series(cp_summary_df["window"].astype(str).unique()).tolist())

    out_results = args.outdir / "results"
    out_figs = args.outdir / "figures"
    out_results.mkdir(parents=True, exist_ok=True)
    out_figs.mkdir(parents=True, exist_ok=True)

    prefix = f"voat_{community}"
    summary_combo_path = out_results / f"{prefix}_timeseries_summary_combo.csv"
    summary_role_path = out_results / f"{prefix}_timeseries_summary_role.csv"
    pairs_default_path = out_results / f"{prefix}_timeseries_pairs.csv"
    selected_path = out_results / f"{prefix}_timeseries_selected_threads.csv"
    entropy_fig_path = out_figs / f"{prefix}_entropy_panels.png"
    core_fig_path = out_figs / f"{prefix}_entropy_core_overlay.png"

    pairs_csv_path = args.pairs_csv if args.pairs_csv and args.pairs_csv.exists() else None
    pairs_save_path = args.pairs_csv if args.pairs_csv else pairs_default_path

    if pairs_csv_path:
        print(f"Loading existing pair data from {pairs_csv_path}", flush=True)
        pair_df = pd.read_csv(pairs_csv_path)
        summary_combo = summarize_by_combo(pair_df, all_months)
        summary_role = summarize_by_role(pair_df, all_months)
        summary_combo.sort_values("month", key=lambda s: s.map(month_order_key), inplace=True, ignore_index=True)
        summary_role.sort_values("month", key=lambda s: s.map(month_order_key), inplace=True, ignore_index=True)
        summary_combo = add_rolling_columns(
            summary_combo,
            group_cols=["pair_type", "cp_combo"],
            value_cols=["mean_H_per_token", "median_H_per_token"],
            window=3,
        )
        summary_role = add_rolling_columns(
            summary_role,
            group_cols=["pair_role"],
            value_cols=["mean_H_per_token", "median_H_per_token"],
            window=3,
        )
        print("Writing summary CSVs…", flush=True)
        summary_combo.to_csv(summary_combo_path, index=False)
        summary_role.to_csv(summary_role_path, index=False)
        print("Rendering panels…", flush=True)
        plot_panels(summary_combo, events, community_title, entropy_fig_path)
        if args.cp_summary and args.cp_summary.exists() and args.cp_stability and args.cp_stability.exists():
            core_metrics = load_core_metrics(args.cp_summary, args.cp_stability, all_months)
            plot_interpersonal_core_rows(
                summary_combo,
                core_metrics,
                events,
                community_title,
                core_fig_path,
            )
        print("Done.", flush=True)
        return

    print(f"Loading Voat /{community_title} data…", flush=True)
    df = load_voat_data(args.parquet, community)
    df["root_id"] = compute_root_map(df)
    print(f"Total interactions: {len(df):,}; months: {df['month'].nunique()}", flush=True)

    cp_labels = pd.read_csv(args.cp_labels)
    cp_labels["label_type"] = cp_labels["label"].map({0: "C", 1: "P"})

    print(f"Loading model {args.model}…", flush=True)
    tokenizer, model, device = make_model(args.model)
    print(f"Model on device: {device}", flush=True)

    pair_frames: List[pd.DataFrame] = []
    selected_records: List[Dict[str, object]] = []

    print(f"Processing {len(all_months)} months", flush=True)
    base_rng = random.Random(args.seed)

    for idx, month_str in enumerate(all_months):
        month_period = pd.Period(month_str, freq="M")
        month_df = df[df["month"] == month_period].copy()
        print(f"[{idx+1}/{len(all_months)}] Month {month_str}: {len(month_df):,} interactions", flush=True)
        cp_month = cp_labels[cp_labels["window"] == month_str]
        if cp_month.empty:
            print("  No CP labels for this month; skipping", flush=True)
            continue
        cp_map = {row["node_id"]: row["label_type"] for _, row in cp_month.iterrows()}

        rng = random.Random(base_rng.randrange(1, 10**9))
        selected = select_month_threads(
            month_df,
            month_period,
            args.min_thread_size,
            args.max_thread_size,
            args.sample_fraction,
            rng,
        )
        if selected.empty:
            print("  No eligible threads after filters", flush=True)
            continue
        print(f"  Selected {len(selected)} threads (25%)", flush=True)

        pairs, texts = collect_pairs(month_str, month_df, selected, cp_map)
        if not pairs:
            print("  No post→comment pairs extracted", flush=True)
            continue
        print(f"  Computing embeddings for {len(texts)} texts", flush=True)

        embeds = compute_embeddings(tokenizer, model, device, texts, args.max_tokens)
        records: List[Dict[str, object]] = []
        for pair in pairs:
            post_embed = embeds.get(pair.post_id)
            comment_embed = embeds.get(pair.comment_id)
            if post_embed is None or comment_embed is None:
                continue
            if post_embed.n_tokens == 0 or comment_embed.n_tokens == 0:
                continue
            h_val = entropy_post_to_comment(post_embed.token_vecs, comment_embed.token_vecs, args.sigma)
            records.append(
                {
                    "month": pair.month,
                    "thread_id": pair.thread_id,
                    "post_id": pair.post_id,
                    "comment_id": pair.comment_id,
                    "post_user": pair.post_user,
                    "comment_user": pair.comment_user,
                    "post_type": pair.post_type,
                    "comment_type": pair.comment_type,
                    "pair_type": pair.pair_type,
                    "pair_role": pair.pair_role,
                    "cp_combo": f"{pair.post_type}-{pair.comment_type}",
                    "H_per_token": h_val / post_embed.n_tokens if post_embed.n_tokens else math.nan,
                    "tokens_post": post_embed.n_tokens,
                    "tokens_comment": comment_embed.n_tokens,
                }
            )

        if not records:
            print("  All pairs filtered out after embedding", flush=True)
            continue

        pair_df = pd.DataFrame.from_records(records)
        print(
            f"  Stored {len(pair_df)} pairs (AA: {(pair_df['pair_type']=='AA').sum()}, AB: {(pair_df['pair_type']=='AB').sum()})",
            flush=True,
        )
        pair_frames.append(pair_df)

        selected_records.extend(
            {
                "month": month_str,
                "root_id": row["root_id"],
                "n_items": row["n_items"],
                "root_publish": row["root_publish"],
                "thread_end": row["thread_end"],
            }
            for _, row in selected.iterrows()
        )

    combined_pairs = (
        pd.concat(pair_frames, ignore_index=True)
        if pair_frames
        else pd.DataFrame(columns=["month", "pair_type", "cp_combo", "pair_role", "H_per_token"])
    )

    summary_combo = summarize_by_combo(combined_pairs, all_months)
    summary_role = summarize_by_role(combined_pairs, all_months)

    summary_combo.sort_values("month", key=lambda s: s.map(month_order_key), inplace=True, ignore_index=True)
    summary_role.sort_values("month", key=lambda s: s.map(month_order_key), inplace=True, ignore_index=True)
    summary_combo = add_rolling_columns(
        summary_combo,
        group_cols=["pair_type", "cp_combo"],
        value_cols=["mean_H_per_token", "median_H_per_token"],
        window=3,
    )
    summary_role = add_rolling_columns(
        summary_role,
        group_cols=["pair_role"],
        value_cols=["mean_H_per_token", "median_H_per_token"],
        window=3,
    )

    print("Writing summary CSVs…", flush=True)
    summary_combo.to_csv(summary_combo_path, index=False)
    summary_role.to_csv(summary_role_path, index=False)

    if args.save_pairs and pair_frames:
        all_pairs = pd.concat(pair_frames, ignore_index=True)
        all_pairs.sort_values(["month", "thread_id"], key=lambda s: s.map(month_order_key) if s.name == "month" else s, inplace=True)
        all_pairs.to_csv(pairs_save_path, index=False)

    if selected_records:
        selected_df = pd.DataFrame(selected_records)
        selected_df = selected_df.sort_values("month", key=lambda s: s.map(month_order_key))
        selected_df.to_csv(selected_path, index=False)

    print("Rendering panels…", flush=True)
    plot_panels(summary_combo, events, community_title, entropy_fig_path)
    if args.cp_summary and args.cp_summary.exists() and args.cp_stability and args.cp_stability.exists():
        core_metrics = load_core_metrics(args.cp_summary, args.cp_stability, all_months)
        plot_interpersonal_core_rows(
            summary_combo,
            core_metrics,
            events,
            community_title,
            core_fig_path,
        )
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
