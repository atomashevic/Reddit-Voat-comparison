# Scientific Reports RR Log

Append-only revision log for the Scientific Reports major revision of
`The Consequences of Reddit Deplatforming: Toxicity Spillover to Generalist Voat Communities`.

Rules:

- Append new entries; do not rewrite prior entries except for fixing broken links or obvious typos.
- Keep reviewer/editor comments verbatim under each response item.
- Mark each item as `done`, `partial`, `planned`, or `open`.
- Manuscript edits should be logged here after they are made, but this file can also record analysis-only evidence.

## 2026-05-27 — RR branch fixed-cohort analysis added

Status: `done` for analysis; manuscript integration still `planned`.

New analysis added on the `RR` branch:

- Script: `scripts/longitudinal_cohort_analysis.py`
- Tests: `tests/test_longitudinal_cohort_analysis.py`
- Evidence note: `results/basic/compare/results/fixed_cohort_review_response.md`
- Summary outputs:
  - `results/basic/compare/results/fixed_cohort_structural_ascent_summary.csv`
  - `results/basic/compare/results/fixed_cohort_retention_toxicity_summary.csv`
  - `results/basic/compare/results/postban_proxy_noise_summary.csv`
- Figures:
  - `results/basic/compare/figures/fixed_cohort_degree_share_ratio.png`
  - `results/basic/compare/figures/fixed_cohort_retention_by_toxicity.png`
- Per-community detail outputs are reproducible but not retained in the PR artifact set.

Verification:

- `python -m unittest tests.test_longitudinal_cohort_analysis -v` passed, 5 tests.
- Smoke run on `gifs` completed successfully.
- Full six-community run completed in `65.28s` wall time.
- Summary table row counts match expected coverage:
  - structural summary: 30 rows = 6 communities x 5 fixed cohorts
  - retention/toxicity summary: 60 rows = 6 communities x 5 cohorts x 2 toxicity groups
  - proxy-noise summary: 24 rows = 6 communities x 4 ban events

Main interpretation from new analysis:

- The original claim that post-ban newcomers remained permanently peripheral is too broad.
- FPH-PG and PG-GA fixed cohorts reach near-proportional median degree-share ratios:
  - `fph_pg`: 0.9755
  - `pg_ga`: 0.9761
- Later fixed cohorts are clearly under-represented:
  - `ga_td`: 0.7684
  - `td_shutdown`: 0.6576
- Average post-ban ever-hub rates remain modest, but high-activity arrivals are much more likely to become hubs:
  - `fph_pg`: average 0.0958, high-activity 0.3170
  - `pg_ga`: average 0.0775, high-activity 0.2111
  - `ga_td`: average 0.0650, high-activity 0.1959
  - `td_shutdown`: average 0.0465, high-activity 0.1899
- Early high-toxicity arrivals persist longer:
  - FPH-PG high-minus-lower toxicity 3-month retention difference: +0.2231
  - PG-GA high-minus-lower toxicity 3-month retention difference: +0.1382
- Proxy-noise check indicates the event-timed arrival proxy is strongest for FPH and much weaker for later events:
  - FPH mean proxy-noise upper bound: 0.0619
  - Pizzagate: 0.8930
  - GreatAwakening: 0.7924
  - The_Donald: 0.9338

Revised single narrative to integrate into manuscript:

> Post-ban arrival cohorts were not uniformly hub-capturing or uniformly peripheral. Early FPH/PG-era arrival cohorts reached near-proportional degree representation, and a high-activity minority within those cohorts became structurally influential. Later GA/TD-era cohorts were more consistently under-represented among high-degree users and entered communities whose norms had already shifted. The mechanism is therefore heterogeneous: broad arrival volume changed participation composition during the early transformation, while concentrated influence among the most active arrivals helped stabilize the later toxic equilibrium.

## Point-by-point response log

### ED-1 — Major revision and longitudinal cohort analysis

Status: `partial`

Verbatim comment:

> As you will see from numerous and constructive comments of the Reviewers, your manuscript requires a major revision. Please carefully address all the points raised, particularly the longitudinal cohort analysis.

Response draft:

