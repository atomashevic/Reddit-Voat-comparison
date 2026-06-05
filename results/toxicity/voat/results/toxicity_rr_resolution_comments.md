# RR TODO Evidence Map

Evidence entries in this document are restricted to manuscript figures/tables,
supplementary figures/tables, or manuscript text modifications. CSV files and
scripts are implementation/source artifacts, not evidence.

# PRs Reviewed

## PR #1 Refactor repository structure

### Answer

Infrastructure PR. It does not directly answer a reviewer issue in the RR
package.

**Evidence:** none needed for RR response.

## PR #2 Claude PR Assistant workflow

### Answer

Infrastructure PR. It does not directly answer a reviewer issue in the RR
package.

**Evidence:** none needed for RR response.

## PR #3 Fixed-cohort retention analysis

### Answer

Directly supports the longitudinal cohort, survival/retention, and hub-ascent
responses. It is central to the revised mechanism claim because it follows fixed
arrival cohorts across later months, compares high versus lower early-toxicity
retention, and separates average arrivals from high-activity arrivals.

**Evidence:** manuscript figure `Fixed-cohort Kaplan-Meier survival by early toxicity`; manuscript table `Fixed-cohort retention and hub-ascent summary`; supplementary table `Toxicity-definition sensitivity`; supplementary table `Hub-definition sensitivity`.

## PR #4 Regime validation upgrade

### Answer

Supports the causal-framing and regime-validation response. It turns breakpoint
analysis into the explicit test of ban alignment and helps distinguish metrics
with ban-aligned evidence from gradual longitudinal trends.

**Evidence:** manuscript or supplementary figure `Global segmented-fit breakpoint visualization`; manuscript or supplementary table `Regime model comparison`; text modification `Breakpoint validation is the explicit ban-alignment test`.

## PR #5 Mechanism clarification note

### Answer

Supports the narrowing of mechanism language. It connects structural ascent,
degree-share ratio, retention/toxicity, and proxy-noise evidence into a smaller
claim: average arrivals do not broadly capture hubs, while high-activity arrivals
are more likely to become structurally central.

**Evidence:** manuscript figure `Fixed-cohort degree-share ratio`; manuscript or supplementary figure `Fixed-cohort retention by toxicity`; text modification `replace permanent marginalization/peripheral proof with concentrated active-arrival mechanism`.

## PR #6 Toxicity robustness analysis

### Answer

Supports the activity-weighted toxicity, cohort decomposition, short-window
dynamics, classifier wording, and toxicity-uncertainty responses. It is mostly a
robustness package; some outputs should become supplementary figures/tables
rather than main-text evidence.

**Evidence:** supplementary figure `Toxicity cohort decomposition`; supplementary figure `Weekly toxicity event-window dynamics`; supplementary table `Activity-weighted versus equal-user toxicity`; text modification `mean ToxiGen classifier probability, not observed toxicity prevalence`.

## PR #7 Toxicity per cohorts

### Answer

Exploratory precursor to the current cohort-toxicity follow-up. By itself it is
not clean manuscript evidence because it is a notebook, but it motivated the
standardized A-D+ cohort summary and all-community figures in the current branch.

**Evidence:** none directly from PR #7; current branch supplies the manuscript or supplementary figure/table.

## PR #8 Weekly toxicity event-window analysis

### Answer

Directly supports the short-term post-ban dynamics response. It complements the
current A-D+ cohort summary by showing event-window dynamics around bans.

**Evidence:** supplementary figure `Weekly toxicity event-window by cohort`; supplementary table `Weekly event-window pre/post summary`; text modification `short-term dynamics are event-specific and descriptive`.

# Reviewer 1

## M3. Report activity-weighted toxicity alongside the equal-weighted measure

### Answer

Addressed. The cohort-toxicity batch reports both equal-user and
activity-weighted mean ToxiGen classifier probabilities by fixed arrival cohort.
The later-cohort gradient remains under activity weighting, so the result is not
only an artifact of giving low-activity users equal weight.

For the main paper, the cleanest presentation is the all-community A-D+ barplot.
For the supplement, include the time-series figure and, if space allows, a
table with the exact A-D+ values.

**Evidence:** manuscript or supplementary figure `A-D+ cohort toxicity by arrival cohort`; manuscript or supplementary table `A-D+ cohort toxicity summary`; text modification `report equal-user and activity-weighted toxicity side by side`.

