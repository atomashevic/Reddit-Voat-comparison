# Analysis traceability index (paper ↔ code ↔ outputs)

This repo contains many historical pipelines (notably under `backup/`). The paper in
`paper/main.tex` depends on a small, well-defined set of artifacts. This document maps:

- **Paper artifacts** → **output files** → **scripts that generate them** (and upstream dependencies)
- **Scripts** → whether they are **paper-critical**, **paper-supporting**, or **legacy/unused**

## Paper-used artifacts (from `paper/main.tex`)

### Figures

- **Fig. 1** (`\ref{fig:global_summary}`)
  - **File**: `paper/figures/global/voat_global_summary.png`
  - **Rendered by**: `scripts/plot_global_summary.py`
  - **Inputs**:
    - `results/global/voat_global_aggregate.csv` (global aggregation)
    - `results/global/event_period_toxicity_diff.csv` (heatmap panel)
    - `results/voat/global/voat_global_newcomer_degree_dynamics.csv` (hub-rate + degree-share panels)
  - **Upstream producers**:
    - `scripts/aggregate_global_metrics.py`
    - `scripts/compute_event_period_toxicity.py`
    - `scripts/compute_newcomer_degree_dynamics.py`

- **Fig. 2–7** (community overview figures; `\ref{fig:funny_overview}` and Appendix overviews)
  - **Files**:
    - `paper/figures/compare/funny/funny_overview.png`
    - `paper/figures/compare/gaming/gaming_overview.png`
    - `paper/figures/compare/gifs/gifs_overview.png`
    - `paper/figures/compare/pics/pics_overview.png`
    - `paper/figures/compare/videos/videos_overview.png`
    - `paper/figures/compare/technology/technology_overview.png`
  - **Rendered by**: `scripts/plot_overview.py`
  - **Inputs (per community)**:
    - `results/compare/<community>/<community>_monthly_metrics.csv`
  - **Upstream producers (per community)**:
    - `scripts/merge_overview_metrics.py` (joins monthly aggregates + bootstrap bands + E–I index)
    - `scripts/aggregate_monthly_metrics_global.py` (monthly aggregates from user-month metrics + network metrics)
    - `scripts/compare_global_bootstrap.py` (bootstrap bands for toxicity/sentiment)
    - `scripts/identify_voat_newcomers.py` + `scripts/analyze_monthly_newcomers.py` (E–I index / cohort partition)
    - `scripts/build_global_monthly_metrics_lowmem.py` (user-month metrics from Parquet; low-memory DuckDB path)
    - `scripts/compute_global_network_metrics.py` (monthly network metrics from edge lists)

### Tables

The current `paper/main.tex` embeds table numbers directly as LaTeX literals (it does **not**
`\input{}` tables from CSV). For reviewer traceability, the recommended next step is to:

- Generate tables into `paper/tables/*.tex` from the CSVs under `results/`
- Replace the hard-coded table bodies with `\input{paper/tables/<table>.tex}`

Relevant supporting outputs already exist:

- **Breakpoint summary / details**: `results/basic/compare/results/regime_breakpoints.csv`
  - Producer: `scripts/regime_break_analysis.py`
- **Hub-threshold robustness**: `results/basic/compare/results/c1_hub_threshold_sensitivity_global.csv`
  - Producer: `scripts/hub_threshold_sensitivity.py`
- **Rolling-tenure E–I robustness**: `results/basic/compare/results/c2_ei_rolling_tenure6_global.csv`
  - Producer: `scripts/rolling_cohort_ei_sensitivity.py`

## “One command” reproduction entrypoint (paper figures)

- **Recommended**: `bash scripts/run_all_pipelines.sh`
  - Builds community-level inputs + global aggregation + writes paper-ready figures into `paper/figures/`

## Script inventory (what’s essential vs legacy)

### Paper-critical (directly required to regenerate paper figures)

- `scripts/run_all_pipelines.sh`
- `scripts/run_alternative_pipeline.sh`
- `scripts/build_global_monthly_metrics_lowmem.py`
- `scripts/compute_global_network_metrics.py`
- `scripts/aggregate_monthly_metrics_global.py`
- `scripts/compare_global_bootstrap.py`
- `scripts/identify_voat_newcomers.py`
- `scripts/analyze_monthly_newcomers.py`
- `scripts/merge_overview_metrics.py`
- `scripts/plot_overview.py`
- `scripts/aggregate_global_metrics.py`
- `scripts/compute_event_period_toxicity.py`
- `scripts/compute_newcomer_degree_dynamics.py`
- `scripts/plot_global_summary.py`
- `scripts/migration_utils.py`

### Paper-supporting (robustness / mechanism validation used in Results/Appendix narrative)

- `scripts/regime_break_analysis.py`
- `scripts/regime_volume_integration_panel.py`
- `scripts/hub_threshold_sensitivity.py`
- `scripts/rolling_cohort_ei_sensitivity.py`

### Utility (not part of results, but useful on the remote machine)

- `scripts/resource_monitor.py`

### Likely legacy / not referenced by the current paper pipeline

- `scripts/restructure_results.sh` (no references; appears to be a one-off organizer)
- `scripts/compute_q90_toxicity.py` (produces `results/global/q90_toxicity.csv`, not used in `paper/main.tex`)

## Notes on `backup/`

This repo keeps historical workspace in `backup/` for prior pipelines (core-periphery, entropy, etc.).

**Reputation data has been moved**: Daily reputation parquets are now under `results/reputation/` (moved from `backup/results/reputation/`). These files are too large for GitHub (~400GB total) and are ignored by `.gitignore`.


