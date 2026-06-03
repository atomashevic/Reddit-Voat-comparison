# Internal RR Todo

Goal: satisfy the editor and both reviewers with the smallest coherent revision
set. Avoid parallel appendices, redundant figures, and claims stronger than the
design supports.

## New Scripts And Results

- [x] **Fixed-cohort survival and hub ascent**
  - Action: follow fixed arrival cohorts across later months; compare high vs
    lower early-toxicity survival; report degree-share ratio, average ever-hub
    rate, high-activity ever-hub rate, and hub-cutoff sensitivity.
  - Output: KM survival figure, manuscript table, SI toxicity-definition
    sensitivity table, SI hub-definition sensitivity table.
  - Covers: editor longitudinal cohort request; Reviewer 1 survival question,
    high-activity newcomer check, peripheral/hub-capture concern; Reviewer 2 E2
    and S3.

- [ ] **Regime and breakpoint validation**
  - Action: make the breakpoint section the explicit test of ban alignment.
    Compare no-break, one-break, and multi-break alternatives; check robustness
    to reasonable split definitions; add one global segmented-fit visualization.
  - Output: one compact model-comparison table and one breakpoint figure.
  - Covers: Reviewer 1 breakpoint/model-comparison request; Reviewer 2 E1 and
    M5.
  - Acceptance: text can say which metrics are ban-aligned and which are gradual
    trends. Do not use E-I alone to define a whole-platform regime change.

- [x] **Weekly short-window toxicity and activity dynamics**
  - Action: analyze weekly bins from `-4` to `+4` weeks around each event;
    compare existing users with event-window arrivals; report user-weighted
    toxicity, activity-weighted toxicity, and weekly post volume.
  - Output: PR #8 figure, full weekly CSV, and compact pre/post summary table.
  - Covers: Reviewer 1 short-term post-ban dynamics and activity-spike checks;
    Reviewer 2 M3 activity-weighted toxicity request.
  - Acceptance: text can say short-term dynamics are event-specific: FPH is the
    largest volume shock, GA/TD arrivals are more toxic, and existing-user
    toxicity does not uniformly jump after bans.

- [ ] **Remaining cohort toxicity decomposition**
  - Action: add one compact A-D+ cohort summary showing user counts,
    user-weighted toxicity, and activity-weighted toxicity by fixed arrival
    cohort over the full post-FPH period.
  - Output: one manuscript/SI table; add a figure only if the table is not clear.
  - Covers: Reviewer 1 cohort toxicity decomposition; complements PR #8 without
    duplicating weekly event windows.
  - Acceptance: text can say whether elevated toxicity is concentrated in
    particular arrival cohorts and whether the conclusion changes under
    activity weighting.

- [ ] **Arrival-proxy and classifier-validity check**
  - Action: estimate post-ban arrival-proxy noise with a simple pre-event
    baseline/excess-arrival calculation; cite ToxiGen validation and, if fast,
    add a small manual sanity-check sample.
  - Output: proxy-noise table and a short classifier-validity note.
  - Covers: Reviewer 1 proxy-noise and validation requests; Reviewer 2 E1, M4,
    and M7.
  - Acceptance: manuscript clearly says arrivals are event-timed Voat arrivals,
    not verified Reddit migrants, and classifier means are probabilities, not
    observed proportions of toxic content.

## Text, Wording, And Writing Tasks

- [ ] **Retitle and remove causal framing**
  - Action: replace causal terms such as spillover, hostile takeover, caused,
    displaced users, and counterfactual baseline with descriptive wording.
  - Covers: editor title request; Reviewer 1 causal-framing concern; Reviewer 2
    E1.
  - Acceptance: title is under 20 words, has no punctuation, and matches the
    tracking system, manuscript, and cover letter.

- [ ] **Rewrite the abstract and main contribution**
  - Action: foreground the paper as a longitudinal study of receiving-platform
    externalities and concentrated active-arrival effects.
  - Covers: Reviewer 1 contribution buried; Reviewer 2 M6 and M8.
  - Acceptance: remove or attribute the enclave claim; do not present Reddit as
    a causal baseline.

- [ ] **Add a short Results primer**
  - Action: before results, define Voat/generalist communities, dynamic
    reputation, E-I index bounds, comment-to-post edge construction, degree,
    hub rate, degree-share ratio, and parallel social structures.
  - Covers: Reviewer 2 E3.
  - Acceptance: a reader can interpret the first Results section without waiting
    for Methods.

- [ ] **Narrow the mechanism language**
  - Action: replace permanent marginalization/peripheral proof with a fixed
    cohort statement: average arrivals do not broadly capture hubs, but
    high-activity arrivals are much more likely to become hubs.
  - Covers: Reviewer 1 peripheral-dynamics concern; Reviewer 2 E2 and S3.
  - Acceptance: claims match the degree-share, ever-hub, and high-activity hub
    evidence.

- [ ] **Reframe regime and platform comparisons**
  - Action: state that breakpoint analysis tests ban alignment; describe E-I as
    ban-aligned where supported and toxicity/reputation as gradual where not.
    Treat Reddit comparisons as descriptive, not controlled counterfactuals.
  - Covers: Reviewer 1 E-I/regime and Reddit-baseline concerns; Reviewer 2 E1,
    M5, and S1.
  - Acceptance: no sentence implies Voat changes are caused by Reddit bans
    unless supported by the specific breakpoint result.

- [ ] **Soften reputation and toxicity interpretations**
  - Action: describe reputation as activity-based persistence/status rather than
    trust, health, or sustainability; qualify “toxicity doubled” as a change in
    mean classifier probability.
  - Covers: Reviewer 2 M1 and M7.
  - Acceptance: all value-laden terms are either justified or replaced with
    measurement-specific language.

- [ ] **Move key limitations into Results**
  - Action: state near the relevant results that networks use comment-to-post
    replies only; subreddit bans were community bans, not user bans; arrivals
    are self-selected and may include organic Voat users.
  - Covers: Reviewer 2 M2 and M4; Reviewer 1 causal/proxy concerns.
  - Acceptance: limitations are visible where claims are made, not only at the
    end of the paper.

- [ ] **Tighten paragraph-level signposting**
  - Action: add topic and takeaway sentences so statistics are tied to a clear
    claim; rewrite the “Taken together” paragraph around the smaller mechanism.
  - Covers: Reviewer 2 M8 and S2; Reviewer 1 clarity of argument structure.
  - Acceptance: each Results paragraph answers one question and ends with the
    supported interpretation.

## Do Not Add

- Cox hazard-ratio framing unless explicitly requested again.
- More than one new manuscript candidate figure from the fixed-cohort analysis.
- Full detailed curve/user-month tables in the PR.
- Claims that newcomers were permanently peripheral, that toxicity caused
  retention, or that Reddit provides a causal counterfactual baseline.