We agree and have added a new fixed-cohort longitudinal analysis that follows users according to their first observed Voat activity cohort across later months, rather than relabeling them at each event boundary. This directly addresses whether event-timed arrivals later reached high-degree positions. The analysis is implemented in `scripts/longitudinal_cohort_analysis.py`, tested in `tests/test_longitudinal_cohort_analysis.py`, and summarized in `results/basic/compare/results/fixed_cohort_review_response.md`.

Manuscript action needed:

- Add a Methods subsection describing fixed arrival cohorts.
- Add a Results subsection summarizing structural ascent, high-activity arrivals, toxicity/retention, and proxy-noise results.
- Revise mechanism claims so the manuscript no longer states that newcomers remained permanently peripheral.

### ED-2 — Title format

Status: `planned`

Verbatim comment:

> To aid our readers, and to maximize the accessibility of your manuscript, the title (title of manuscript) should have a clear, precise scientific meaning. Where possible, the title should be read as one concise sentence which is under 20 words long, should not contain punctuation (full stops, hyphen, semi-colons, colon, question mark) and should not be phrased as a question. Please could you re-write the title ensuring that it is informative and appropriate. After correcting the title please ensure that the title exactly matches on the tracking system, manuscript file and cover letter.

Response draft:

We will revise the title to remove punctuation and reduce causal overstatement. A candidate title is:

`Longitudinal toxicity dynamics in generalist Voat communities after Reddit community bans`

Manuscript action needed:

- Update title in manuscript, submission system, and cover letter.
- Ensure the revised title remains under 20 words and does not contain punctuation.

### R1-Summary — Overall concern about causal framing

Status: `planned`

Verbatim comment:

> This manuscript addresses an understudied and genuinely important question: when deplatforming displaces users, what happens to the generalist communities on the receiving platform that never sought them? I think this manuscript represents a real contribution to the field and a sound choice for observational design: studying Voat’s generalist subverses across four Reddit ban waves through network analysis, toxicity classification, and dynamic reputation modeling over the platform’s full lifespan is very interesting and understudied. The Introduction frames the ecosystem gap especially well, and the Limitations section is candid and thorough.
>
> My central concern is that the framing and several headline claims currently go beyond what the design and data can support. Most importantly, the analysis is descriptive and correlational, while the title, abstract, and discussion are written in causal language. I know you openly acknowledge in the Discussion that you cannot determine causality, but the framing throughout the paper still seems to lean far too much into causal language (e.g., Reddit bans caused “spillover” into Voat).
>
> The encouraging part is that the fixes are largely about recalibrating claims and reorganizing presentation rather than overturning the analysis. One essential point about newcomers’ position in the Voat networks would benefit from a modest additional analysis, which I flag as encouraged rather than required.
>
> Overall, I think the underlying work is sound and the question is genuinely worth answering. With the framing recalibrated to match the study’s descriptive design and/or more robust analysis in the Results, this would be a valuable contribution to the field of social media research and computational social science.

Response draft:

We agree that the manuscript should consistently present the design as descriptive and longitudinal rather than causal. We will revise the title, abstract, Results, and Discussion to avoid implying that Reddit bans causally produced all observed Voat changes. We will describe the study as characterizing Voat generalist communities over a period containing major Reddit community bans. We have also added the suggested longitudinal fixed-cohort analysis to better characterize how event-timed arrival cohorts later occupied network positions.

Manuscript action needed:

- Replace causal phrases such as `caused spillover`, `transformation occurred through`, and strong `hostile takeover` language with descriptive alternatives.
- Frame Reddit comparisons as descriptive matched reference series, not causal counterfactuals.
- Add a sentence early in Results/Methods that event-timed arrivals are not verified Reddit migrants.

### R1-E1 — Causal framing and breakpoint analysis

Status: `planned`

Verbatim comment:

