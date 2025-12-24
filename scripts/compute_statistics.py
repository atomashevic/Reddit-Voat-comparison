#!/usr/bin/env python3
"""Compute effect sizes and permutation tests for Reddit-Voat paper.

Computes:
1. Effect sizes (Glass's Δ, Cliff's δ) for Voat vs Reddit toxicity
2. Block permutation tests for pre/post-GA regime comparison
3. FDR correction for multiple comparisons

Usage:
    python scripts/compute_statistics.py
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from datetime import datetime

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Configuration
RESULTS_ROOT = Path(__file__).resolve().parents[1] / "results"
COMMUNITIES = ["funny", "gaming", "technology", "videos", "gifs", "pics"]

# Event dates
GA_BAN_DATE = pd.Timestamp("2018-09-12")  # GreatAwakening ban

# Analysis parameters
BLOCK_SIZE = 3  # months, for block permutation
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


# =============================================================================
# Effect Size Functions
# =============================================================================

def cliffs_delta(x: np.ndarray, y: np.ndarray) -> float:
    """
    Cliff's delta: non-parametric effect size for ordinal/bounded data.

    Measures the probability that a randomly selected value from x
    is greater than a randomly selected value from y, minus the reverse.

    Interpretation:
        |δ| < 0.147: negligible
        |δ| < 0.33: small
        |δ| < 0.474: medium
        |δ| >= 0.474: large

    Returns: delta in [-1, 1]
    """
    x = np.asarray(x)
    y = np.asarray(y)

    # Remove NaN values
    x = x[~np.isnan(x)]
    y = y[~np.isnan(y)]

    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return np.nan

    # Count dominance
    greater = sum(1 for a in x for b in y if a > b)
    less = sum(1 for a in x for b in y if a < b)

    return (greater - less) / (n1 * n2)


def glass_delta(treatment: np.ndarray, control: np.ndarray) -> float:
    """
    Glass's Δ: effect size using control group SD as denominator.

    Appropriate when comparing to a baseline (Reddit as control).

    Returns: (mean_treatment - mean_control) / sd_control
    """
    treatment = np.asarray(treatment)
    control = np.asarray(control)

    # Remove NaN values
    treatment = treatment[~np.isnan(treatment)]
    control = control[~np.isnan(control)]

    if len(treatment) == 0 or len(control) == 0:
        return np.nan

    sd_control = np.std(control, ddof=1)
    if sd_control == 0:
        return np.nan

    return (np.mean(treatment) - np.mean(control)) / sd_control


def bootstrap_ci(x: np.ndarray, y: np.ndarray, func, n_bootstrap: int = 1000,
                 ci: float = 0.95, seed: int = 42) -> tuple:
    """Bootstrap confidence interval for effect size."""
    rng = np.random.RandomState(seed)

    x = np.asarray(x)
    y = np.asarray(y)
    x = x[~np.isnan(x)]
    y = y[~np.isnan(y)]

    boot_values = []
    for _ in range(n_bootstrap):
        x_boot = rng.choice(x, size=len(x), replace=True)
        y_boot = rng.choice(y, size=len(y), replace=True)
        boot_values.append(func(x_boot, y_boot))

    boot_values = np.array(boot_values)
    alpha = 1 - ci
    lower = np.nanpercentile(boot_values, 100 * alpha / 2)
    upper = np.nanpercentile(boot_values, 100 * (1 - alpha / 2))

    return lower, upper


def interpret_cliffs_delta(d: float) -> str:
    """Interpret Cliff's delta magnitude."""
    abs_d = abs(d)
    if abs_d < 0.147:
        return "negligible"
    elif abs_d < 0.33:
        return "small"
    elif abs_d < 0.474:
        return "medium"
    else:
        return "large"


# =============================================================================
# Permutation Test Functions
# =============================================================================

