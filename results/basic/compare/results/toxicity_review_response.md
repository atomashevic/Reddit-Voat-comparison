# Toxicity Robustness Reviewer-Response Note

Measurement model:
- Latent construct: toxic, hateful, abusive, or demeaning discourse.
- Observed input: Voat posts and comments with timestamps and user IDs.
- Instrument output: RoBERTa ToxiGen probability in [0, 1].
- Noise/error: domain shift, coded Voat-specific language, calibration drift, and user/post aggregation choices.
- Downstream estimand: longitudinal changes in mean ToxiGen probabilities, not manually observed toxicity prevalence.

Evidence files:
- `results/basic/compare/results/toxicity_cohort_decomposition_summary.csv`
- `results/basic/compare/results/toxicity_weighting_comparison_summary.csv`
- `results/basic/compare/results/toxicity_monthly_paired_interval_summary.csv`
- `results/basic/compare/results/toxicity_cross_platform_ratio_uncertainty.csv`
- `results/basic/compare/results/toxicity_weekly_event_window_summary.csv`
- `results/basic/compare/results/toxicity_weekly_prepost_change_summary.csv`
- `results/basic/compare/results/toxicity_weekly_activity_spike_summary.csv`
- `results/basic/compare/figures/toxicity_cohort_decomposition_global.png`
- `results/basic/compare/figures/toxicity_weekly_event_window_global.png`
- `results/basic/compare/results/toxicity_detoxify_toxigen_voat_correlation_summary.csv`

Key descriptive results:
- Equal-user and activity-weighted global monthly estimates are highly aligned (Pearson r=0.9929; mean activity-minus-equal difference=-0.0225).
- Across global months where both groups are observed, newcomer minus existing equal-user mean ToxiGen probability averages 0.0100 (median 0.0112).
- Autocorrelation-aware intervals for the global monthly paired differences support the same descriptive interpretation: activity-weighted minus equal-user mean=-0.0225, MBB 95% CI [-0.0285, -0.0173], HAC 95% CI [-0.0286, -0.0164]; newcomer minus existing equal-user mean=0.0100, MBB 95% CI [0.0023, 0.0192], HAC 95% CI [0.0016, 0.0184].
- Cross-platform Voat/Reddit mean ToxiGen probability ratios remain descriptive rather than causal. Moving-block bootstrap intervals for all available months place 5/6 community ratios above 1.0; technology is the exception where the interval includes 1.0.
- Supplementary convergent-validity check: on Voat, Detoxify unbiased toxicity scores are strongly positively associated with ToxiGen probabilities for all posts (n=368,727, Pearson r=0.6935, Spearman rho=0.6528), all comments (n=785,746, Pearson r=0.7153, Spearman rho=0.7375), and a stratified 1k post sample (Pearson r=0.7284, Spearman rho=0.6436).
- Weekly global all-user post-minus-pre changes by event:
  - FPH: equal-user 0.0175; activity-weighted 0.0171.
  - Pizzagate: equal-user 0.0097; activity-weighted 0.0180.
  - GreatAwakening: equal-user 0.0138; activity-weighted 0.0092.
  - The_Donald: equal-user 0.0084; activity-weighted 0.0072.
- Weekly global all-user activity-volume changes by event:
  - FPH: post/pre activity ratio 12.4025; event-week/pre activity ratio 3.3999; max post-week/pre activity ratio 30.4257.
  - Pizzagate: post/pre activity ratio 1.1264; event-week/pre activity ratio 1.0176; max post-week/pre activity ratio 1.3934.
  - GreatAwakening: post/pre activity ratio 1.2381; event-week/pre activity ratio 1.0880; max post-week/pre activity ratio 1.5348.
  - The_Donald: post/pre activity ratio 0.9513; event-week/pre activity ratio 1.1243; max post-week/pre activity ratio 1.1243.

Reviewer-response framing:
- R1-M3: report both equal-user and activity-weighted mean ToxiGen probabilities and state whether the two estimands align.
- R1-M7: replace `toxicity doubled` with `mean ToxiGen classifier probability approximately doubled`.
- R2-5 / PDF M7: cite Hartvigsen et al. (2022) for ToxiGen validation and explicitly acknowledge platform/domain-shift limits; add the Detoxify/ToxiGen Voat correlation table as supplementary convergent-validity evidence. This is not a manual gold-standard validation sample.
- R1-S1/R2-6: report uncertainty for cross-platform toxicity ratios and state that Reddit is a descriptive reference series, not a causal baseline.
- R2-7.1: use the monthly newcomer-vs-existing decomposition as the cohort toxicity evidence.
- R2-7.2: use the weekly event-window table/figure as the short-term post-ban evidence.
- R2-4: use the weekly activity-spike table to answer whether there were immediate post-ban volume spikes around each event.