> E1. Bring the causal framing in line with the descriptive design, and use the breakpoint analysis as the explicit test of ban-alignment. The manuscript disavows causal inference (Discussion, Limitations) yet the title (“Toxicity Spillover”), the abstract, and the discussion section consistently use causal language around presumed migration from Reddit (“Hostile Takeover,” “displaced users,” bans “followed by” transformation). Two issues follow. First, the “Newcomer” cohort is defined by first activity after a ban (Methods, User Cohort Partitioning), which mixes actual migrants with organic arrivals. Therefore, the language throughout should not attribute change to migrants more strongly than this proxy allows. Second, the matched Reddit series is described as a counterfactual showing that observed changes “reflect platform-specific dynamics rather than broader temporal trends” (Discussion, Para. 7). That comparison does not control for Voat-specific organic toxification—a permissive, free-speech platform may well self-select toxic users and naturally drift more toxic over time independent of any ban—so it cannot rule out that Voat would have trended this way regardless. Notably, your own breakpoint analysis supports caution: toxicity shows weak breaks (Table 2; 0 of 7 series near GA), consistent with a gradual rise rather than ban-triggered discontinuities.
>
> Revision needed: reframe the paper as a longitudinal characterization of Voat’s generalist communities over a period that includes major Reddit bans, and position the Breakpoint Validation section as the explicit test of whether each metric aligns with ban events. Then interpret each metric by what that test supports: the E-I index does break at the GA ban (5 of 7 series), so a ban-aligned reading is defensible there; toxicity and reputation do not, so describe them as gradual trends, or conduct further analysis to strengthen the link to the Reddit bans. As a result, I would soften “Spillover/Hostile Takeover/displaced users” throughout and consider revising the title accordingly.

Response draft:

We agree. We will revise the framing to describe a longitudinal characterization of Voat’s generalist communities during a period containing major Reddit community bans. We will explicitly position breakpoint analysis as the ban-alignment test. We will state that E-I index changes are the strongest ban-aligned structural evidence, while toxicity and reputation are better described as gradual longitudinal trends rather than abrupt ban-triggered discontinuities.

Evidence/actions:

- Existing breakpoint evidence: `results/basic/compare/results/regime_break_summary.txt`.
- New proxy-noise evidence: `results/basic/compare/results/postban_proxy_noise_summary.csv`.
- FPH event-timed arrivals are much cleaner than later event proxies; later proxy-noise upper bounds are high, so language about later arrivals must be cautious.

Manuscript action needed:

- Rewrite title/abstract/discussion to soften `spillover`, `hostile takeover`, and `displaced users`.
- Add direct statement that toxicity and reputation do not show strong GA-aligned breaks.
- Add proxy-noise paragraph in Methods/Limitations.

### R1-E2 — Newcomer marginalization and hub-rate baseline

Status: `partial`

Verbatim comment:

> E2. Temper the “newcomers remained structurally marginalized” claim to match the cohort design, and state the baseline for the hub rate. The Results state that newcomers “remained structurally marginalized” despite numerical dominance (Results, Platform Dynamics, Para. 4), and the Discussion concludes that fewer than 5% of newcomers achieved central positions (Discussion, Para. 2). The cohort definition makes this hard to claim as written: because labels reset at each ban—a Newcomer in one period becomes Existing in the next (Methods, User Cohort Partitioning)—a post-ban arrival who rose into the core in a later period would be relabeled Existing before that shift in network position could be observed. The design therefore cannot establish that arrivals remained permanently peripheral. The figure also lacks an interpretive anchor: Supplementary Table 2 shows a consistent and more compelling pattern at every threshold where newcomers are consistently below the population-equality baseline at every hub threshold tested (3.3% vs. 10%; 7.1% vs. 20%; 1.4% vs. 5%).
>
> Revision needed: state the roughly 10% equality baseline so the hub rate is interpretable, and foreground the degree-share ratio more clearly in the text and figure (Figure 1, panel 5; null = 1.0). Revise the “structurally marginalized” language to a claim the design supports. For example, you might say that within each inter-ban period newcomers were under-represented among high-degree users relative to their population share.
>
> Encouraged (not required): a longitudinal analysis that tracks arrival cohorts across period boundaries would directly test the marginalization claim and substantially strengthen the mechanism argument (RQ2). By following users who first appeared after a given ban to see whether they later reach core or hub status, you could more clearly establish whether newcomers remain marginalized and yet are still able to influence the platform’s social norms. I encourage it but do not require it for acceptance.

Response draft:

We agree and implemented the encouraged longitudinal cohort analysis. The new results show that the original permanent-marginalization claim was too broad. Early FPH-PG and PG-GA arrival cohorts reached near-proportional median degree-share ratios, while later GA-TD and TD-shutdown cohorts were under-represented. We will revise the manuscript accordingly and use degree-share ratio as the primary structural-representation metric, with hub-rate baselines stated explicitly.