## M7. Qualify the "toxicity doubled" statement

### Answer

Partially addressed by the new analysis language; manuscript text still needs to
be changed. All new toxicity outputs are framed as mean ToxiGen classifier
probabilities, not proportions of toxic content.

The manuscript should replace unqualified "toxicity doubled" wording with
"mean ToxiGen classifier probability increased" or "mean ToxiGen classifier
probability approximately doubled," depending on the specific sentence.

**Evidence:** text modification `replace toxicity doubled with mean ToxiGen classifier probability increased`; text modification `caption tables and figures as classifier probabilities`.

## Request for cohort toxicity decomposition

### Answer

Addressed. The current batch provides the compact decomposition requested: user
counts, activity counts, equal-user toxicity, and activity-weighted toxicity by
fixed arrival cohort over the full post-FPH A-D+ period.

Core all-community values for the manuscript or supplement:

| Cohort | Active users | Activity count | Equal-user mean ToxiGen probability | Activity-weighted mean ToxiGen probability |
|---|---:|---:|---:|---:|
| Before A | 641 | 51,765 | 0.105 | 0.080 |
| A-B | 23,389 | 221,299 | 0.103 | 0.136 |
| B-C | 14,232 | 101,432 | 0.172 | 0.208 |
| C-D | 10,468 | 55,163 | 0.227 | 0.246 |
| D+ | 1,654 | 5,436 | 0.266 | 0.259 |

Interpretation: later arrival cohorts have higher mean ToxiGen classifier
probabilities over A-D+. The pattern is visible under both estimands, so the
cohort gradient is not solely an equal-user weighting artifact.

**Evidence:** manuscript or supplementary figure `A-D+ cohort toxicity by arrival cohort`; manuscript or supplementary table `A-D+ cohort toxicity summary`.

## Short-term post-ban dynamics

### Answer

Addressed by PR #8 and contextualized by the current batch. PR #8 answers the
short-window question around bans. The current rolling 30-day cohort time series
shows the longer longitudinal context: toxicity changes gradually, and cohorts
move within that broader platform environment.

This distinction is important for framing. The weekly event-window figure can
answer event-specific dynamics, while the rolling time-series figure should be
used as descriptive context rather than a ban-alignment test.

**Evidence:** supplementary figure `Weekly toxicity event-window by cohort`; supplementary table `Weekly event-window pre/post summary`; supplementary figure `Rolling cohort toxicity trajectories`; text modification `short-term dynamics are event-specific; long-run toxicity is gradual`.

# Reviewer 2

## E1. Bring causal framing in line with the descriptive design

### Answer

Partially addressed. The toxicity time series reinforces the descriptive
framing: toxicity changes gradually and cohort trajectories move within the
broader platform environment. This does not support a simple causal sentence
that Reddit bans caused toxicity increases.

Recommended wording:

> Toxicity increased gradually across Voat's generalist communities during a
> period containing major Reddit community bans. Later arrival cohorts entered
> and participated in an increasingly toxic discourse environment.

Avoid:

- "Reddit bans caused toxicity increases"
- "hostile takeover" as a mechanism claim
- "toxicity spillover" unless explicitly framed as descriptive and proxy-based

**Evidence:** supplementary figure `Rolling cohort toxicity trajectories`; text modification `replace causal ban-shock framing with descriptive longitudinal framing`; text modification `state that breakpoint analysis is the ban-alignment test`.

## E2/S3. Narrow the mechanism language and avoid permanent marginalization claims

### Answer

Partially addressed by combining PR #3, PR #5, and the current toxicity batch.
The toxicity batch shows a cohort-toxicity gradient. PR #3 shows that high
early-toxicity users persist longer in early cohorts and high-activity arrivals
are more likely to become hubs. PR #5 provides the mechanism-language
clarification.

The supported mechanism is ecological selection and concentrated active-arrival
influence, not permanent newcomer marginalization or proven peripheral
causation.

Recommended wording:

> The evidence is consistent with ecological selection into an increasingly
> toxic platform environment: later cohorts exhibit higher mean classifier
> probabilities, high early-toxicity users persist longer in early cohorts, and
> high-activity arrivals are more likely to become structurally central.

Avoid:

- "newcomers remained permanently peripheral"
- "toxicity caused retention"
- "users adapted" unless a within-user change model is added