def block_permutation_test(pre_data: np.ndarray, post_data: np.ndarray,
                           n_permutations: int = 10000,
                           block_size: int = 3,
                           seed: int = 42) -> dict:
    """
    Block permutation test preserving temporal autocorrelation.

    Shuffles blocks of consecutive observations rather than individual points
    to preserve short-term dependencies in time series data.

    Args:
        pre_data: observations before breakpoint
        post_data: observations after breakpoint
        n_permutations: number of permutations
        block_size: size of blocks to shuffle (in months)
        seed: random seed

    Returns:
        dict with observed_diff, p_value, null_distribution
    """
    rng = np.random.RandomState(seed)

    # Remove NaN
    pre_data = np.asarray(pre_data)
    post_data = np.asarray(post_data)
    pre_data = pre_data[~np.isnan(pre_data)]
    post_data = post_data[~np.isnan(post_data)]

    if len(pre_data) == 0 or len(post_data) == 0:
        return {"observed_diff": np.nan, "p_value": np.nan, "null_distribution": []}

    # Observed difference
    observed_diff = np.mean(post_data) - np.mean(pre_data)

    # Combine data
    combined = np.concatenate([pre_data, post_data])
    n_pre = len(pre_data)
    n_total = len(combined)

    # Create blocks
    n_blocks = n_total // block_size
    remainder = n_total % block_size

    # Build blocks (last block may be smaller)
    blocks = []
    for i in range(n_blocks):
        blocks.append(combined[i * block_size:(i + 1) * block_size])
    if remainder > 0:
        blocks.append(combined[n_blocks * block_size:])

    # Permutation test
    null_diffs = []
    for _ in range(n_permutations):
        # Shuffle blocks
        shuffled_blocks = [blocks[i].copy() for i in rng.permutation(len(blocks))]
        shuffled = np.concatenate(shuffled_blocks)

        # Split at original breakpoint
        null_pre = shuffled[:n_pre]
        null_post = shuffled[n_pre:]

        null_diff = np.mean(null_post) - np.mean(null_pre)
        null_diffs.append(null_diff)

    null_diffs = np.array(null_diffs)

    # Two-sided p-value
    p_value = np.mean(np.abs(null_diffs) >= np.abs(observed_diff))

    return {
        "observed_diff": observed_diff,
        "p_value": p_value,
        "null_distribution": null_diffs,
        "n_pre": n_pre,
        "n_post": len(post_data)
    }


