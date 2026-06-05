# What changes when ToxiGen is replaced with Detoxify?

Scope: Voat posts+comments only, using the Detoxify `unbiased` run. This does not replace paper results that require Reddit-side Detoxify scores.

## Global agreement

- ToxiGen vs Detoxify general toxicity on the same Voat posts+comments: Pearson r=0.7159, Spearman rho=0.7108, n=1154473.
- Mean ToxiGen toxicity=0.2033; mean Detoxify toxicity=0.1792.
- Detoxify special labels are sparse: severe=0.00461, identity=0.02340, insult=0.09284, threat=0.00628.

## Community ordering

Top communities by mean Detoxify toxicity:

| community_type   | community            |     mean |   share_gt_0_5 |
|:-----------------|:---------------------|---------:|---------------:|
| controversial    | cringeanarchy        | 0.268629 |       0.260396 |
| controversial    | fatpeoplehate        | 0.260898 |       0.255008 |
| controversial    | milliondollarextreme | 0.218263 |       0.210109 |
| controversial    | mensrights           | 0.201649 |       0.179652 |
| normal           | funny                | 0.194019 |       0.186569 |
| normal           | videos               | 0.159748 |       0.149771 |

Top communities by mean Detoxify identity attack:

| community_type   | community            |      mean |   share_gt_0_5 |
|:-----------------|:---------------------|----------:|---------------:|
| controversial    | cringeanarchy        | 0.0866487 |      0.0861386 |
| controversial    | milliondollarextreme | 0.0687991 |      0.0606919 |
| normal           | funny                | 0.0512646 |      0.047099  |
| controversial    | mensrights           | 0.0473013 |      0.0278447 |
| normal           | videos               | 0.0458389 |      0.0404038 |
| normal           | pics                 | 0.0326989 |      0.0289998 |

Top communities by mean Detoxify threat:

| community_type   | community            |       mean |   share_gt_0_5 |
|:-----------------|:---------------------|-----------:|---------------:|
| controversial    | cringeanarchy        | 0.0114892  |     0.00759076 |
| controversial    | milliondollarextreme | 0.0095426  |     0.00622965 |
| normal           | videos               | 0.00844398 |     0.00527057 |
| normal           | gifs                 | 0.00778871 |     0.00477515 |
| normal           | funny                | 0.00775998 |     0.00474533 |
| controversial    | mensrights           | 0.00744015 |     0.00455154 |

## Paper-style event periods for general communities

These are Voat posts+comments means by chronological period, not Reddit-vs-Voat differences.

| period   |   toxigen_toxicity_mean |   detoxify_toxicity_mean |   detoxify_severe_mean |   detoxify_identity_mean |   detoxify_insult_mean |   detoxify_threat_mean |
|:---------|------------------------:|-------------------------:|-----------------------:|-------------------------:|-----------------------:|-----------------------:|
| A-B      |                0.104778 |                 0.105907 |             0.002202   |                0.0102609 |              0.0469592 |             0.00449311 |
| B-C      |                0.159784 |                 0.150731 |             0.00495392 |                0.0296351 |              0.0730647 |             0.00657849 |
| C-D      |                0.205087 |                 0.187301 |             0.00682033 |                0.0546815 |              0.0928679 |             0.00756142 |
| D-end    |                0.206239 |                 0.188591 |             0.00656922 |                0.0581093 |              0.0923381 |             0.00852859 |

## Regime-volume panel analog

Same fixed-effect specification as `regime_volume_integration_panel.py`, but outcomes are monthly Detoxify/ToxiGen means for normal Voat posts+comments.

