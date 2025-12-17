# Voat Dataset and Timeline (from Mekacher & Papasavva, 2022)

This note extracts key facts about the Voat dataset and a timeline of major Voat events related to major Reddit bans and migrations, based on Mekacher & Papasavva (ICWSM 2022) [mekacher2022Other-a]. Where useful, I reference related entries from `notes/references.bib`.

## Dataset: Scope, Size, Structure, Access
- Scope: Full lifetime of Voat, from the first public post on 2013-11-08 (pre‑launch, in `/v/voatdev`) and official launch in 2014-04, through shutdown on 2020-12-25 [mekacher2022Other-a].
- Size (final released dataset): 2,380,262 submissions; 16,263,309 comments; 113,431 users; 7,095 subverses (Table 3) [mekacher2022Other-a].
- Prior snapshot counts (IAWM extraction): 2,334,817 submissions; 15,731,754 comments; 108,451 users; 7,094 subverses (Table 2) [mekacher2022Other-a].
- Sources: Combined Voat API data with Internet Archive Wayback Machine (IAWM) WARC snapshots released by the Archive Team after shutdown [mekacher2022Other-a].
- File format and organization: newline‑delimited JSON (`.ndjson`).
  - Per‑subverse files: 7,616 `subverse_name_submissions.ndjson` and 7,515 `subverse_name_comments.ndjson` (101 subverses had no comments) [mekacher2022Other-a].
  - Global files: `user_profiles.ndjson` (1) and `subverse_profiles.ndjson` (1). Total 15,133 files [mekacher2022Other-a].
- Schemas (Table 4 highlights) [mekacher2022Other-a]:
  - Submissions: `title`, `body`, `user`, `time`, `date`, `upvotes`, `downvotes`, `net_score`, `domain`, `url`, `subverse`, `comments_count`, etc.
  - Comments: `content`, `user`, `time`, `date`, `upvotes`, `downvotes`, `parent_id`, `submission_id`, etc.
  - User profiles: registration date, bio/intro, activity stats; `mods` (subverses moderated), `owns` (subverses created).
  - Subverse profiles: `subverse`, `subscriber_count`, `about`, `date_created`.
- Access: Released via Zenodo (DOI 10.5281/zenodo.5841668) with documentation; data are primarily in English and were publicly accessible before shutdown [mekacher2022Other-a].
- Relevance signals from paper’s analysis [mekacher2022Other-a]:
  - Links shared heavily from alternative/partisan outlets (e.g., Breitbart, GatewayPundit); frequent use of archive links to avoid traffic to targets.
  - User–community interaction network shows strong narrative clustering; echo‑chamber tendencies in specific subverses (see EI‑homophily below).

## Platform Basics (Voat rules/config, from paper)
- Reddit‑like structure; “subverses” are the equivalent of subreddits. Users can subscribe to many but cannot moderate more than ten subverses. New users must accrue enough comment upvotes before posting submissions [mekacher2022Other-a].

## Activity Highlights (from paper’s figures)
- Most active day: 2015-07-10 with ~5.5K submissions and ~37.5K comments; discussions that day included Donald Trump, vaccine legislation, and Reddit CEO Ellen Pao’s resignation [mekacher2022Other-a].
- Growth plateaus after ~2016; general‑interest subverses (/v/AskVoat, /v/news, /v/politics, /v/videos, /v/funny, /v/whatever) surged during Reddit ban waves [mekacher2022Other-a].
- QAnon on Voat: `/v/GreatAwakening` created 2018-01-01 (months before Reddit’s Q bans); `/v/theawakening` (2018‑09‑12) and `/v/QRV` (2018‑09‑22) rapidly became among the most active, with `/v/QRV` the most active within ~10 days of Reddit’s ban [mekacher2022Other-a].
- Homophily (EI index averages) indicative of echo chambers [mekacher2022Other-a]: `politics` 0.50; `news` 0.40; `whatever` 0.23; `theawakening` 0.01; `GreatAwakening` −0.25; `pizzagate` −0.49; `fatpeoplehate` −0.61; `NeoFAG` −0.74 (more negative → more insular).

## Voat–Reddit Timeline (major events affecting Voat)
Note: Dates and subreddit names are from Table 1 and surrounding narrative in [mekacher2022Other-a]; these are the Reddit moderation events and Voat‑specific responses that measurably affected Voat activity.

