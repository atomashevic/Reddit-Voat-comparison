#!/usr/bin/env python3
"""Convergence entropy for Voat post–comment pairs.

This script samples Voat threads for a specific community/month and computes
convergence entropy between the root post and each first-level comment within
those threads. Pair types follow the earlier convention:

- AA: post author == comment author (intrapersonal)
- AB: post author != comment author (interpersonal)

For each pair we also track core/periphery membership of both users using the
monthly labels, enabling summaries by pair type, core/periphery combination, and
inter/intra-personal roles.

Outputs (saved under ``<outdir>/results``):

- ``voat_<community>_<month>_selected_threads.csv`` – sampled thread metadata
- ``voat_<community>_<month>_entropy_pairs.csv`` – pair-level entropy metrics
- ``voat_<community>_<month>_summary_entropy.csv`` – averages by pair/core combo
- ``voat_<community>_<month>_summary_personal.csv`` – intra vs. interpersonal

Example usage::

    python scripts/convergence_entropy_chains.py \
        --parquet data/voat_funny_madoc.parquet \
        --cp-labels results/core-periphery/voat/results/voat_funny_cp_labels.csv \
        --community funny --month 2016-07 \
        --outdir results/sentiment/funny/voat \
        --sample-size 10 --min-thread-size 5 --max-thread-size 15
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from transformers import AutoModel, AutoTokenizer

from entropy import entropy as LegacyEntropy


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
    thread_id: str
    post_id: str
    comment_id: str
    post_user: str
    comment_user: str
    post_type: str
    comment_type: str
    pair_type: str  # "AA" or "AB"
    pair_role: str  # "intrapersonal" or "interpersonal"


@dataclass
class EmbedItem:
    token_vecs: np.ndarray
    n_tokens: int


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", required=True, type=Path, help="Voat MADOC parquet")
    parser.add_argument("--cp-labels", required=True, type=Path, help="Core/periphery labels CSV")
    parser.add_argument("--community", required=True, help="Community name (e.g., funny)")
    parser.add_argument("--month", required=True, help="Month in YYYY-MM format")
    parser.add_argument("--outdir", required=True, type=Path, help="Output directory root")
    parser.add_argument("--sample-size", type=int, default=10, help="Threads to sample")
    parser.add_argument("--min-thread-size", type=int, default=5, help="Minimum interactions per thread")
    parser.add_argument("--max-thread-size", type=int, default=None, help="Maximum interactions per thread (omit or <=0 for no cap)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for thread sampling")
    parser.add_argument("--model", default="bert-base-uncased", help="HF model name for embeddings")
    parser.add_argument("--max-tokens", type=int, default=256, help="Max tokens per text for embeddings")
    parser.add_argument("--sigma", type=float, default=0.3, help="Sigma parameter for entropy estimator")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Loading and selection
# ---------------------------------------------------------------------------


def clean_text(text: str) -> str:
    text = (text or "").replace("\n", " ").strip()
    return " ".join(text.split())


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
    df = df[df["community"].astype(str) == community].copy()
    df["publish_dt"] = pd.to_datetime(df["publish_date"], unit="s", utc=True)
    df["year_month"] = df["publish_dt"].dt.to_period("M")
    df["post_id"] = df["post_id"].astype(str)
    df["user_id"] = df["user_id"].astype(str)
    df["parent_id"] = df["parent_id"].apply(lambda x: str(x) if pd.notna(x) else None)
    df["parent_user_id"] = df["parent_user_id"].apply(lambda x: str(x) if pd.notna(x) else None)
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


def select_threads(
    df: pd.DataFrame,
    month: str,
    min_size: int,
    max_size: Optional[int],
    sample_size: int,
    seed: int,
) -> pd.DataFrame:
    period = pd.Period(month)
    grouped = (
        df.groupby("root_id")
        .agg(
            root_publish=("publish_dt", "min"),
            thread_end=("publish_dt", "max"),
            n_items=("post_id", "count"),
        )
        .reset_index()
    )
    grouped["start_month"] = grouped["root_publish"].dt.to_period("M")
    grouped["end_month"] = grouped["thread_end"].dt.to_period("M")
    eligible = grouped[
        (grouped["start_month"] == period)
        & (grouped["end_month"] == period)
        & (grouped["n_items"] >= min_size)
    ]
    if max_size is not None and max_size > 0:
        eligible = eligible[eligible["n_items"] <= max_size]
    if eligible.empty:
        raise RuntimeError("No threads match the selection criteria.")
    rng = random.Random(seed)
    if len(eligible) > sample_size:
        eligible = eligible.sample(n=sample_size, random_state=rng.randrange(1, 10**9))
    return eligible.sort_values("root_id").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


def make_model(model_name: str) -> Tuple[AutoTokenizer, AutoModel, str]:
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
            outputs = model(**enc).last_hidden_state
            special_ids = {tokenizer.cls_token_id, tokenizer.sep_token_id, tokenizer.pad_token_id}
            for idx, uid in enumerate(batch_ids):
                input_ids = enc["input_ids"][idx]
                vecs = outputs[idx]
                mask = torch.ones_like(input_ids, dtype=torch.bool)
                for sid in special_ids:
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
        if len(batch_ids) >= 16:
            flush()
    flush()
    return embeddings


def entropy_post_to_comment(ex: np.ndarray, ey: np.ndarray, sigma: float) -> float:
    ent = LegacyEntropy(sigma=sigma, dim=-1)
    val = ent.forward(torch.from_numpy(ex), torch.from_numpy(ey), dim=-1)
    return float(val.detach().cpu().numpy())


# ---------------------------------------------------------------------------
# Pair collection
# ---------------------------------------------------------------------------


def collect_pairs(
    df: pd.DataFrame,
    selected_threads: pd.DataFrame,
    cp_map: Dict[str, str],
) -> Tuple[List[Pair], Dict[str, str]]:
    pairs: List[Pair] = []
    texts: Dict[str, str] = {}

    for _, row in selected_threads.iterrows():
        root_id = row["root_id"]
        thread_rows = df[df["root_id"] == root_id]

        post_row = thread_rows[thread_rows["post_id"] == root_id]
        if post_row.empty:
            continue
        post_row = post_row.iloc[0]
        post_text = clean_text(str(post_row.get("content", "")))
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
            (thread_rows["interaction_type"].str.lower() == "comment")
            & (thread_rows["parent_id"] == root_id)
        ].copy()

        for _, c_row in comments.iterrows():
            comment_text = clean_text(str(c_row.get("content", "")))
            if not comment_text:
                continue
            comment = Comment(
                post_id=c_row["post_id"],
                user_id=c_row["user_id"],
                parent_id=c_row["parent_id"],
                parent_user_id=c_row["parent_user_id"],
                content=comment_text,
                publish_ts=c_row["publish_dt"],
            )
            texts[comment.post_id] = comment.content

            post_type = cp_map.get(post.user_id, "P")
            comment_type = cp_map.get(comment.user_id, "P")
            same_user = post.user_id == comment.user_id
            pair = Pair(
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
            pairs.append(pair)

    return pairs, texts


# ---------------------------------------------------------------------------
# Aggregation utilities
# ---------------------------------------------------------------------------


def summarize_by_type(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["pair_type", "cp_combo", "n_pairs", "mean_H", "mean_H_per_token"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    grouped = df.groupby(["pair_type", "cp_combo"], dropna=False)
    agg = grouped["H"].agg(mean_H="mean", n_pairs="count")
    agg_pt = grouped["H_per_token"].mean().rename("mean_H_per_token")
    out = agg.join(agg_pt, how="left").reset_index()
    return out[cols]


def summarize_personal(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["pair_role", "n_pairs", "mean_H", "mean_H_per_token"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    grouped = df.groupby("pair_role")
    agg = grouped["H"].agg(mean_H="mean", n_pairs="count")
    agg_pt = grouped["H_per_token"].mean().rename("mean_H_per_token")
    out = agg.join(agg_pt, how="left").reset_index()
    return out[cols]


# ---------------------------------------------------------------------------
# Main routine
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()

    out_results = args.outdir / "results"
    out_figs = args.outdir / "figures"
    out_results.mkdir(parents=True, exist_ok=True)
    out_figs.mkdir(parents=True, exist_ok=True)

    df = load_voat_data(args.parquet, args.community)
    df["root_id"] = compute_root_map(df)

    selected = select_threads(
        df,
        args.month,
        args.min_thread_size,
        args.max_thread_size,
        args.sample_size,
        args.seed,
    )
    selected.to_csv(out_results / f"voat_{args.community}_{args.month}_selected_threads.csv", index=False)

    cp_labels = pd.read_csv(args.cp_labels)
    cp_month = cp_labels[cp_labels["window"] == args.month]
    if cp_month.empty:
        raise RuntimeError(f"No core/periphery labels for month {args.month}")
    cp_map = {row["node_id"]: ("C" if row["label"] == 0 else "P") for _, row in cp_month.iterrows()}

    pairs, texts = collect_pairs(df, selected, cp_map)
    if not pairs:
        raise RuntimeError("No qualifying post/comment pairs were extracted.")

    tokenizer, model, device = make_model(args.model)
    embeddings = compute_embeddings(tokenizer, model, device, texts, args.max_tokens)

    records: List[Dict[str, object]] = []
    for pair in pairs:
        post_embed = embeddings.get(pair.post_id)
        comment_embed = embeddings.get(pair.comment_id)
        if post_embed is None or comment_embed is None:
            continue
        if post_embed.n_tokens == 0 or comment_embed.n_tokens == 0:
            continue
        h_val = entropy_post_to_comment(post_embed.token_vecs, comment_embed.token_vecs, args.sigma)
        records.append(
            {
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
                "H": h_val,
                "H_per_token": h_val / post_embed.n_tokens if post_embed.n_tokens else math.nan,
                "tokens_post": post_embed.n_tokens,
                "tokens_comment": comment_embed.n_tokens,
            }
        )

    pair_df = pd.DataFrame.from_records(records)
    if pair_df.empty:
        raise RuntimeError("All post/comment pairs were filtered out during embedding.")

    pairs_path = out_results / f"voat_{args.community}_{args.month}_entropy_pairs.csv"
    pair_df.to_csv(pairs_path, index=False)

    summary_type = summarize_by_type(pair_df)
    summary_type.to_csv(
        out_results / f"voat_{args.community}_{args.month}_summary_entropy.csv",
        index=False,
    )

    summary_personal = summarize_personal(pair_df)
    summary_personal.to_csv(
        out_results / f"voat_{args.community}_{args.month}_summary_personal.csv",
        index=False,
    )

    print("=== Entropy by Pair/Core Combo ===")
    print(summary_type)
    print("\n=== Intra vs Interpersonal ===")
    print(summary_personal)


if __name__ == "__main__":
    main()