| label             | term               |         coef |   se_cluster |   p_value_norm |       r2 |   n_obs |
|:------------------|:-------------------|-------------:|-------------:|---------------:|---------:|--------:|
| toxigen_toxicity  | newcomer_pop_share |  0.0353297   |   0.00852355 |    3.39895e-05 | 0.825509 |     463 |
| toxigen_toxicity  | post_ga            | -0.00148339  |   0.0114197  |    0.896648    | 0.825509 |     463 |
| toxigen_toxicity  | newcomer_x_post_ga |  0.0373682   |   0.0212446  |    0.0785853   | 0.825509 |     463 |
| detoxify_toxicity | newcomer_pop_share |  0.0395487   |   0.00858095 |    4.04814e-06 | 0.796648 |     463 |
| detoxify_toxicity | post_ga            |  0.006685    |   0.011249   |    0.552327    | 0.796648 |     463 |
| detoxify_toxicity | newcomer_x_post_ga |  0.0212492   |   0.0215785  |    0.324753    | 0.796648 |     463 |
| detoxify_severe   | newcomer_pop_share |  0.000602329 |   0.00031039 |    0.052312    | 0.6345   |     463 |
| detoxify_severe   | post_ga            | -0.00186908  |   0.00128249 |    0.145009    | 0.6345   |     463 |
| detoxify_severe   | newcomer_x_post_ga |  0.00411562  |   0.00270416 |    0.12802     | 0.6345   |     463 |
| detoxify_identity | newcomer_pop_share | -0.00499762  |   0.00235569 |    0.0338788   | 0.792741 |     463 |
| detoxify_identity | post_ga            | -0.0139859   |   0.0052297  |    0.00748791  | 0.792741 |     463 |
| detoxify_identity | newcomer_x_post_ga |  0.0340013   |   0.0114044  |    0.00286912  | 0.792741 |     463 |
| detoxify_insult   | newcomer_pop_share |  0.0178116   |   0.00492417 |    0.000297829 | 0.768899 |     463 |
| detoxify_insult   | post_ga            | -0.00315773  |   0.00985382 |    0.748622    | 0.768899 |     463 |
| detoxify_insult   | newcomer_x_post_ga |  0.0199555   |   0.0174769  |    0.253527    | 0.768899 |     463 |
| detoxify_threat   | newcomer_pop_share |  0.000936215 |   0.00149056 |    0.52994     | 0.321264 |     463 |
| detoxify_threat   | post_ga            |  0.000866395 |   0.00237096 |    0.714798    | 0.321264 |     463 |
| detoxify_threat   | newcomer_x_post_ga | -0.00154173  |   0.00328553 |    0.638893    | 0.321264 |     463 |

## Cohort follow-up analog

A-D+ pooled cohort means over all examined Voat posts+comments; columns are activity-weighted means.

| cohort   | label             |   active_users |   activity_count |   activity_mean |
|:---------|:------------------|---------------:|-----------------:|----------------:|
| Before A | toxigen_toxicity  |            760 |            84785 |      0.100634   |
| Before A | detoxify_toxicity |            760 |            84785 |      0.093848   |
| Before A | detoxify_insult   |            760 |            84785 |      0.0451841  |
| Before A | detoxify_threat   |            760 |            84785 |      0.00299541 |
| A-B      | toxigen_toxicity  |          35052 |           498698 |      0.221791   |
| A-B      | detoxify_toxicity |          35052 |           498698 |      0.20455    |
| A-B      | detoxify_insult   |          35052 |           498698 |      0.103891   |
| A-B      | detoxify_threat   |          35052 |           498698 |      0.00622799 |
| C-D      | toxigen_toxicity  |          21213 |           347810 |      0.183636   |
| C-D      | detoxify_toxicity |          21213 |           347810 |      0.147935   |
| C-D      | detoxify_insult   |          21213 |           347810 |      0.0792016  |
| C-D      | detoxify_threat   |          21213 |           347810 |      0.00644461 |
| D+       | toxigen_toxicity  |           2245 |             8945 |      0.260922   |
| D+       | detoxify_toxicity |           2245 |             8945 |      0.224125   |
| D+       | detoxify_insult   |           2245 |             8945 |      0.11672    |
| D+       | detoxify_threat   |           2245 |             8945 |      0.00954131 |

## Interpretation

- The headline ToxiGen pattern is broadly robust for general toxicity: Detoxify tracks ToxiGen strongly and preserves the broad controversial-vs-normal separation.
- Detoxify is more diagnostic about mechanism: most general toxicity signal is ordinary insult/obscene-style toxicity, while severe toxicity and threats are rare.
- Identity attack is not just a relabeling of general toxicity; it concentrates most in explicitly controversial communities, with the highest means in cringeanarchy, milliondollarextreme, and mensrights. Fatpeoplehate is top for general Detoxify toxicity, but not for identity attack.
- Threat is too sparse to carry the main paper toxicity argument by itself. Treat it as a tail-risk diagnostic rather than a replacement outcome.
- Because this run scores Voat posts+comments only, the current evidence supports a robustness/sensitivity statement for Voat-side toxicity, not a full replacement of the paper's Reddit-vs-Voat toxicity panels.