Evidence:

- `results/basic/compare/results/fixed_cohort_structural_ascent_summary.csv`
- `results/basic/compare/results/fixed_cohort_review_response.md`
- Figure: `results/basic/compare/figures/fixed_cohort_degree_share_ratio.png`

Key fixed-cohort values:

- `fph_pg` median degree-share ratio: 0.9755
- `pg_ga` median degree-share ratio: 0.9761
- `ga_td` median degree-share ratio: 0.7684
- `td_shutdown` median degree-share ratio: 0.6576

Manuscript action needed:

- Remove claim that newcomers remained permanently marginalized.
- Replace with: early event-timed cohorts partially integrated; later cohorts were under-represented.
- State hub equality baseline: top-10% hub rate has 10% expected baseline.
- Promote degree-share ratio as the main evidence.

### R1-E3 — Results primer

Status: `planned`

Verbatim comment:

> E3. Add a conceptual and methodological primer to the Results so the findings are interpretable without the Methods. In the results-first format used in this manuscript, several central concepts are used before they are defined, which makes the Results difficult to follow on a first read:
> 1. Voat itself is barely characterized and the reputation metric is invoked repeatedly (for example, “sustained activity” in Para. 2 and the 4.5 “sustainability threshold” in Para. 5) without explaining that it is an activity-based metric rather than a native Voat feature.
> 2. The E-I index is named with only a brief gloss (Para. 3, Sentence 1), insufficient to interpret what its bounds are or why -0.35 is “moderate”.
> 3. The network metrics (degree, assortativity, hub rate) cannot be interpreted by the reader without knowing how edges are formed in your analysis, which is only clarified later in the methods as comment-to-post replies only.
> 4. The phrase “parallel social structures” is never clearly defined (Abstract, Sentence 4; Discussion, Para. 2), despite it playing a major part in the RQ1 finding.
>
> Revision needed: add a brief overview at the start of Results that (a) characterizes Voat and the six communities, (b) defines reputation, the E-I index, and the edge construction with enough detail to interpret their values, and (c) defines “parallel social structures” concretely.

Response draft:

We agree. We will add a short Results primer before the first results subsection. This primer will characterize Voat and the six generalist communities, clarify that reputation is an activity-based DIBRM score rather than a native Voat variable, define E-I index bounds, explain comment-to-post edge construction, and operationalize any retained use of "parallel social structures."

Manuscript action needed:

- Add Results primer.
- If "parallel social structures" remains, define it as within-cohort interaction concentration and low cross-cohort mixing measured by E-I index, not as directly observed full-thread conversational structure.

### R1-M1 — Reputation sustainability interpretation

Status: `planned`

Verbatim comment:

> M1. Justify or soften the reputation-based “sustainability” interpretation. The case study concludes that /v/funny became toxic yet “achieved sustainability,” inferring trust and community health from reputation stabilization (Results, Case Study, Paras. 5-6). Because reputation here is an activity-based measure, “stable reputation” largely reflects that active users kept being active, which is not as direct a measure of “trust” or “health” as one might expect. The 4.5 threshold is imported from a Stack Exchange study (Methods, Dynamic Reputation), justified only by asserting structural similarity across platforms. Please either justify the threshold’s applicability to Voat or soften the trust/health/sustainability language to match what an activity-based measure supports.

Response draft:

We agree that "sustainability," "trust," and "health" overstate what the activity-based reputation model directly measures in this setting. We will soften this interpretation and describe stable reputation as evidence of continued active participation among reputation-active users, not as direct evidence of community health or trust.

Manuscript action needed:

- Replace "achieved sustainability" with "maintained stable activity-based reputation among active users" or equivalent.
- Treat the 4.5 threshold as contextual comparison, not a validated Voat sustainability cutoff.

### R1-M2 — Network-construction limitation near findings

Status: `planned`

Verbatim comment:

> M2. Foreground the network-construction limitation where the structural findings are stated. Networks use comment-to-post replies only, with no comment-to-comment threading (Methods, Network Metrics), and as you note (Discussion, Limitations, “Third”) the “parallel structures” could instead reflect thread-level conversational dynamics. Because this caveat bears directly on the RQ1 finding, please state it where that finding is presented, not only in Limitations, and temper the claim accordingly.