- 2013‑11‑08: First Voat post by @Atko in `/v/voatdev` (pre‑launch) [mekacher2022Other-a].
- 2014‑04: Official Voat launch [mekacher2022Other-a].
- 2014‑05‑09: Reddit bans `/r/beatingwomen` (ban #1). 2014‑06‑20: 145 new Voat subverses in one day; 2014‑06‑22: 112 new subverses [mekacher2022Other-a].
- 2014‑09‑06: Reddit bans `/r/TheFappening` (ban #2) [mekacher2022Other-a].
- 2015‑05‑07: Reddit bans `/r/nigger` (ban #3) [mekacher2022Other-a].
- 2015‑06‑06: Reddit bans `/r/fatpeoplehate` (ban #4); heavy traffic to Voat; downtime [mekacher2022Other-a; chandrasekharan2017cant].
- 2015‑06‑19: Host Europe cancels Voat’s hosting (abusive/youth‑endangering/right‑wing extremist content). Days later, PayPal freezes payment processing; Voat closes four subverses (including sexualized‑minors content), moves hosts, and starts accepting crypto donations [mekacher2022Other-a].
- 2015‑07‑05 & 2015‑07‑07: Peak new registrations (2,854 and 3,175 users/day). 2015‑07‑10: Most active day on Voat; also near Ellen Pao’s resignation. Summer 2015: Reddit updates content policy; large DDoS against Voat in July [mekacher2022Other-a].
- 2015‑08: Voat, Inc. registers in the U.S. despite Swiss base (citing U.S. free‑speech law) [mekacher2022Other-a].
- 2016‑11‑23: Reddit bans `/r/pizzagate` (ban #5) [mekacher2022Other-a].
- 2017‑11‑07: Reddit bans `/r/incel` (ban #6) [mekacher2022Other-a].
- 2018‑01‑01: Voat’s `/v/GreatAwakening` created (pre‑ban QAnon community) [mekacher2022Other-a].
- 2018‑03‑15: Reddit bans `/r/CBTS_Stream` (ban #7) [mekacher2022Other-a].
- 2018‑09‑18: Reddit bans `/r/GreatAwakening` (ban #8). On Voat, `/v/theawakening` (2018‑09‑12) and `/v/QRV` (2018‑09‑22) surge; `/v/QRV` becomes the most active subverse within ~10 days [mekacher2022Other-a].
- 2020‑03 → 2020‑12‑22: “Chastain” personally funds Voat since March 2020; final shutdown announcement on 2020‑12‑22 citing lack of funds [mekacher2022Other-a].
- 2020‑12‑25: Voat shuts down; last post by Chastain; Archive Team releases WARC captures used to reconstruct the dataset [mekacher2022Other-a].

## Communities In Focus (this project)
The paper explicitly discusses only some of these. Below indicates what is directly confirmed in [mekacher2022Other-a] versus not explicitly covered there.

- Controversial:
  - fatpeoplehate: Explicit on Reddit ban timeline (2015‑06‑06) and present on Voat as `/v/fatpeoplehate`; among top‑subscribed/active; highly insular (EI ≈ −0.61) [mekacher2022Other-a; chandrasekharan2017cant].
  - GreatAwakening: Explicit; `/v/GreatAwakening` created 2018‑01‑01; Voat’s Q communities (`/v/theawakening`, `/v/QRV`) rapidly dominated activity after Reddit Q bans [mekacher2022Other-a].
  - CringeAnarchy: Not explicitly mentioned in [mekacher2022Other-a] (its 2019 Reddit ban falls outside Table 1’s list ending in 2018).
  - MensRights: Not explicitly mentioned in [mekacher2022Other-a].
  - milliondollarextreme: Not explicitly mentioned in [mekacher2022Other-a].
  - KotakuInAction: Not explicitly mentioned in [mekacher2022Other-a].

- Normal:
  - funny: Explicit; `/v/funny` among top‑subscribed; high image sharing; frequent in overall activity plots [mekacher2022Other-a].
  - videos: Explicit; `/v/videos` among top‑subscribed; frequent in activity plots [mekacher2022Other-a].
  - gaming, gifs, pics, technology: Not explicitly mentioned in [mekacher2022Other-a] (likely present as general subverses, but not highlighted by the paper’s top‑10 analyses).

## Notes for Downstream Analyses (why this matters here)
- Deplatforming/migration: The eight Reddit bans (2014–2018) align with spikes in Voat registrations, subverse creation, and activity; QAnon migration particularly visible in 2018 [mekacher2022Other-a].
- Link ecosystems: Alternative media prominence and archive‑linking patterns are relevant for toxicity and misinformation modules.
- Community structure: The EI‑homophily results suggest strong narrative clustering in targeted communities (e.g., `/v/fatpeoplehate`, QAnon subverses), relevant to core–periphery and sentiment/toxicity interplay.

## Primary Source
- Mekacher, A., & Papasavva, A. (2022). “I Can’t Keep It Up.” A Dataset from the Defunct Voat.co News Aggregator. Proceedings of ICWSM 16, 1302–1311. DOI: 10.1609/icwsm.v16i1.19382 [mekacher2022Other-a].

## Related References (from `notes/references.bib`)
- Reddit 2015 ban study (fatpeoplehate, CoonTown) [chandrasekharan2017cant].
- Post‑Voat Q migration context (to Poal) [papasavva2023waitin].

## Post‑Voat Q Migration (Papasavva & Mariconti, 2023)
- Scope: Mixed‑methods study of QAnon migrations across Reddit → Voat and Voat → Poal; analyzes activity, user overlap, topics, and sentiment toward alternatives [papasavva2023waitin].
- Datasets (Table 1) [papasavva2023waitin]:
  - Reddit: `/r/CBTS_Stream` (30,176 submissions; 267,744 comments; 2017‑12‑20→2018‑02‑28), `/r/greatawakening` (79,952; 926,676; 2018‑01‑09→2018‑08‑19).
  - Voat: `/v/news` (176,948; 1,397,955; 2016‑10‑01→2020‑12‑25), `/v/GreatAwakening` (100,699; 982,702; 2018‑01‑09→2020‑12‑25), `/v/QRV` (185,929; 2,225,702; 2018‑09‑22→2020‑12‑25).
  - Poal: `/s/News` (26,919; 74,431; 2018‑03‑29→2021‑09‑06), `/s/GreatAwakening` (1,889; 2,032; 2019‑07‑13→2021‑09‑06), `/s/QStorm` (19,966; 109,358; 2019‑07‑12→2021‑09‑06), `/s/QPatriots` (5,930; 22,167; 2021‑02‑09→2021‑09‑06).
- Q timeline (Table 2) [papasavva2023waitin]: 2017‑10‑28 first Q drop; 2018‑03‑14 Reddit bans `/r/CBTS_Stream`; 2018‑09‑12 Reddit bans `/r/greatawakening`; 2020‑12‑25 Voat shuts down; 2021‑01‑06 U.S. Capitol attack. Note: the paper also states `/v/GreatAwakening` appears 2018‑01‑09 (same day as `/r/greatawakening`), whereas [mekacher2022Other-a] reports 2018‑01‑01 for creation.
- Platform interplay & timing [papasavva2023waitin]:
  - `/v/GreatAwakening` appears on Voat the same day `/r/greatawakening` appears on Reddit (2018‑01‑09). After Reddit’s 2018‑09‑12 Q bans, average daily submitters on Voat Q subverses rose to ~43.2.
  - Poal’s `/s/QStorm` appears 2019‑09‑02; activity rises near Voat’s shutdown announcement (2020‑12‑21→12‑25). After shutdown, `/s/QStorm` and `/s/GreatAwakening` surge; `/s/QPatriots` appears 2021‑02‑09.
- Migration/overlap (username matching; SHA‑256) [papasavva2023waitin]:
  - Reddit↔Voat: 1.3K shared usernames (≈9.7% of Voat Q‑engaging users).
  - Voat↔Poal: 862 shared usernames (≈43.3% of Poal Q‑engaging users) → about half of Poal users previously had Voat accounts.
  - Scale retention: If Reddit’s Q base ≈31.7K, Voat retained ≈42.1% post‑ban; Poal attracted ≈14.8% compared to Reddit+Voat combined; community shrinks with each ban/shutdown.
- Announced shutdown vs abrupt bans [papasavva2023waitin]:
  - Voat shutdown (pre‑announced) led to more coordinated migration; almost half of active Poal users were Voat migrants who registered after the announcement.
  - After Reddit bans, users did not coalesce around a single alternative; 4chan Q drops influenced Voat as a preferred destination earlier on.
- Alternatives discussed on Voat (last 6 months) [papasavva2023waitin]: Poal mentioned most; sentiment toward alternatives (VADER) shows substantial positive polarity for Poal (≈45.7% positive; ≈28.8% strongly positive), Parler (≈58.8% strongly positive), Gab (≈40.8% strongly positive), GA.win (≈27% strongly positive), while Voat itself also had many positive mentions pre‑shutdown.
- Topics (bigrams) [papasavva2023waitin]:
  - Voat Q before/after announcement: “president trump,” “martial law,” “deep state,” “election fraud,” “q post” → after: slurs (“zee bad,” “bad jew”) and holiday greetings dominate.
  - Poal Q after (Dec 21–30, 2020): Q‑themes plus “jan 6,” “insurrection act”; manual inspection shows premeditated discussion of the Jan 6 attack more than a week prior.
- Conclusion [papasavva2023waitin]: Poal emerges as “new Voat” for Q communities but at reduced scale; continued echo chambers and harmful content; practical effect of announced shutdowns is more organized migration.

## /v/GreatAwakening Date Discrepancy
- Mekacher & Papasavva (2022): Reports `/v/GreatAwakening` was created on 2018‑01‑01 [mekacher2022Other-a].
- Papasavva & Mariconti (2023/2024): States `/v/GreatAwakening` “appears” on 2018‑01‑09, same day as `/r/greatawakening`; Table 1 spans Voat `/v/GreatAwakening` from 2018‑01‑09 to 2020‑12‑25 [papasavva2023waitin].
- Interpretation: Likely “creation date” (subverse profile) vs “first observed activity” (earliest submission/comment in their dataset window). Both dates are within 8 days; analyses remain consistent.

### Communities In Focus: Mentions in Papasavva & Mariconti (2023)
- Controversial (this project):
  - GreatAwakening: Explicitly central. Uses `/r/greatawakening`, `/v/GreatAwakening`, `/s/GreatAwakening`, plus Voat `/v/QRV` and Poal `/s/QStorm`, `/s/QPatriots` as key Q communities.
  - fatpeoplehate, CringeAnarchy, MensRights, milliondollarextreme, KotakuInAction: Not discussed in this manuscript.
- Normal (this project):
  - videos, funny, gaming, gifs, pics, technology: Not discussed as communities. Paper includes a “News” baseline (`/v/news`, `/s/News`) but not these specific normals.

## Deplatforming Effects and Alt‑Platforms (Ali et al., 2021)
- Scope: Studies users suspended on Twitter/Reddit who migrate to Gab; measures activity, toxicity, and audience changes post‑migration [ali2021unders].
- Key findings (context for deplatforming):
  - Migrants to Gab become more active and more toxic after suspension, but their reachable audience shrinks (loss of followers) [ali2021unders].
  - Lower‑bound mapping: ~2.5% of Gab accounts can be reliably linked to a previously suspended Twitter/Reddit account; many mapped accounts are created after the suspension event [ali2021unders].
- Mentions of Voat (relevance to this project):
  - Alt‑platform landscape: Names Voat among destinations (with Parler, WrongThink, PewTube) where suspended/banned users migrate; suggests measuring migrations to these communities for a fuller picture [ali2021unders].
  - Prior cross‑platform matching: Cites Newell et al. 2016, which matched usernames across platforms including Voat to study migration during Reddit unrest [ali2021unders].
  - QAnon on Voat: References Papasavva et al. 2020 (“is it a qoincidence?”) as an early quantitative study of QAnon on Voat [ali2021unders].
- Takeaway for our analyses: Supports the hypothesis that bans on mainstream platforms can increase activity/toxicity on fringe destinations; motivates explicit measurement of Reddit→Voat migrations alongside toxicity/sentiment dynamics, and comparison with Voat→Poal patterns.

## Persistent Interaction Patterns (Avalle et al., 2024)
- Scope: Comparative study of ~500M comments across eight platforms (Facebook, Gab, Reddit, Telegram, Twitter, Usenet, Voat, YouTube) over 34 years; focuses on how toxicity and participation scale with conversation size [avalle2024persis].
- Datasets (Table 1 excerpts) [avalle2024persis]:
  - Voat: conspiracy (2018‑01‑09→2020‑12‑25: 1,024,812 comments; 99,953 users; 27,641 threads; toxicity 0.10), news (2013‑11‑21→2020‑12‑25: 1,397,955; 170,801; 88,434; toxicity 0.19), politics (2014‑06‑19→2020‑12‑25: 1,083,932; 143,103; 66,424; toxicity 0.19).
  - Reddit: conspiracy (2018‑01‑01→2022‑12‑08: 777,393 comments; 92,678 users; 35,092 threads; toxicity 0.07), news (2018‑01‑01→2018‑12‑31: 389,582; 109,860; 7,798; toxicity 0.09), science (2018‑01‑01→2022‑12‑11: 549,543; 211,546; 28,330; toxicity 0.01), climate change (2018‑01‑01→2022‑12‑12: 70,648; 26,521; 5,057; toxicity 0.07), vaccines (2018‑01‑01→2022‑11‑06: 66,457; 5,192; 4,539; toxicity 0.04).
- Key findings relevant to Voat/Reddit [avalle2024persis]:
  - Longer conversations consistently exhibit higher toxicity across platforms; yet toxicity does not necessarily reduce participation.
  - Fraction of toxic comments is mostly <10% across datasets; Voat news/politics are notable higher (≈19%). Extremely toxic users are rare in every dataset.
  - Participation pattern: as threads grow, fewer unique users contribute more (decreasing participants, increasing per‑user contribution) — consistent across platforms/topics.
  - Conversation peaks (bursts) align with higher toxicity levels (Extended Data Table 4).
- Relevance to this project: Control for conversation length when comparing toxicity across Voat/Reddit and across communities; note Voat news/politics higher toxic share than Reddit news; “Voat conspiracy” likely aggregates Q‑subverses (e.g., `/v/GreatAwakening`, `/v/QRV`), but subverses are not explicitly named in this paper.

### Voat vs Reddit Toxicity Benchmarks (Avalle 2024)
- News: Voat ≈ 0.19 vs Reddit ≈ 0.09 → ~2.1× higher on Voat [avalle2024persis].
- Conspiracy: Voat ≈ 0.10 vs Reddit ≈ 0.07 → ~1.4× higher on Voat [avalle2024persis].
- Politics: Voat ≈ 0.19 (no Reddit politics series in Table 1 for direct comparison) [avalle2024persis].
- Other Reddit baselines for context: science ≈ 0.01, vaccines ≈ 0.04, climate change ≈ 0.07 [avalle2024persis].

Normalization suggestions (toxicity module)
- Per‑topic platform baseline: compute normalized toxicity as either ratio `tox / baseline_topic_platform` or difference `tox − baseline_topic_platform` to compare Voat vs Reddit fairly.
- Control for conversation size: calibrate within size bins (e.g., 6–20, 21–50, 51+) or include thread length as a covariate, since longer threads are more toxic across platforms [avalle2024persis].
- Robustness: use Wilson CIs on proportions; consider winsorizing extreme outliers; align Perspective API threshold at 0.6 for comparability with Avalle et al. [avalle2024persis].

## Users’ Volatility on Reddit and Voat (Di Marco et al., 2023)
- Scope: Analyses user exploration and attention allocation across communities on Reddit and Voat during 2019 (~215M comments; ~16M users) [diMarco2023users].
- Data and preprocessing [diMarco2023users]:
  - Reddit via Pushshift; Voat dataset from Mekacher & Papasavva (2022) [mekacher2022Other-a].
  - Removed 8Chan, Anon, and QRV (Voat) due to identity anonymization codes.
  - Included communities with ≥30 commenting users and at least one comment in every month of 2019. Final: Voat 23,189 users; 2,206,665 comments; 237 subverses. Reddit 16,458,011 users; 215,496,434 comments; 24,780 subreddits (post‑filters).
- Key methods and findings [diMarco2023users]:
  - Exploration sublinear over time: Users keep exploring new communities but allocate most comments to a small, stable set of preferred communities; average exploration metric Ū(t) fits show stability through 2019 in both platforms.
  - Turnover high: Comments‑per‑user distributions per community fit power‑laws (p‑value thresholds), indicating most users leave quickly; a minority stay longer. Jaccard similarity of monthly user sets decays roughly as a power‑law (rapid drop), in both Voat and Reddit.
  - Activity vs retention: Users with higher activity are more likely to return month‑to‑month (shown for biggest 9 communities on each platform).
  - Topic stability: Using sentence‑embedding CA (all‑mpnet‑base‑v2) on names+descriptions, preferred communities change but topical coordinates remain similar over time; per‑community CA coordinates reported monthly.
- Communities explicitly listed for Voat (size ≥1.5K, 2019) [diMarco2023users]: `AskVoat`, `funny`, `GreatAwakening`, `news`, `politics`, `theawakening`, `videos`, `whatever` (appearing in CA tables/figures). Note: `QRV` excluded by preprocessing.
- Relevance: Confirms centrality of our focus communities on Voat in 2019 (GreatAwakening; normals like funny/videos), while highlighting that QRV is omitted due to anonymization. Supports modeling user turnover and stable preference sets when comparing Voat vs Reddit networks and reputational dynamics.

### Topic Stability (why it matters here)
- Concept: Users’ preferred communities change over time, but the topics they engage with remain similar (community embeddings + CA coordinates remain near a stable region) [diMarco2023users].
- Operationalization: Encodes community names/descriptions with `all-mpnet-base-v2`; tracks month-by-month CA coordinates for large subverses (e.g., `GreatAwakening`, `theawakening`, `news`, `politics`, `funny`, `videos`) showing limited drift [diMarco2023users].
- Value for our analyses:
  - Confounding control: When comparing toxicity/sentiment over time, stable topics reduce topic-drift confounds; observed changes more likely reflect platform/community dynamics rather than content shifts.
  - Migration lens: Migrants often preserve topical preference (e.g., Q communities); helps align Voat vs Reddit vs Poal comparisons by topic, not just by community name.
  - Core–periphery: Stability supports persistent topical “cores” with volatile peripheries; useful for interpreting stability of block labels and interplay of reputation/toxicity within cores vs peripheries.
  - Reputation dynamics: Topic-stable engagement suggests we can attribute reputation changes to behavior/structure rather than theme changes; enables per-topic normalization.
  - Cross-platform mapping: Facilitates matching analogous communities (e.g., Reddit conspiracy ↔ Voat conspiracy/Q subverses) via topical vectors when names differ or are filtered (QRV excluded).

## Conversation Size & Engagement (Nudo et al., 2025)
- Scope: Six-platform, 33-year comparison of conversation dynamics; studies how conversation size and community outreach size relate to user re-entry (engagement) [nudo2025niche]. Platforms include Reddit and Voat (data from [mekacher2022Other-a]).
- Data breakdown (Table 1) [nudo2025niche]:
  - Voat: 153,255 users; 3,454,791 comments; 413,854 threads; time range Nov 2013–Dec 2020.
  - Reddit: 394,733 users; 1,798,628 comments; 808,016 threads; time range Jan 2018–Dec 2022.
- Key measures [nudo2025niche]:
  - Localization parameter L: probability of re-entry (leaving more than one comment) within a thread; analyzed vs number of participants and vs community outreach size.
- Findings relevant to Voat/Reddit [nudo2025niche]:
  - Re-entry vs participants: On Reddit and Voat, engagement (L) increases with number of participants up to ≈150 users, then declines; peak aligns with Dunbar’s number (cognitive limit), suggesting human constraints bound sustained dialogue in larger groups.
  - Re-entry vs outreach size: Across platforms, larger communities (greater outreach) correlate with reduced likelihood of re-entry; effect strongest on mainstream platforms; niche platforms preserve higher engagement as size grows.
  - Platform contrast: Smaller/niche (e.g., Voat, Usenet, Gab) show richer, sustained interactions; larger/mainstream (Facebook, Twitter) favor broader but shorter participation.
- Relevance for our project:
  - Toxicity/sentiment normalization: Include participant count and outreach size as covariates when modeling engagement-linked outcomes (toxicity often rises with size; re-entry nonmonotonic with participants).
  - Core–periphery: Peak engagement near ~150 participants suggests a natural boundary for “core” conversational cohesion; beyond that, periphery grows and engagement diffuses.
- Community comparisons: When benchmarking Voat vs Reddit communities, stratify analyses by participant-count bins (≤150 vs >150) and by outreach deciles to avoid scale-induced biases.

## Deplatforming and Alt‑Platform Ecology (Rogers, 2020)
- Scope: Follows deplatformed “extreme Internet celebrities” to Telegram and alternative social media; examines whether deplatforming “works” and for whom [rogers2020deplat].
- Findings/context [rogers2020deplat]:
  - Effectiveness on mainstream: Echoes Reddit 2015 ban findings — on‑platform harassment declines; some offenders leave; recipient subreddits do not inherit elevated extreme speech (cites [chandrasekharan2017cant]).
  - Migration targets: Notes alternative platforms gaining migrants and attention (Telegram, Gab, and Voat). Mentions that deplatformed Pizzagate, incel, and QAnon subreddit users are said to have migrated to Voat (and Gab).
  - Platform boost: When deplatformed celebrities migrate, alt‑platforms receive media attention and user influx.
  - Open question: While bans benefit the mainstream platform’s metrics, effects on the broader Internet ecology remain under‑studied.
- Relevance here: Supports our cross‑platform framing (Reddit → Voat/Gab/Telegram), including Q‑related migrations touching `/v/GreatAwakening`/`/v/QRV`; complements migration and toxicity dynamics from other sources.

### Multi‑Event Months (alignment with Rogers)
- 2015‑06: Reddit bans (e.g., `/r/fatpeoplehate`) trigger migration; Voat hosting/payment crises occur days later. Aligns with Rogers’ narrative: bans benefit Reddit’s on‑site metrics while boosting alt‑platform attention/uptake (Voat, Gab) [rogers2020deplat; chandrasekharan2017cant; mekacher2022Other-a].
- 2015‑07: Continued unrest (admin ban), major DDoS, record Voat activity (07‑10). Consistent with post‑ban turbulence and alt‑platform visibility effects (Rogers) [rogers2020deplat; mekacher2022Other-a].
- 2018‑09: Reddit bans QAnon (`/r/GreatAwakening`); Voat Q subverses surge (`/v/theawakening`, `/v/QRV`). Rogers notes QAnon migration paths to Voat and Telegram (alt‑platform ecology) [rogers2020deplat; mekacher2022Other-a].
- 2020‑12: Voat shutdown announcement (12‑22) and closure (12‑25). While outside Rogers’ primary case set, the observed Voat→Poal migration (Papasavva & Mariconti 2023) fits the broader deplatforming ecology perspective (flows across alt‑platforms) [papasavva2023waitin].
- 2014‑06: Early Reddit moderation and rapid Voat subverse creation spikes (06‑20, 06‑22) reflect the same displacement mechanism highlighted by Rogers (mainstream moderation → alt‑platform growth) [mekacher2022Other-a; rogers2020deplat].

## Platform Centralization via User–Community Structure (Trujillo et al., 2024)
- Scope: Introduces a disruption‑curve metric on bipartite user–community networks to quantify how removing influential communities degrades a platform; compares five platforms including Voat [trujillo2024measur].
- Data (Table 2) [trujillo2024measur]:
  - Voat: 7,515 communities; 3,624,486 “users” (vertex count as modeled); 16,263,309 edges (comment‑weighted user↔subverse relationships; before compression). Source aligned with Mekacher & Papasavva dataset.
- Method (intuition) [trujillo2024measur]:
  - Build bipartite graph users↔communities with weights (e.g., number of comments by a user in a subverse).
  - Rank communities by structural influence (how many remaining user–community edges would be severed if removed; bridges consideration).
  - Remove communities in order; plot cumulative “disruption” (fraction of remaining graph impacted) → platform‑level centralization signature; also supports community‑level influence scores.
- Findings for Voat [trujillo2024measur]:
  - Size vs structure: Voat shows the most skewed community size distribution, yet removing the largest community impacts <0.03% of the remaining graph; only after removing the top three does >10% become impacted. Size distribution alone is insufficient for centralization.
  - Explanation: New Voat accounts were auto‑subscribed to a default set of 27 subverses, inflating sizes of certain communities without conferring proportionate structural centrality (low bridging).
  - Comparative: Even platforms designed to be decentralized (e.g., Mastodon) can be more centralized than synthetic baselines; Voat’s skewed sizes did not translate to extreme structural centrality under this metric.
- Relevance to our project:
  - Complement core–periphery: Use disruption curves monthly to quantify platform/community centralization beyond size or modularity; compare with ρCC/ρPP and core size.
  - Default‑subscription caveat: When interpreting Voat’s top‑sized subverses (e.g., AskVoat/news/whatever), account for auto‑subscribe effects; prefer structural influence over raw size.
  - Community‑level influence: Identify communities whose removal disproportionately fragments remaining users; track changes around events (2015/2018/2020) and relate to reputation/toxicity shifts.


## Reddit 2015 Ban Effects (Chandrasekharan et al., 2017)
- Scope: Quasi‑experimental analysis of Reddit’s 2015 bans of `/r/fatpeoplehate` (FPH) and `/r/CoonTown` using >100M posts/comments; builds hate‑speech lexicons; uses causal inference (matching, diff‑in‑diff) [chandrasekharan2017cant].
- Core findings [chandrasekharan2017cant]:
  - The ban “worked for Reddit”: more banned‑community users than expected discontinued using Reddit; those who stayed decreased hate‑speech usage by ≥80%.
  - Recipient subreddits that received migrants did not inherit increased hate‑speech rates when controlling for site‑wide trends.
  - Within‑Reddit migration patterns: many `/r/CoonTown` users moved to subreddits like `/r/The_Donald`, `/r/homeland`, `/r/BlackCrimeMatters`; many `/r/fatpeoplehate` users moved to `/r/RoastMe`, gaming (`/r/fo4`), and TV show (`/r/MrRobot`) subreddits.
- Voat relevance [chandrasekharan2017cant]:
  - Confirms off‑platform migration to Voat (and Snapzu, Empeopled) during/after unrest; reports that 1,536 `/r/fatpeoplehate` users had exact‑match usernames on Voat, where Voat equivalents of the banned subreddits continued racism/fat‑shaming.
  - Interprets Reddit’s bans as shifting harms off‑platform (“someone else’s problem”), while reducing on‑site harm metrics.
- Takeaway for this project: Reinforces linking Reddit ban dates (2015) to Voat influx and the need to quantify how migration reshaped Voat’s network/reputation/toxicity dynamics, while noting that Reddit‑side metrics improved even as Voat absorbed migrants.

### Key Data Points (Chandrasekharan 2017)
- ≥80%: Reduction in hate‑speech usage by remaining users from banned communities [chandrasekharan2017cant].
- ~2x: Migrants’ posting activity within recipient subreddits post‑ban (reallocation from banned subs) [chandrasekharan2017cant].
- 1,536: Exact‑match usernames from `/r/fatpeoplehate` found on Voat (users reorganized in Voat equivalents) [chandrasekharan2017cant].
- 0 site‑level spillover: Recipient subreddits did not inherit elevated hate‑speech rates when controlling for trends [chandrasekharan2017cant].

## Community Crosswalk (Coverage by Sources)
Legend: Explicit = directly named/analyzed; Implicit = referenced conceptually or in related work; Not mentioned = no reference.

- fatpeoplehate
  - [mekacher2022Other-a]: Explicit — `/v/fatpeoplehate`; Voat activity and EI homophily; tied to 2015 ban.
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Explicit in related work context of Reddit 2015 bans; not in their dataset.
  - [chandrasekharan2017cant]: Explicit — primary banned community studied; provides ban effects and migration context (incl. Voat matches).
  - [avalle2024persis]: Not mentioned (topic‑level Voat datasets only).
  - [nudo2025niche]: Not mentioned (platform-level conversation dynamics; no community names).
  - [rogers2020deplat]: Explicit — Reddit ban example; mentions migration to Voat/Gab/Telegram.
  - [trujillo2024measur]: Not mentioned (platform-level centralization; no named communities).

- GreatAwakening
  - [mekacher2022Other-a]: Explicit — `/v/GreatAwakening` (+ `/v/theawakening`, `/v/QRV`).
  - [papasavva2023waitin]: Explicit — `/r/greatawakening`, `/v/GreatAwakening`, `/s/GreatAwakening` central to analysis.
  - [ali2021unders]: Implicit — cites QAnon on Voat work; no specific subverse analyzed.
  - [avalle2024persis]: Implicit — covered via “Voat conspiracy” topic, subverses not named.
  - [nudo2025niche]: Not mentioned explicitly.
  - [diMarco2023users]: Explicit — appears among Voat top subverses (2019 CA tables/figures); QRV excluded by preprocessing.
  - [trujillo2024measur]: Not mentioned explicitly.

- CringeAnarchy
  - [mekacher2022Other-a]: Not mentioned.
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Not mentioned.
  - [avalle2024persis]: Not mentioned.
  - [nudo2025niche]: Not mentioned.

- MensRights
  - [mekacher2022Other-a]: Not mentioned.
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Not mentioned.
  - [avalle2024persis]: Not mentioned.
  - [nudo2025niche]: Not mentioned.

- milliondollarextreme
  - [mekacher2022Other-a]: Not mentioned.
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Not mentioned.
  - [avalle2024persis]: Not mentioned.
  - [nudo2025niche]: Not mentioned.

- KotakuInAction
  - [mekacher2022Other-a]: Not mentioned.
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Not mentioned.
  - [avalle2024persis]: Not mentioned.
  - [nudo2025niche]: Not mentioned.

- funny
  - [mekacher2022Other-a]: Explicit — `/v/funny` high image sharing; appears in activity plots.
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Not mentioned.
  - [avalle2024persis]: Not mentioned.
  - [nudo2025niche]: Not mentioned.
  - [diMarco2023users]: Explicit — appears among Voat top subverses (2019 CA tables/figures).

- videos
  - [mekacher2022Other-a]: Explicit — `/v/videos` present in activity plots.
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Not mentioned.
  - [avalle2024persis]: Not mentioned.
  - [nudo2025niche]: Not mentioned.
  - [diMarco2023users]: Explicit — appears among Voat top subverses (2019 CA tables/figures).

- gaming
  - [mekacher2022Other-a]: Not mentioned as a highlighted subverse.
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Not mentioned.
  - [avalle2024persis]: Not mentioned.
  - [nudo2025niche]: Not mentioned.

- gifs
  - [mekacher2022Other-a]: Not mentioned as a highlighted subverse.
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Not mentioned.
  - [avalle2024persis]: Not mentioned.
  - [nudo2025niche]: Not mentioned.

- pics
  - [mekacher2022Other-a]: Not mentioned as a highlighted subverse (image sharing noted broadly).
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Not mentioned.
  - [avalle2024persis]: Not mentioned.
  - [nudo2025niche]: Not mentioned.

- technology
  - [mekacher2022Other-a]: Not mentioned as a highlighted subverse.
  - [papasavva2023waitin]: Not mentioned.
  - [ali2021unders]: Not mentioned.
  - [avalle2024persis]: Not mentioned.
  - [nudo2025niche]: Not mentioned.
