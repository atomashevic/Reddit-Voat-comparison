# Migration Analysis Data Dictionary

This document records the schema for new outputs generated on 2025-11-08.

## `results/basic/compare/results/group_month_validity.csv`
- `platform, community, month, group`: identifiers
- `member_count`: users in group-month
- `mean_*`: behavior metrics (toxicity, sentiment, subjectivity, reputation)
- `valid_member_count`: bool flag (member_count ≥ 20)
- `group_min_member_threshold`: effective threshold per row (Voat cores default to 5; all other groups default to 20)
- `num_metrics_missing`, `metrics_missing_ratio`: NA counts across behavior metrics
- `validation_reason`: semicolon summary describing failed checks
- `min_member_threshold`: deprecated (mirrors `group_min_member_threshold` for backward compatibility)
- `qa_*`: NA rates and coverage from QA summaries when available

## `results/basic/<community>/compare/results/<community>_monthly_diffs.csv`
- `voat_value`: Voat group-month metric
- `reddit_p5/p25/p50/p75/p95`: Reddit-at-Voat-scale bootstrap percentiles
- `diff_voat_minus_reddit_median`: difference vs median
- `valid_member_count`, `member_count`: included for filtering

## `results/basic/<community>/compare/results/<community>_event_windows.csv`
- Extends monthly diff table with `event`, `event_variant` (`actual` vs `placebo`), `anchor_month`, `event_description`, `offset` (months relative to anchor)

- `results/basic/<community>/compare/results/<community>_event_window_summary.csv`
- `event_variant` distinguishes actual deplatforming anchors vs placebo windows shifted six months earlier.
- `pre/post_diff_mean`: average Voat-minus-Reddit diff within [-6,-1] vs [0,+12]
- `pre/post_diff_ci_low/high`: bootstrap 5th/95th percentiles of the mean
- `pre/post_voat_mean` + CI: same windows using absolute Voat values
- `n_pre`, `n_post`: months contributing to windows

## `results/basic/compare/results/periphery_exceedance_summary.csv`
- `months_available`: count of valid Voat periphery months with bootstrap coverage
- `months_exceeding`: months where Voat toxicity > Reddit 95th percentile
- `share_exceeding` (fraction) and `_percent`
- Includes `ALL` aggregate row

## `results/basic/<community>/compare/results/<community>_periphery_exceedance_monthly.csv`
- Month-level subset of `monthly_diffs` with `exceeds_95` boolean and bootstrap columns

## `results/basic/<community>/compare/results/<community>_composition_decomposition.csv`
- `member_count`, `newcomer_count`, `incumbent_count`, `share_newcomers`
- `overall_mean`, `mean_newcomers`, `mean_incumbents`: toxicity averages
- `delta_overall`: month-over-month change
- `composition_component`, `newcomer_behavior_component`, `incumbent_behavior_component`, `residual_component`: Oaxaca-style decomposition pieces
- `valid_member_count`: threshold flag (≥ 20)

## `results/basic/<community>/compare/results/<community>_sensitivity.csv`
- Reuses original group metrics plus:
  - `member_count_comments`: users observed via comments/replies only
  - `mean_toxicity_comments`: comment-only per-user average
  - `delta_toxicity_comments_minus_all`: difference vs posts+comments baseline

## `results/basic/compare/results/behavior_significance_summary.csv`
- Output from `scripts/behavior_significance.py`
- Columns: `community`, `group`, `metric`, `n_months`, `mean_diff`, `median_diff`, `share_positive`, `stouffer_z`, `p_value`, `p_value_bonferroni`, `p_value_fdr`
- Provides combined significance tests for Voat-minus-Reddit differences (Stouffer's method) with Bonferroni and BH adjustments across 60 comparisons.

## `results/basic/compare/results/reddit_bootstrap_coverage.csv`
- Output from `scripts/behavior_bootstrap_coverage.py`
- Coverage ratios for Reddit months relative to Voat-scale bootstrap percentile bands per community/group/metric.
- Columns: `n_months`, `coverage_5_95`, `coverage_25_75`; includes an aggregate `ALL` row.

## `results/toxicity/compare/results/toxicity_calibration_summary.csv`
- `total_rows`, `non_null_rows`, `missing_share`
- `q_10`, `q_25`, `q_50`, `q_75`, `q_90`: annual toxicity quantiles per platform/community
- `share_ge_0_5`, `share_ge_0_8`: share of interactions above thresholds

## `results/core-periphery/compare/results/core_periphery_stability_summary.csv`
- Aggregates `_cp_stability.csv` outputs for Reddit and Voat.
- Columns: `pairs` (window pairs), `median_jaccard_core`, `median_label_agreement_pct`, `share_common_nodes_ge_10`, `share_jaccard_ge_0_2`.

All CSVs use ISO `YYYY-MM` months; event offsets are integers (months relative to anchor). Figures derived from these tables should cite the file path and column names referenced above.