Response draft:

We agree. We will move this caveat into the Results near the structural findings and use more cautious language about "parallel social structures." We will state that the network captures comment-to-post reply relations only and cannot observe comment-to-comment threading.

Manuscript action needed:

- Add caveat in Results near E-I/degree-share discussion.
- Avoid claims implying full conversational network observation.

### R1-M3 — Activity-weighted toxicity

Status: `partial`

Verbatim comment:

> M3. Report activity-weighted toxicity alongside the equal-weighted measure. Toxicity is aggregated as an unweighted mean of per-user monthly means, such that each user contributes equally regardless of posting volume (Methods, Toxicity Detection, Para. 2). An activity-weighted version would better capture the discourse a typical reader encounters, and the comparison would give speak to RQ2: if elevated toxicity is driven by a few highly active users who remain peripheral in the reply network, the two weightings will diverge, and equal weighting would obscure exactly that signal. Please report both, and ideally discuss any insight from alignment or divergence of these two measurements.

Response draft:

We agree and have added activity-weighted toxicity to the fixed-cohort monthly outputs. This allows direct comparison between equal-user and activity-weighted toxicity by cohort and month.

Evidence:

- Per-community monthly outputs: `results/basic/voat/results/voat_<community>_fixed_cohort_monthly.csv`
- Relevant columns:
  - `mean_toxicity_equal_user`
  - `mean_toxicity_activity_weighted`

Manuscript action needed:

- Summarize whether activity-weighted toxicity aligns with or diverges from equal-user toxicity.
- Add table or figure if divergence materially changes interpretation.

### R1-M4 — Community bans not user bans

Status: `planned`

Verbatim comment:

> M4. Clarify what was banned, and unpack the implication. Please state explicitly that the four events are community (subreddit) bans rather than user bans. This matters for interpretation, since users retained their Reddit accounts and lost only the banned space. Therefore, arrivals on Voat are plausibly topic-motivated and self-selected for the banned content. That self-selection is part of the confound noted in E1 and is worth making explicit.

Response draft:

We agree. We will state explicitly that the focal events are subreddit/community bans, not user-account bans. We will explain that event-timed Voat arrivals are therefore a noisy and self-selected proxy for actual migration.

Manuscript action needed:

- Add this clarification in Methods/Event description.
- Add self-selection/confounding language in Limitations and where arrival cohorts are introduced.

### R1-M5 — Breakpoint validation visualization

Status: `planned`

Verbatim comment:

> M5. Expand and visualize the Breakpoint Validation section. This section validates the central two-regime thesis but appears only as a table (Table 2; Supplementary Table 1). Please consider adding a visualization of the segmented fits for at least the global series, and state directly that only the E-I index breaks at the GA ban while toxicity, reputation, Gini, and assortativity do not. Given the importance of this section to the causal interpretation of this entire paper, I think more work and analysis should be put into it.

Response draft:

We agree. We will expand the breakpoint section and add at least one visualization for global segmented fits. We will explicitly state which metrics show GA-aligned breaks and which do not.

Evidence/actions:

- Existing breakpoint outputs: `results/basic/compare/results/regime_breakpoints.csv` and `results/basic/compare/results/regime_break_summary.txt`.

Manuscript action needed:

- Add figure for global segmented fits.
- Add direct sentence: E-I index is the metric with robust GA-aligned breaks; toxicity and reputation are gradual/non-GA-aligned in this analysis.

### R1-M6 — Dedicated enclaves claim

Status: `planned`

Verbatim comment:

> M6. Remove or attribute the “dedicated enclaves” claim in the Abstract. The Abstract states that “ideologically cohesive groups concentrated in dedicated enclaves,” but the enclave communities (e.g., /v/GreatAwakening, /v/QRV, /v/pizzagate, /v/TheDonald) were explicitly excluded from analysis (Methods, Dataset). Please either remove this claim or attribute it clearly to prior work, since it is not tested here.

Response draft:

We agree. We will either remove this sentence from the Abstract or attribute it explicitly to prior work rather than presenting it as a finding from our analysis.

Manuscript action needed:

