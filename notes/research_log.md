# Research Log

## 2025-11-08

- [09:58 UTC] Event: Kickoff, requirements review, backups created.
  - New information: Existing summaries and results snapped to `backups/2025-11-08T0955Z/` (includes memos, results/basic, core-periphery compare outputs).
  - Lessons learned: `rsync` unavailable in this environment—use `cp -r` for backups and document tool availability before scripting.
- [10:05 UTC] Event: Implemented automated group-month QA filters via `scripts/migration_filters.py`.
  - New information: Generated `results/basic/compare/results/group_month_validity(.csv|_summary.csv)` with member-count validity flags and NA coverage placeholders; confirmed only gaming had prior QA file, so script infers missing-data ratios directly.
  - Lessons learned: Existing metrics already carry `community` column—helper utilities must check before inserting to avoid pandas errors.
- [09:58 UTC] Event: Built Voat-vs-Reddit monthly diff panels and event windows using `scripts/migration_event_windows.py`.
  - New information: Produced per-community monthly diff tables plus event-window summaries (pre/post window means with bootstrap CIs) under `results/basic/<community>/compare/results/`.
  - Lessons learned: Period arithmetic in pandas requires ordinal conversions; subtracting PeriodIndex directly returns offsets rather than ints.
- [10:07 UTC] Event: Recomputed Voat periphery exceedance stats via `scripts/migration_exceedance.py`.
  - New information: `results/basic/compare/results/periphery_exceedance_summary.csv` shows updated fractions (e.g., videos 87%, technology 31%) after enforcing member-count threshold; monthly booleans stored alongside each community.
  - Lessons learned: Centralizing monthly diffs simplifies downstream re-use—only toxicity metric needed double-check for nulls when bootstrap data unavailable.
- [10:18 UTC] Event: Generated newcomer composition decompositions via `scripts/migration_composition.py`.
  - New information: Stored Voat user-month metrics (`results/basic/<community>/voat/results/voat_<community>_user_month_metrics.parquet`) and per-group decomposition tables capturing composition vs behavior components.
  - Lessons learned: DuckDB’s `strftime` expects plain timestamps; explicit casts avoid timezone issues when deriving monthly buckets.
- [10:32 UTC] Event: Ran comments-only sensitivity with `scripts/migration_sensitivity.py`.
  - New information: `results/basic/<community>/compare/results/<community>_sensitivity.csv` contrast comment-only toxicity against posts+comments for both platforms (delta column shows magnitude per month).
  - Lessons learned: DuckDB joins directly to CP labels make it feasible to aggregate large Reddit files without materializing user-month tables.
- [10:45 UTC] Event: Produced toxicity calibration summary via `scripts/migration_toxicity_calibration.py`.
  - New information: `results/toxicity/compare/results/toxicity_calibration_summary.csv` now reports yearly quantiles, missing-share, and high-toxicity tail stats per platform/community.
  - Lessons learned: DuckDB's `quantile_cont` works efficiently on full Parquet files—no need for sampling to get platform-wide distributions.
- [10:52 UTC] Event: Updated documentation artifacts.
  - New information: `notes/migration_analysis_plan.md` now lists full script commands; `notes/migration_data_dictionary.md` describes output schemas.
  - Lessons learned: Centralizing schema notes prevents future guesswork when analysts consume CSV outputs.
- [11:05 UTC] Event: Revised research summary + behavior + networks memos.
  - New information: Causal language replaced with descriptive statements; memos now cite new outputs (event windows, exceedance summary, composition, calibration).
  - Lessons learned: Maintaining per-community medians prevents overstated generalizations (e.g., technology behaves differently from videos).