**Evidence:** manuscript figure `Fixed-cohort Kaplan-Meier survival by early toxicity`; manuscript table `Fixed-cohort retention and hub-ascent summary`; manuscript or supplementary figure `A-D+ cohort toxicity by arrival cohort`; text modification `narrow mechanism to ecological selection and concentrated active-arrival influence`.

## M4. Clarify that arrivals are a noisy, self-selected proxy

### Answer

Still open. The cohort labels are based on first observed Voat activity, not
verified Reddit migration. The results can support statements about event-timed
Voat arrivals, but not direct migration or causal displacement.

Manuscript text should state near the cohort results that subreddit bans were
community bans, not user-account bans, and that Voat arrivals are self-selected
and may include organic Voat users.

**Evidence:** text modification `state subreddit bans were community bans, not user bans`; text modification `state event-timed Voat arrivals are a noisy, self-selected proxy`; supplementary table `arrival-proxy noise estimate` still needed.

## M7. Treat classifier scores as probabilities, not observed toxic content

### Answer

Partially addressed. The new outputs and proposed captions use mean ToxiGen
classifier probability. A classifier-validity paragraph still needs to cite
ToxiGen validation and note domain-shift limitations for Voat-specific language.

**Evidence:** text modification `describe ToxiGen as classifier probability`; text modification `add classifier-validity and domain-shift limitation`; supplementary table or text box `classifier-validity note` still needed.

## M8/S2. Improve signposting and paragraph-level interpretation

### Answer

Partially addressed by providing a clearer figure hierarchy.

Use the barplot as the compact main claim:

> Later arrival cohorts have higher A-D+ mean ToxiGen classifier probabilities,
> and the pattern remains under activity weighting.

Use the time series as context:

> Rolling trajectories show gradual platform-level toxicity change rather than a
> discrete toxicity shock.

Suggested paragraph sequence:

1. Later arrival cohorts have higher A-D+ mean ToxiGen classifier probabilities.
2. Activity weighting preserves the cohort gradient.
3. Rolling 30-day trajectories show gradual platform-level change.
4. Together with fixed-cohort retention and hub-ascent evidence, the results
   support ecological selection and concentrated active-arrival influence, not
   abrupt takeover.

**Evidence:** manuscript or supplementary figure `A-D+ cohort toxicity by arrival cohort`; supplementary figure `Rolling cohort toxicity trajectories`; text modification `add topic and takeaway sentences to the cohort-toxicity Results paragraph`.

# Editor / Cross-Cutting RR Tasks

## Rewrite abstract and main contribution

### Answer

Partially addressed. The toxicity batch supports a contribution centered on
receiving-platform dynamics and cohort composition. Combined with PR #3, the
paper can foreground ecological selection and concentrated active-arrival
effects.

Candidate wording:

> We characterize how Voat's generalist communities changed during a period
> containing major Reddit community bans. Later arrival cohorts show higher mean
> ToxiGen classifier probabilities, high early-toxicity users persisted longer
> in early post-ban cohorts, and high-activity arrivals were more likely to
> become hubs. These patterns are consistent with ecological selection into an
> increasingly toxic receiving platform, rather than a simple abrupt takeover.

**Evidence:** manuscript or supplementary figure `A-D+ cohort toxicity by arrival cohort`; manuscript figure `Fixed-cohort Kaplan-Meier survival by early toxicity`; manuscript table `Fixed-cohort retention and hub-ascent summary`; text modification `rewrite abstract and contribution around longitudinal receiving-platform dynamics`.

## Regime and breakpoint validation

### Answer

Partially addressed by PR #4. The toxicity batch should be used to reinforce the
gradual-toxicity interpretation, not to replace breakpoint validation. PR #4
should remain the evidence for which metrics are ban-aligned.

**Evidence:** manuscript or supplementary figure `Global segmented-fit breakpoint visualization`; manuscript or supplementary table `Regime model comparison`; text modification `state E-I is ban-aligned where supported, toxicity/reputation are gradual where not`.

## Arrival-proxy and classifier-validity check

### Answer

Still open. This toxicity batch improves cohort decomposition and classifier
wording, but it does not estimate post-ban arrival-proxy noise, verify Reddit
migration, or add manual validation.

Needed next:

- Excess-arrival/proxy-noise table.
- ToxiGen validation note.
- Optional manual sanity-check sample across communities and toxicity quantiles.

**Evidence:** supplementary table `arrival-proxy noise estimate` still needed; text modification `classifier-validity and domain-shift limitation` still needed.