- Remove or cite/qualify dedicated-enclave claim.

### R1-M7 — Toxicity doubled statement

Status: `planned`

Verbatim comment:

> M7. Qualify the “toxicity doubled” statement. The doubling refers to a mean ToxiGen probability rising from about 0.12 to about 0.24 (Results, Platform Dynamics, Para. 6; Results, Case Study, Para. 4). If I understand correctly, this is a mean classifier probability rather than a proportion of toxic content, and therefore “doubled” should be qualified to avoid implying that content became twice as toxic.

Response draft:

We agree. We will specify that this refers to the mean ToxiGen toxicity probability, not the proportion of toxic content.

Manuscript action needed:

- Replace "toxicity doubled" with "mean ToxiGen toxicity probability approximately doubled" or similar.

### R1-M8 — Clarify RQ takeaway paragraph

Status: `planned`

Verbatim comment:

> M8. Clarify the “Taken together” paragraph. The paragraph restating RQ1 and RQ2 is difficult to follow and carries the paper’s main takeaways; please rewrite it for clarity.

Response draft:

We agree. We will rewrite the RQ1/RQ2 takeaway paragraph to incorporate the revised fixed-cohort interpretation: early cohorts partially integrated and high-activity arrivals were structurally influential, while later cohorts were more consistently under-represented.

Manuscript action needed:

- Rewrite paragraph after integrating fixed-cohort results.

### R1-S1 — Confidence intervals or descriptive framing for toxicity ratios

Status: `planned`

Verbatim comment:

> S1. Add confidence intervals or explicit descriptive framing to the cross-platform toxicity ratios. The point ratios in Table 1 lack an inferential framing; either add intervals or mark the comparison as descriptive, consistent with the reframing in E1.

Response draft:

We agree. We will either add uncertainty intervals to the toxicity ratios or explicitly mark these as descriptive comparisons rather than inferential estimates.

Manuscript action needed:

- Decide whether to add intervals or descriptive wording.
- Ensure this aligns with the broader non-causal reframing.

### R1-S2 — Interpretive guidance in Results

Status: `planned`

Verbatim comment:

> S2. Add better interpretive guidance to the reading throughout the results. Throughout Results, several paragraphs are largely sequences of statistics, and it is not always clear what each is meant to demonstrate to the reader. If you add more clear topic and concluding sentences for each paragraph that indicate the point being made or the conclusion to draw, it will help the reader make sense of the statistics contained within.

Response draft:

We agree. We will add topic and takeaway sentences to the Results paragraphs so each set of statistics is tied to a specific interpretive claim.

Manuscript action needed:

- Edit Results section paragraph by paragraph after claims are softened.

### R1-S3 — Promote degree-share ratio

Status: `partial`

Verbatim comment:

> S3. Promote the degree-share ratio to the primary newcomer-centrality evidence in the Discussion. It is better constructed than the raw hub rate (related to E2). [Discussion, Para. 2; Figure 1, panel 5.]

Response draft:

We agree. The fixed-cohort analysis now uses degree-share ratio as the primary structural representation measure and uses hub rate as supporting evidence.

Evidence:

- `results/basic/compare/results/fixed_cohort_structural_ascent_summary.csv`
- `results/basic/compare/figures/fixed_cohort_degree_share_ratio.png`

Manuscript action needed:

- Make degree-share ratio the main structural-representation metric in Discussion.
- Retain hub rate as an interpretable baseline comparison.

### R2-1 — Peripheral dynamics not proven

Status: `partial`

Verbatim comment:

> You claim “transformation occurred through peripheral dynamics rather than hub capture”. But what you actually show is low newcomer hub rate, rising toxicity, and cohort segregation patterns. This is consistent with peripheral influence, but does not prove it.

Response draft:

We agree and will soften the mechanism claim. The fixed-cohort analysis further shows that the original dichotomy is too strong: average post-ban cohorts did not broadly capture hubs, but high-activity arrivals were much more likely to become hubs. We will frame the result as evidence inconsistent with broad hub capture, not proof of peripheral causation.

Evidence:

- `results/basic/compare/results/fixed_cohort_structural_ascent_summary.csv`
- `results/basic/compare/results/fixed_cohort_review_response.md`

