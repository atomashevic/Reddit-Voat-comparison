#!/usr/bin/env python3
"""Score Voat activity with Detoxify and compare Detoxify outputs to ToxiGen."""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from detoxify import Detoxify
from scipy.stats import pearsonr, spearmanr
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[1]

CONTROVERSIAL_COMMUNITIES = [
    "cringeanarchy",
    "fatpeoplehate",
    "greatawakening",
    "mensrights",
    "milliondollarextreme",
    "kotakuinaction",
]
NORMAL_COMMUNITIES = ["funny", "gaming", "gifs", "pics", "technology", "videos"]
COMMUNITIES = CONTROVERSIAL_COMMUNITIES + NORMAL_COMMUNITIES

LOGGER = logging.getLogger(__name__)


def community_type(community: str) -> str:
    if community in CONTROVERSIAL_COMMUNITIES:
        return "controversial"
    if community in NORMAL_COMMUNITIES:
        return "normal"
    return "unknown"


def allocate_sample(total: int, communities: list[str]) -> dict[str, int]:
    base = total // len(communities)
    remainder = total % len(communities)
    return {
        community: base + (1 if index < remainder else 0)
        for index, community in enumerate(communities)
    }


def interaction_slug(interaction_type: str) -> str:
    mapping = {
        "post": "posts",
        "comment": "comments",
    }
    return mapping.get(interaction_type, f"{interaction_type}s")


def load_eligible_activity(data_dir: Path, community: str, interaction_type: str) -> pd.DataFrame:
    path = data_dir / f"voat_{community}_madoc.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing input parquet: {path}")

    columns = [
        "post_id",
        "publish_date",
        "user_id",
        "content",
        "interaction_type",
        "platform",
        "community",
        "toxicity_toxigen",
    ]
    df = pd.read_parquet(path, columns=columns)
    df["interaction_type"] = df["interaction_type"].astype(str).str.lower()
    df["content"] = df["content"].fillna("").astype(str).str.strip()
    df["toxicity_toxigen"] = pd.to_numeric(df["toxicity_toxigen"], errors="coerce")
    df = df[
        (df["interaction_type"] == interaction_type)
        & df["content"].ne("")
        & df["toxicity_toxigen"].notna()
    ].copy()
    df["community"] = community
    df["community_type"] = community_type(community)
    return df


def load_eligible_posts(data_dir: Path, community: str) -> pd.DataFrame:
    return load_eligible_activity(data_dir, community, "post")


