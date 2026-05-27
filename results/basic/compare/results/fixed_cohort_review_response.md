# Fixed-cohort reviewer-response evidence

Generated for TODO item 2: longitudinal cohort analysis. This note is evidence
for revision planning only; it does not modify the manuscript.

## Evidence files

- `scripts/longitudinal_cohort_analysis.py`
- `results/basic/compare/results/fixed_cohort_structural_ascent_summary.csv`
- `results/basic/compare/results/fixed_cohort_retention_toxicity_summary.csv`
- `results/basic/compare/results/postban_proxy_noise_summary.csv`
- `results/basic/compare/figures/fixed_cohort_degree_share_ratio.png`
- `results/basic/compare/figures/fixed_cohort_retention_by_toxicity.png`

Per-community user/month detail tables are intentionally not retained in the
PR artifact set because they are intermediate outputs. They can be regenerated
with `python scripts/longitudinal_cohort_analysis.py --write-detail-tables`.

## Reviewer/editor items addressed

### Editor: longitudinal cohort analysis

The new analysis follows fixed arrival cohorts across later months instead of
resetting labels at each ban. Cohorts are chronological and fixed by first Voat
activity:

- `pre_fph`: before 2015-06-10
- `fph_pg`: 2015-06-10 to before 2016-11-23
- `pg_ga`: 2016-11-23 to before 2018-09-12
- `ga_td`: 2018-09-12 to before 2020-06-29
- `td_shutdown`: 2020-06-29 onward

This directly answers whether users who arrived after an event later became
central. It should be added as a Methods subsection and a short Results
subsection.

### Reviewer concern: permanent structural marginalization

The fixed-cohort evidence does not support a blanket claim that arrivals
remained permanently marginalized.

Across the six communities, median degree-share ratio by cohort is:

| Cohort | Median degree-share ratio | Mean share of months under-represented | Mean hub rate |
|---|---:|---:|---:|
| `pre_fph` | 3.6814 | 0.0262 | 0.3665 |
| `fph_pg` | 0.9755 | 0.5100 | 0.1249 |
| `pg_ga` | 0.9761 | 0.5500 | 0.1109 |
| `ga_td` | 0.7684 | 0.9226 | 0.0748 |
| `td_shutdown` | 0.6576 | 1.0000 | 0.0442 |

Interpretation:

- Pre-FPH users remain structurally over-represented.
- FPH-PG and PG-GA cohorts are close to proportional representation, not
  consistently marginalized.
- GA-TD and TD-shutdown cohorts are consistently under-represented.
- The manuscript should replace permanent-marginalization language with a
  temporally specific claim: later arrival cohorts are under-represented among
  high-degree users, while earlier post-FPH/PG cohorts partially integrated.

### Reviewer concern: hub capture versus peripheral mechanism

User-level ever-hub rates are below or near the 10% equality baseline for most
post-ban cohorts:

| Cohort | Mean user ever-hub rate | High-activity ever-hub rate |
|---|---:|---:|
| `fph_pg` | 0.0958 | 0.3170 |
| `pg_ga` | 0.0775 | 0.2111 |
| `ga_td` | 0.0650 | 0.1959 |
| `td_shutdown` | 0.0465 | 0.1899 |

Interpretation:

- Average post-ban users do not show broad hub capture.
- High-activity arrivals are much more likely to become hubs.
- The manuscript should avoid saying peripheral dynamics were proven. A safer
  formulation is: the evidence is inconsistent with broad hub capture, but
  high-activity arrivals form an important exception and should be discussed as
  a likely mechanism for concentrated influence.

### Reviewer concern: high-activity newcomers

The high-activity split materially changes interpretation. High-activity
arrival users reach hub status at roughly 19-32% across post-ban cohorts, far
above the average cohort rates. This should be reported explicitly because it
shows that "newcomers" are heterogeneous and that influence is concentrated
among active arrivals rather than uniformly peripheral.

Suggested manuscript change:

- Add a sentence after hub-rate results: "A fixed-cohort robustness check shows
  that average post-ban cohorts rarely achieve hub status, but users in the top
  decile of first-month activity do so much more often, indicating substantial
  heterogeneity among arrivals."

### Reviewer concern: survival of toxic users

Retention evidence is cohort-dependent. Mean high-minus-lower toxicity
differences across communities are:

| Cohort | 3-month retention difference | 12-month retention difference | Ever-hub-rate difference |
|---|---:|---:|---:|
| `fph_pg` | +0.2231 | +0.1473 | +0.0504 |
| `pg_ga` | +0.1382 | +0.0979 | +0.0032 |
| `ga_td` | +0.0127 | -0.0006 | -0.0215 |
| `td_shutdown` | -0.0159 | 0.0000 | -0.0179 |

Interpretation:

- Early high-toxicity arrivals persist longer, especially in the FPH-PG and
  PG-GA cohorts.
- This pattern weakens or disappears in later cohorts.
- The manuscript can report this descriptively, but should not frame it as a
  causal survival model unless a fuller time-to-event model is added.

### Reviewer concern: proxy noise in post-ban arrival labels

The proxy-noise check shows the arrival proxy is strongest for FPH and much
weaker for later events:

| Event | Observed first users in event+2 months | Expected from baseline | Excess users | Mean proxy-noise upper bound |
|---|---:|---:|---:|---:|
| FPH | 17,075 | 1,093.5 | 15,981.5 | 0.0619 |
| Pizzagate | 3,507 | 3,369.0 | 458.5 | 0.8930 |
| GreatAwakening | 2,948 | 2,176.5 | 771.5 | 0.7924 |
| The_Donald | 2,024 | 1,932.0 | 210.5 | 0.9338 |

Interpretation:

- The FPH arrival wave is very large relative to prior monthly arrivals.
- Later event windows have high estimated organic/noise shares.
- The manuscript should state that fixed cohorts are event-timed arrivals, not
  verified Reddit migrants, and that this proxy is much cleaner for FPH than
  for later events.

## Recommended manuscript positioning

Do not claim that all newcomers stayed peripheral. The revised mechanism should
be:

> Post-ban arrival cohorts were not uniformly hub-capturing. Early FPH/PG
> arrivals reached near-proportional degree representation, while later GA/TD
> arrivals were consistently under-represented among high-degree users. Within
> all post-ban cohorts, high-activity arrivals were much more likely to become
> hubs than average arrivals. Thus, the fixed-cohort analysis supports a
> heterogeneous mechanism: broad arrival volume changed participation
> composition, while influence was concentrated among the most active arrivals.

This answers the reviewer more accurately than the original "peripheral
dynamics rather than hub capture" formulation.