Manuscript action needed:

- Replace proof language with "consistent with" and "does not support broad hub capture."
- Add high-activity exception.

### R2-2 — E-I index regime-change justification

Status: `planned`

Verbatim comment:

> Justify why E-I index alone defines regime change. Add model comparison (1 vs 2 vs multiple breakpoints) and robustness to alternative splits.

Response draft:

We agree that E-I index should not be treated as sufficient on its own without clearer validation. Existing breakpoint results show that E-I is the strongest GA-aligned metric, while other metrics show different timing or gradual trends. We will expand model comparison and clarify that the two-regime interpretation is primarily structural/cohort-mixing evidence rather than a universal breakpoint across all metrics.

Manuscript/action needed:

- Add model comparison for breakpoint models if feasible.
- Add robustness to alternative split dates.
- State directly which metrics do and do not support GA-aligned regime change.

### R2-3 — Takeover of norms, not structure

Status: `planned`

Verbatim comment:

> Clarify takeover of norms, not structure. Rename if needed: “Normative Overwrite” and “Peripheral Saturation Phase”.

Response draft:

We agree that the term "takeover" risks implying structural capture of hubs or institutions. The fixed-cohort results suggest a mixed mechanism: early arrival cohorts became near-proportionally represented, while high-activity users were especially likely to become hubs. We will revise terminology to avoid implying wholesale structural takeover.

Manuscript action needed:

- Consider replacing "Hostile Takeover" with a less causal term such as "Early arrival-volume phase" or "Norm-shift phase."
- If retaining the phrase, define it as shorthand and explicitly state that it does not mean hub capture.

### R2-4 — Robustness checks

Status: `partial`

Verbatim comment:

> Add robustness checks:
> --activity spikes immediately post-ban (short window)
> --high-activity newcomers vs low-activity
> Explicitly estimate noise level of proxy

Response draft:

We have addressed two of these three requests in the fixed-cohort analysis. High-activity arrivals are compared with lower-activity arrivals, and proxy-noise is estimated for each event using prior six-month first-user baselines. Short-window post-ban activity spikes remain to be added if needed.

Evidence:

- High-activity split: `results/basic/compare/results/fixed_cohort_structural_ascent_summary.csv`
- Proxy-noise: `results/basic/compare/results/postban_proxy_noise_summary.csv`

Open action:

- Add short-window weekly or monthly activity-spike analysis around ban events.

### R2-5 — Toxicity validation

Status: `open`

Verbatim comment:

> Add validation sample manual annotation or cite validation on similar platforms

Response draft:

This remains open. We should either add a small manual validation sample for ToxiGen scores or cite validation evidence on comparable online discussion platforms.

Manuscript/action needed:

- Decide between manual annotation and citation-only validation.
- If manual annotation is chosen, sample comments/posts across communities and toxicity quantiles.

### R2-6 — Voat vs Reddit comparison limitations

Status: `planned`

Verbatim comment:

> You compare Voat vs Reddit toxicity. Problem is platforms differ in:
> --moderation
> --user base
> --scale
> Required explicitly state this is not a controlled comparison and avoid implying Reddit is causal baseline.

Response draft:

We agree. We will explicitly describe the Reddit series as a descriptive matched-platform reference, not a causal baseline. We will discuss moderation, user-base, and scale differences as limitations.

Manuscript action needed:

- Revise cross-platform comparison language.
- Add limitations in Results/Discussion where ratios are interpreted.

### R2-7.1 — Cohort toxicity decomposition

Status: `partial`

Verbatim comment:

> You should strongly consider adding:
> 5.1 Cohort Toxicity Decomposition
> newcomer vs existing user toxicity over time

Response draft:

Partially addressed. The fixed-cohort monthly tables now report equal-user and activity-weighted toxicity by fixed arrival cohort and month. This provides cohort toxicity decomposition, but not exactly the original dynamic newcomer/existing split unless we summarize it explicitly.

Evidence:

- `results/basic/voat/results/voat_<community>_fixed_cohort_monthly.csv`
- Columns: `mean_toxicity_equal_user`, `mean_toxicity_activity_weighted`

Manuscript/action needed:

- Add a concise cohort-toxicity summary table/paragraph.

### R2-7.2 — Short-term post-ban dynamics