def build_sample(data_dir: Path, sample_size: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    allocation = allocate_sample(sample_size, COMMUNITIES)
    samples = []
    manifest_rows = []

    for community in COMMUNITIES:
        eligible = load_eligible_posts(data_dir, community)
        requested = allocation[community]
        n = min(requested, len(eligible))
        if n < requested:
            LOGGER.warning(
                "%s has only %d eligible posts; requested %d",
                community,
                len(eligible),
                requested,
            )
        sample = eligible.sample(n=n, random_state=seed).copy()
        sample["sample_seed"] = seed
        sample["sample_requested_n"] = requested
        sample["sample_actual_n"] = n
        samples.append(sample)
        manifest_rows.append(
            {
                "platform": "voat",
                "community": community,
                "community_type": community_type(community),
                "eligible_posts": len(eligible),
                "sample_requested_n": requested,
                "sample_actual_n": n,
            }
        )

    out = pd.concat(samples, ignore_index=True)
    out = out.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    out.insert(0, "sample_row_id", np.arange(1, len(out) + 1))
    manifest = pd.DataFrame(manifest_rows)
    return out, manifest


def score_detoxify(
    texts: list[str],
    model_name: str,
    device: str,
    batch_size: int,
) -> tuple[pd.DataFrame, str]:
    model = Detoxify(model_name, device=device)
    model_device = str(next(model.model.parameters()).device)
    return score_detoxify_with_model(model, texts, batch_size), model_device


def score_detoxify_with_model(
    model: Detoxify,
    texts: list[str],
    batch_size: int,
    desc: str = "Detoxify batches",
) -> pd.DataFrame:
    batches = []
    for start in tqdm(range(0, len(texts), batch_size), desc=desc):
        batch_texts = texts[start : start + batch_size]
        scores = model.predict(batch_texts)
        batches.append(pd.DataFrame({f"detoxify_{k}": v for k, v in scores.items()}))
    return pd.concat(batches, ignore_index=True)


def correlation_rows(data: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    if group_cols:
        grouped = data.groupby(group_cols, dropna=False, sort=True)
    else:
        grouped = [("global", data)]

    detox_cols = [
        c
        for c in data.columns
        if c.startswith("detoxify_") and c != "detoxify_row_id"
    ]
    for group_key, group in grouped:
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        group_values = dict(zip(group_cols or ["scope"], group_key))
        for detox_col in detox_cols:
            pair = group[["toxicity_toxigen", detox_col]].dropna()
            row = {
                **group_values,
                "toxigen_col": "toxicity_toxigen",
                "detoxify_col": detox_col,
                "n": int(pair.shape[0]),
                "toxigen_mean": float(pair["toxicity_toxigen"].mean()) if not pair.empty else math.nan,
                "detoxify_mean": float(pair[detox_col].mean()) if not pair.empty else math.nan,
                "pearson_r": math.nan,
                "pearson_p": math.nan,
                "spearman_rho": math.nan,
                "spearman_p": math.nan,
            }
            if pair.shape[0] >= 3:
                tox = pair["toxicity_toxigen"].to_numpy()
                det = pair[detox_col].to_numpy()
                if np.nanstd(tox) > 0 and np.nanstd(det) > 0:
                    pearson = pearsonr(tox, det)
                    spearman = spearmanr(tox, det)
                    row.update(
                        {
                            "pearson_r": float(pearson.statistic),
                            "pearson_p": float(pearson.pvalue),
                            "spearman_rho": float(spearman.statistic),
                            "spearman_p": float(spearman.pvalue),
                        }
                    )
            rows.append(row)
    return pd.DataFrame(rows)


def write_summary(
    path: Path,
    sample: pd.DataFrame,
    manifest: pd.DataFrame,
    global_corr: pd.DataFrame,
    community_corr: pd.DataFrame,
    metadata: dict[str, object],
) -> None:
    toxicity_corr = global_corr[global_corr["detoxify_col"] == "detoxify_toxicity"].iloc[0]
    lines = [
        "# Detoxify vs ToxiGen Voat post sample",
        "",
        f"- sample_rows: {len(sample)}",
        f"- sample_seed: {metadata['sample_seed']}",
        f"- detoxify_model: {metadata['detoxify_model']}",
        f"- requested_device: {metadata['requested_device']}",
        f"- model_device: {metadata['model_device']}",
        f"- torch_version: {metadata['torch_version']}",
        f"- cuda_available: {metadata['cuda_available']}",
        f"- cuda_device: {metadata['cuda_device']}",
        "",
        "## Global toxicity correlation",
        "",
        (
            f"- n={int(toxicity_corr['n'])}; Pearson r={toxicity_corr['pearson_r']:.4f}; "
            f"Spearman rho={toxicity_corr['spearman_rho']:.4f}"
        ),
        f"- mean ToxiGen toxicity={toxicity_corr['toxigen_mean']:.4f}",
        f"- mean Detoxify toxicity={toxicity_corr['detoxify_mean']:.4f}",
        "",
        "## Community sample counts",
        "",
        manifest.to_markdown(index=False),
        "",
        "## Per-community Detoxify toxicity correlations",
        "",
        community_corr[community_corr["detoxify_col"] == "detoxify_toxicity"].to_markdown(index=False),
        "",
    ]
    path.write_text("\n".join(lines))


def write_all_activity_summary(
    path: Path,
    manifest: pd.DataFrame,
    global_corr: pd.DataFrame,
    community_corr: pd.DataFrame,
    metadata: dict[str, object],
) -> None:
    toxicity_corr = global_corr[global_corr["detoxify_col"] == "detoxify_toxicity"].iloc[0]
    interaction_label = metadata["interaction_type"]
    lines = [
        f"# Detoxify vs ToxiGen Voat all-{interaction_label} run",
        "",
        f"- scored_rows: {metadata['scored_rows']}",
        f"- interaction_type: {interaction_label}",
        f"- detoxify_model: {metadata['detoxify_model']}",
        f"- requested_device: {metadata['requested_device']}",
        f"- model_device: {metadata['model_device']}",
        f"- torch_version: {metadata['torch_version']}",
        f"- cuda_available: {metadata['cuda_available']}",
        f"- cuda_device: {metadata['cuda_device']}",
        "",
        "## Global toxicity correlation",
        "",
        (
            f"- n={int(toxicity_corr['n'])}; Pearson r={toxicity_corr['pearson_r']:.4f}; "
            f"Spearman rho={toxicity_corr['spearman_rho']:.4f}"
        ),
        f"- mean ToxiGen toxicity={toxicity_corr['toxigen_mean']:.4f}",
        f"- mean Detoxify toxicity={toxicity_corr['detoxify_mean']:.4f}",
        "",
        "## Community counts",
        "",
        manifest.to_markdown(index=False),
        "",
        "## Per-community Detoxify toxicity correlations",
        "",
        community_corr[community_corr["detoxify_col"] == "detoxify_toxicity"].to_markdown(index=False),
        "",
    ]
    path.write_text("\n".join(lines))


def run_all_activity(args: argparse.Namespace, prefix: str) -> None:
    model = Detoxify(args.detoxify_model, device=args.device)
    model_device = str(next(model.model.parameters()).device)

    scored_frames = []
    manifest_rows = []
    for community in COMMUNITIES:
        community_output = args.output_dir / f"{prefix}_{community}_scores.csv"
        eligible = load_eligible_activity(args.data_dir, community, args.interaction_type)
        if community_output.exists() and not args.overwrite:
            LOGGER.info("Using existing scores for %s: %s", community, community_output)
            scored = pd.read_csv(community_output)
        else:
            LOGGER.info(
                "Scoring %s (%d eligible %s rows)",
                community,
                len(eligible),
                args.interaction_type,
            )
            scores = score_detoxify_with_model(
                model,
                eligible["content"].tolist(),
                args.batch_size,
                desc=f"Detoxify {community}",
            )
            scored = pd.concat([eligible.reset_index(drop=True), scores], axis=1)
            scored.insert(0, "score_row_id", np.arange(1, len(scored) + 1))
            if args.drop_content:
                scored = scored.drop(columns=["content"])
            scored.to_csv(community_output, index=False)

        scored_frames.append(scored)
        manifest_rows.append(
            {
                "platform": "voat",
                "community": community,
                "community_type": community_type(community),
                "interaction_type": args.interaction_type,
                "eligible_rows": len(eligible),
                "scored_rows": len(scored),
                "score_file": community_output.name,
            }
        )

    scored_all = pd.concat(scored_frames, ignore_index=True)
    manifest = pd.DataFrame(manifest_rows)
    metadata = {
        "mode": f"all_{interaction_slug(args.interaction_type)}",
        "interaction_type": args.interaction_type,
        "scored_rows": int(len(scored_all)),
        "detoxify_model": args.detoxify_model,
        "requested_device": args.device,
        "model_device": model_device,
        "batch_size": args.batch_size,
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
    }

    global_corr = correlation_rows(scored_all, [])
    type_corr = correlation_rows(scored_all, ["community_type"])
    community_corr = correlation_rows(scored_all, ["community_type", "community"])

    combined_path = args.output_dir / f"{prefix}_scores_all_communities.csv"
    manifest_path = args.output_dir / f"{prefix}_manifest.csv"
    global_corr_path = args.output_dir / f"{prefix}_correlations_global.csv"
    type_corr_path = args.output_dir / f"{prefix}_correlations_by_type.csv"
    community_corr_path = args.output_dir / f"{prefix}_correlations_by_community.csv"
    metadata_path = args.output_dir / f"{prefix}_metadata.json"
    summary_path = args.output_dir / f"{prefix}_summary.md"

    scored_all.to_csv(combined_path, index=False)
    manifest.to_csv(manifest_path, index=False)
    global_corr.to_csv(global_corr_path, index=False)
    type_corr.to_csv(type_corr_path, index=False)
    community_corr.to_csv(community_corr_path, index=False)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    write_all_activity_summary(summary_path, manifest, global_corr, community_corr, metadata)

    LOGGER.info("Wrote combined all-%s scores: %s", args.interaction_type, combined_path)
    LOGGER.info("Wrote manifest: %s", manifest_path)
    LOGGER.info("Wrote global correlations: %s", global_corr_path)
    LOGGER.info("Wrote community correlations: %s", community_corr_path)
    LOGGER.info("Wrote summary: %s", summary_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "results" / "toxicity" / "voat" / "results",
    )
    parser.add_argument("--sample-size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260602)
    parser.add_argument("--all-posts", action="store_true", help="Score every eligible post instead of a stratified sample.")
    parser.add_argument(
        "--interaction-type",
        choices=["post", "comment"],
        default="post",
        help="Interaction type to score in all-posts mode.",
    )
    parser.add_argument("--detoxify-model", default="unbiased")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--output-prefix")
    parser.add_argument("--overwrite", action="store_true", help="Rescore community outputs that already exist.")
    parser.add_argument("--drop-content", action="store_true", help="Do not duplicate source text in score CSVs.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("Requested CUDA, but torch.cuda.is_available() is false")

    if args.output_prefix:
        prefix = args.output_prefix
    elif args.all_posts:
        prefix = f"voat_detoxify_{args.detoxify_model}_all_{interaction_slug(args.interaction_type)}"
    else:
        prefix = f"voat_detoxify_{args.detoxify_model}_{args.sample_size // 1000}k_post_sample"

    if args.all_posts:
        run_all_activity(args, prefix)
        return

    sample, manifest = build_sample(args.data_dir, args.sample_size, args.seed)
    scores, model_device = score_detoxify(
        sample["content"].tolist(),
        args.detoxify_model,
        args.device,
        args.batch_size,
    )
    scored = pd.concat([sample.reset_index(drop=True), scores], axis=1)

    metadata = {
        "sample_size": args.sample_size,
        "sample_seed": args.seed,
        "detoxify_model": args.detoxify_model,
        "requested_device": args.device,
        "model_device": model_device,
        "batch_size": args.batch_size,
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
    }

    global_corr = correlation_rows(scored, [])
    type_corr = correlation_rows(scored, ["community_type"])
    community_corr = correlation_rows(scored, ["community_type", "community"])

    sample_path = args.output_dir / f"{prefix}_scores.csv"
    manifest_path = args.output_dir / f"{prefix}_manifest.csv"
    global_corr_path = args.output_dir / f"{prefix}_correlations_global.csv"
    type_corr_path = args.output_dir / f"{prefix}_correlations_by_type.csv"
    community_corr_path = args.output_dir / f"{prefix}_correlations_by_community.csv"
    metadata_path = args.output_dir / f"{prefix}_metadata.json"
    summary_path = args.output_dir / f"{prefix}_summary.md"

    scored.to_csv(sample_path, index=False)
    manifest.to_csv(manifest_path, index=False)
    global_corr.to_csv(global_corr_path, index=False)
    type_corr.to_csv(type_corr_path, index=False)
    community_corr.to_csv(community_corr_path, index=False)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    write_summary(summary_path, scored, manifest, global_corr, community_corr, metadata)

    LOGGER.info("Wrote sample scores: %s", sample_path)
    LOGGER.info("Wrote global correlations: %s", global_corr_path)
    LOGGER.info("Wrote community correlations: %s", community_corr_path)
    LOGGER.info("Wrote summary: %s", summary_path)


if __name__ == "__main__":
    main()