def benjamini_hochberg(p_values: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """
    Benjamini-Hochberg FDR correction.

    Returns adjusted p-values.
    """
    p_values = np.asarray(p_values)
    n = len(p_values)

    # Handle NaN
    valid_mask = ~np.isnan(p_values)
    valid_p = p_values[valid_mask]

    if len(valid_p) == 0:
        return p_values

    # Sort and compute adjusted p-values
    sorted_idx = np.argsort(valid_p)
    sorted_p = valid_p[sorted_idx]

    # Compute adjusted p-values
    adjusted = np.zeros_like(sorted_p)
    m = len(sorted_p)

    for i in range(m - 1, -1, -1):
        if i == m - 1:
            adjusted[i] = sorted_p[i]
        else:
            adjusted[i] = min(adjusted[i + 1], sorted_p[i] * m / (i + 1))

    # Unsort
    unsorted_adjusted = np.zeros_like(sorted_p)
    unsorted_adjusted[sorted_idx] = adjusted

    # Put back into original array
    result = p_values.copy()
    result[valid_mask] = unsorted_adjusted

    return result


# =============================================================================
# Data Loading
# =============================================================================

def load_voat_global() -> pd.DataFrame:
    """Load Voat global aggregate data."""
    path = RESULTS_ROOT / "global" / "voat_global_aggregate.csv"
    df = pd.read_csv(path)
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    return df.sort_values("month_dt")


def load_reddit_community(community: str) -> pd.DataFrame:
    """Load Reddit monthly aggregates for a community."""
    path = RESULTS_ROOT / "reddit" / community / f"reddit_{community}_monthly_aggregates.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["month_dt"] = pd.to_datetime(df["month"] + "-01")
    return df.sort_values("month_dt")


def load_voat_community(community: str) -> pd.DataFrame:
    """Load Voat monthly aggregates for a community."""
    # Try compare directory first
    path = RESULTS_ROOT / "compare" / community / f"{community}_monthly_metrics.csv"
    if path.exists():
        df = pd.read_csv(path)
        if "month" in df.columns:
            df["month_dt"] = pd.to_datetime(df["month"] + "-01")
        return df.sort_values("month_dt") if "month_dt" in df.columns else df
    return None


# =============================================================================
# Main Analysis
# =============================================================================

def compute_toxicity_effect_sizes() -> pd.DataFrame:
    """Compute effect sizes for Voat vs Reddit toxicity by community."""
    print("\n" + "=" * 60)
    print("EFFECT SIZES: Voat vs Reddit Toxicity")
    print("=" * 60)

    results = []

    for comm in COMMUNITIES:
        reddit_df = load_reddit_community(comm)

        # For Voat, we need community-specific data
        # Load from compare directory
        voat_path = RESULTS_ROOT / "compare" / comm / f"{comm}_monthly_metrics.csv"
        if voat_path.exists():
            voat_df = pd.read_csv(voat_path)
        else:
            print(f"  {comm}: Voat data not found, skipping")
            continue

        if reddit_df is None:
            print(f"  {comm}: Reddit data not found, skipping")
            continue

        # Extract toxicity values
        # Reddit column name
        reddit_tox = reddit_df["toxicity_mean"].dropna().values

        # Voat column name (might be toxicity_mean_voat or similar)
        voat_col = None
        for col in ["toxicity_mean_voat", "toxicity_mean", "voat_toxicity_mean"]:
            if col in voat_df.columns:
                voat_col = col
                break

        if voat_col is None:
            print(f"  {comm}: No toxicity column found in Voat data")
            continue

        voat_tox = voat_df[voat_col].dropna().values

        # Compute effect sizes
        glass_d = glass_delta(voat_tox, reddit_tox)
        cliff_d = cliffs_delta(voat_tox, reddit_tox)

        # Bootstrap CIs
        glass_ci = bootstrap_ci(voat_tox, reddit_tox, glass_delta, n_bootstrap=1000)
        cliff_ci = bootstrap_ci(voat_tox, reddit_tox, cliffs_delta, n_bootstrap=1000)

        # Raw means
        voat_mean = np.mean(voat_tox)
        reddit_mean = np.mean(reddit_tox)

        results.append({
            "community": comm,
            "voat_mean": voat_mean,
            "reddit_mean": reddit_mean,
            "difference": voat_mean - reddit_mean,
            "ratio": voat_mean / reddit_mean if reddit_mean > 0 else np.nan,
            "glass_delta": glass_d,
            "glass_ci_lower": glass_ci[0],
            "glass_ci_upper": glass_ci[1],
            "cliffs_delta": cliff_d,
            "cliffs_ci_lower": cliff_ci[0],
            "cliffs_ci_upper": cliff_ci[1],
            "interpretation": interpret_cliffs_delta(cliff_d),
            "n_voat": len(voat_tox),
            "n_reddit": len(reddit_tox)
        })

        print(f"\n  {comm}:")
        print(f"    Voat mean: {voat_mean:.4f}, Reddit mean: {reddit_mean:.4f}")
        print(f"    Glass's Δ: {glass_d:.3f} [{glass_ci[0]:.3f}, {glass_ci[1]:.3f}]")
        print(f"    Cliff's δ: {cliff_d:.3f} [{cliff_ci[0]:.3f}, {cliff_ci[1]:.3f}] ({interpret_cliffs_delta(cliff_d)})")

    return pd.DataFrame(results)


def compute_regime_permutation_tests() -> pd.DataFrame:
    """Run block permutation tests for pre/post-GA regime comparison."""
    print("\n" + "=" * 60)
    print("PERMUTATION TESTS: Pre/Post-GA Regime Comparison")
    print(f"Block size: {BLOCK_SIZE} months, Permutations: {N_PERMUTATIONS}")
    print("=" * 60)

    # Load global Voat data
    voat_df = load_voat_global()

    # Filter to analysis period (after first ban to end)
    voat_df = voat_df[voat_df["month_dt"] >= "2015-06-01"].copy()

    # Define metrics to test
    metrics = {
        "ei_index": "E-I Index",
        "toxicity_mean_voat": "Toxicity",
        "reputation_mean_voat_agg": "Reputation"
    }

    results = []

    # Global tests
    print("\n  GLOBAL (all communities):")
    for metric_col, metric_name in metrics.items():
        if metric_col not in voat_df.columns:
            print(f"    {metric_name}: column not found")
            continue

        # Split at GA ban
        pre_mask = voat_df["month_dt"] < GA_BAN_DATE
        post_mask = voat_df["month_dt"] >= GA_BAN_DATE

        pre_data = voat_df.loc[pre_mask, metric_col].values
        post_data = voat_df.loc[post_mask, metric_col].values

        # Run permutation test
        result = block_permutation_test(
            pre_data, post_data,
            n_permutations=N_PERMUTATIONS,
            block_size=BLOCK_SIZE,
            seed=RANDOM_SEED
        )

        results.append({
            "community": "global",
            "metric": metric_name,
            "pre_mean": np.nanmean(pre_data),
            "post_mean": np.nanmean(post_data),
            "observed_diff": result["observed_diff"],
            "p_value": result["p_value"],
            "n_pre": result["n_pre"],
            "n_post": result["n_post"]
        })

        print(f"    {metric_name}:")
        print(f"      Pre-GA mean: {np.nanmean(pre_data):.4f} (n={result['n_pre']})")
        print(f"      Post-GA mean: {np.nanmean(post_data):.4f} (n={result['n_post']})")
        print(f"      Difference: {result['observed_diff']:.4f}")
        print(f"      p-value: {result['p_value']:.4f}")

    # Per-community tests (for E-I index which varies by community)
    print("\n  PER-COMMUNITY E-I Index:")
    for comm in COMMUNITIES:
        voat_path = RESULTS_ROOT / "compare" / comm / f"{comm}_monthly_metrics.csv"
        if not voat_path.exists():
            continue

        comm_df = pd.read_csv(voat_path)
        if "month" not in comm_df.columns:
            continue

        comm_df["month_dt"] = pd.to_datetime(comm_df["month"] + "-01")
        comm_df = comm_df[comm_df["month_dt"] >= "2015-06-01"].copy()

        # Find E-I column
        ei_col = None
        for col in ["ei_index", "ei_index_voat", "voat_ei_index"]:
            if col in comm_df.columns:
                ei_col = col
                break

        if ei_col is None:
            continue

        pre_mask = comm_df["month_dt"] < GA_BAN_DATE
        post_mask = comm_df["month_dt"] >= GA_BAN_DATE

        pre_data = comm_df.loc[pre_mask, ei_col].values
        post_data = comm_df.loc[post_mask, ei_col].values

        result = block_permutation_test(
            pre_data, post_data,
            n_permutations=N_PERMUTATIONS,
            block_size=BLOCK_SIZE,
            seed=RANDOM_SEED
        )

        results.append({
            "community": comm,
            "metric": "E-I Index",
            "pre_mean": np.nanmean(pre_data),
            "post_mean": np.nanmean(post_data),
            "observed_diff": result["observed_diff"],
            "p_value": result["p_value"],
            "n_pre": result["n_pre"],
            "n_post": result["n_post"]
        })

        sig = "*" if result["p_value"] < 0.05 else ""
        print(f"    {comm}: diff={result['observed_diff']:+.3f}, p={result['p_value']:.4f}{sig}")

    return pd.DataFrame(results)


def apply_fdr_correction(results_df: pd.DataFrame) -> pd.DataFrame:
    """Apply Benjamini-Hochberg FDR correction to p-values."""
    print("\n" + "=" * 60)
    print("FDR CORRECTION (Benjamini-Hochberg)")
    print("=" * 60)

    if "p_value" not in results_df.columns:
        print("  No p_value column found")
        return results_df

    p_values = results_df["p_value"].values
    adjusted_p = benjamini_hochberg(p_values)

    results_df = results_df.copy()
    results_df["p_value_fdr"] = adjusted_p
    results_df["significant_raw"] = results_df["p_value"] < 0.05
    results_df["significant_fdr"] = results_df["p_value_fdr"] < 0.05

    print(f"\n  Total tests: {len(p_values)}")
    print(f"  Significant (raw α=0.05): {sum(results_df['significant_raw'])}")
    print(f"  Significant (FDR α=0.05): {sum(results_df['significant_fdr'])}")

    print("\n  Results:")
    for _, row in results_df.iterrows():
        sig_raw = "*" if row["significant_raw"] else ""
        sig_fdr = "†" if row["significant_fdr"] else ""
        print(f"    {row['community']:12} {row['metric']:12}: "
              f"p={row['p_value']:.4f}{sig_raw} → p_fdr={row['p_value_fdr']:.4f}{sig_fdr}")

    return results_df


def main():
    """Run all statistical analyses."""
    print("=" * 60)
    print("STATISTICAL ANALYSIS FOR REDDIT-VOAT PAPER")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. Effect sizes
    effect_sizes_df = compute_toxicity_effect_sizes()

    # 2. Permutation tests
    permutation_df = compute_regime_permutation_tests()

    # 3. FDR correction
    permutation_df = apply_fdr_correction(permutation_df)

    # Save results
    output_dir = RESULTS_ROOT / "statistics"
    output_dir.mkdir(parents=True, exist_ok=True)

    effect_sizes_path = output_dir / "effect_sizes.csv"
    permutation_path = output_dir / "permutation_tests.csv"

    effect_sizes_df.to_csv(effect_sizes_path, index=False)
    permutation_df.to_csv(permutation_path, index=False)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print("\n  Effect Sizes (Toxicity: Voat vs Reddit):")
    for _, row in effect_sizes_df.iterrows():
        print(f"    {row['community']:12}: Cliff's δ = {row['cliffs_delta']:+.3f} ({row['interpretation']})")

    print(f"\n  Results saved to:")
    print(f"    {effect_sizes_path}")
    print(f"    {permutation_path}")

    return effect_sizes_df, permutation_df


if __name__ == "__main__":
    effect_df, perm_df = main()