Status: `open`

Verbatim comment:

> 5.2 Short-Term Post-Ban Dynamics
> weekly (not monthly) analysis around bans

Response draft:

Open. Current fixed-cohort analysis remains monthly because it builds on existing user-month and network outputs. A separate weekly short-window analysis is needed if we choose to address this fully.

Manuscript/action needed:

- Add weekly event-window analysis around ban events or explain why monthly resolution is retained.

### R2-7.3 — Survival analysis of users

Status: `partial`

Verbatim comment:

> 5.3 Survival Analysis of Users
> do toxic users persist longer?

Response draft:

Partially addressed descriptively. The fixed-cohort analysis computes retention at 1, 3, 6, and 12 months by early-toxicity group and shows that high-toxicity arrivals persist longer in early cohorts, especially FPH-PG and PG-GA. This is not yet a formal survival model.

Evidence:

- `results/basic/compare/results/fixed_cohort_retention_toxicity_summary.csv`
- FPH-PG high-minus-lower 3-month retention difference: +0.2231
- PG-GA high-minus-lower 3-month retention difference: +0.1382

Manuscript/action needed:

- Decide whether descriptive retention is enough or whether to add formal survival modeling.
- If descriptive, avoid calling it "survival analysis" in a strict statistical sense.

### R2-7.4 — Community-level heterogeneity

Status: `planned`

Verbatim comment:

> 5.4 Community-Level Heterogeneity
> why does /v/technology behave differently?

Response draft:

Planned. The fixed-cohort outputs include community-specific tables, including technology. Technology shows the same later-cohort under-representation pattern but differs in toxicity comparison elsewhere. We need to add a short heterogeneity paragraph connecting structural and toxicity differences.

Evidence:

- `results/basic/compare/results/fixed_cohort_structural_ascent_summary.csv`
- Technology fixed-cohort rows:
  - `fph_pg` median degree-share ratio: 1.1202
  - `pg_ga`: 0.8908
  - `ga_td`: 0.7483
  - `td_shutdown`: 0.6515

Manuscript action needed:

- Add community heterogeneity subsection or paragraph.
- Explain technology cautiously, likely as topic-oriented discussion with weaker toxicity divergence.

### R2-8 — Make contribution explicit

Status: `planned`

Verbatim comment:

> Right now contribution is somewhat buried. Make explicit:
> --first study of receiving-platform externalities
> --peripheral vs hub-driven transformation insight

Response draft:

We agree. We will make the contributions explicit while revising the mechanism language to avoid overclaiming. The second contribution should become "tests whether transformation is hub-driven or distributed across arrival cohorts" rather than "proves peripheral transformation."

Manuscript action needed:

- Add contribution paragraph in Introduction and sharpen Discussion.

## 2026-05-27 — RR TODO cleanup before draft PR

Status: `done`

Cleanup decision:

- Retained compact artifacts needed for RR answers:
  - `RR-log.md`
  - `scripts/longitudinal_cohort_analysis.py`
  - `tests/test_longitudinal_cohort_analysis.py`
  - `results/basic/compare/results/fixed_cohort_structural_ascent_summary.csv`
  - `results/basic/compare/results/fixed_cohort_retention_toxicity_summary.csv`
  - `results/basic/compare/results/postban_proxy_noise_summary.csv`
  - `results/basic/compare/results/fixed_cohort_review_response.md`
  - `results/basic/compare/figures/fixed_cohort_degree_share_ratio.png`
  - `results/basic/compare/figures/fixed_cohort_retention_by_toxicity.png`
- Removed bulky per-community intermediate detail tables from the PR artifact set:
  - `results/basic/voat/results/voat_<community>_fixed_cohort_users.csv`
  - `results/basic/voat/results/voat_<community>_fixed_cohort_monthly.csv`
- Updated `scripts/longitudinal_cohort_analysis.py` so compact summaries remain the default output. Per-community detail tables are now opt-in with:

```bash
python scripts/longitudinal_cohort_analysis.py --write-detail-tables
```

Rationale:

The RR response and manuscript revision need compact cross-community summaries,
the two figures, and reproducible code. The per-user/per-month detail tables are
useful for debugging but are not necessary evidence for the reviewer response
and would make the PR noisier.
