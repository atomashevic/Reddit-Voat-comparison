# Toxicity Robustness Reviewer-Response Note

Measurement model:
- Latent construct: toxic, hateful, abusive, or demeaning discourse.
- Observed input: Voat posts and comments with timestamps and user IDs.
- Instrument output: RoBERTa ToxiGen probability in [0, 1].
- Noise/error: domain shift, coded Voat-specific language, calibration drift, and user/post aggregation choices.
- Downstream estimand: longitudinal changes in mean ToxiGen probabilities, not manually observed toxicity prevalence.

Evidence files:
- `results/toxicity/compare/results/toxicity_cohort_decomposition_summary.csv`
- `results/toxicity/compare/results/toxicity_weighting_comparison_summary.csv`
- `results/toxicity/compare/results/toxicity_weekly_event_window_summary.csv`
- `results/toxicity/compare/results/toxicity_weekly_prepost_change_summary.csv`
- `results/toxicity/compare/figures/toxicity_cohort_decomposition_global.png`
- `results/toxicity/compare/figures/toxicity_weekly_event_window_global.png`

Key descriptive results:
- Equal-user and activity-weighted global monthly estimates are highly aligned (Pearson r=0.9929; mean activity-minus-equal difference=-0.0225).
- Across global months where both groups are observed, newcomer minus existing equal-user mean ToxiGen probability averages 0.0100 (median 0.0112).
- Weekly global all-user post-minus-pre changes by event:
  - FPH: equal-user 0.0175; activity-weighted 0.0171.
  - Pizzagate: equal-user 0.0097; activity-weighted 0.0180.
  - GreatAwakening: equal-user 0.0138; activity-weighted 0.0092.
  - The_Donald: equal-user 0.0084; activity-weighted 0.0072.

Reviewer-response framing:
- R1-M3: report both equal-user and activity-weighted mean ToxiGen probabilities and state whether the two estimands align.
- R1-M7: replace `toxicity doubled` with `mean ToxiGen classifier probability approximately doubled`.
- R2-5 / PDF M7: cite Hartvigsen et al. (2022) for ToxiGen validation and explicitly acknowledge platform/domain-shift limits; no manual validation sample was added.
- R2-7.1: use the monthly newcomer-vs-existing decomposition as the cohort toxicity evidence.
- R2-7.2: use the weekly event-window table/figure as the short-term post-ban evidence.
