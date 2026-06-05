# What changes when ToxiGen is replaced with Detoxify?

Scope: Voat posts only, using the Detoxify `unbiased` run. This does not replace paper results that require Reddit-side Detoxify scores.

## Global agreement

- ToxiGen vs Detoxify general toxicity on the same Voat posts: Pearson r=0.6935, Spearman rho=0.6528, n=368727.
- Mean ToxiGen toxicity=0.1311; mean Detoxify toxicity=0.1125.
- Detoxify special labels are sparse: severe=0.00226, identity=0.01368, insult=0.05575, threat=0.00316.

## Community ordering

Top communities by mean Detoxify toxicity:

| community_type   | community            |      mean |   share_gt_0_5 |
|:-----------------|:---------------------|----------:|---------------:|
| controversial    | fatpeoplehate        | 0.26063   |      0.252707  |
| controversial    | cringeanarchy        | 0.211567  |      0.205538  |
| controversial    | milliondollarextreme | 0.164708  |      0.153449  |
| controversial    | mensrights           | 0.119085  |      0.08      |
| normal           | funny                | 0.0916625 |      0.0801719 |
| normal           | videos               | 0.0874666 |      0.0725815 |

Top communities by mean Detoxify identity attack:

| community_type   | community            |      mean |   share_gt_0_5 |
|:-----------------|:---------------------|----------:|---------------:|
| controversial    | cringeanarchy        | 0.0716441 |     0.0670927  |
| controversial    | milliondollarextreme | 0.0515668 |     0.0410828  |
| controversial    | mensrights           | 0.0306494 |     0.0144928  |
| normal           | videos               | 0.0277119 |     0.0213659  |
| normal           | funny                | 0.0219047 |     0.0174287  |
| controversial    | fatpeoplehate        | 0.0135492 |     0.00505307 |

Top communities by mean Detoxify threat:

| community_type   | community            |       mean |   share_gt_0_5 |
|:-----------------|:---------------------|-----------:|---------------:|
| controversial    | milliondollarextreme | 0.00805195 |     0.00503333 |
| controversial    | cringeanarchy        | 0.00739909 |     0.00425985 |
| normal           | videos               | 0.00452319 |     0.00221027 |
| controversial    | mensrights           | 0.00434186 |     0.00231884 |
| controversial    | fatpeoplehate        | 0.00405936 |     0.00217897 |
| normal           | gifs                 | 0.00394061 |     0.00137243 |

## Paper-style event periods for general communities

These are Voat posts means by chronological period, not Reddit-vs-Voat differences.

| period   |   toxigen_toxicity_mean |   detoxify_toxicity_mean |   detoxify_severe_mean |   detoxify_identity_mean |   detoxify_insult_mean |   detoxify_threat_mean |
|:---------|------------------------:|-------------------------:|-----------------------:|-------------------------:|-----------------------:|-----------------------:|
| A-B      |               0.0476945 |                0.0468313 |            0.000735603 |                0.0053988 |              0.0188219 |             0.00246912 |
| B-C      |               0.0724068 |                0.0655158 |            0.00135537  |                0.0128429 |              0.0283129 |             0.00315635 |
| C-D      |               0.0874664 |                0.0785679 |            0.00199206  |                0.0225198 |              0.0345543 |             0.00318334 |
| D-end    |               0.0975992 |                0.0877369 |            0.00207638  |                0.0269155 |              0.0385633 |             0.0036091  |

## Regime-volume panel analog

Same fixed-effect specification as `regime_volume_integration_panel.py`, but outcomes are monthly Detoxify/ToxiGen means for normal Voat posts.

| label             | term               |         coef |   se_cluster |   p_value_norm |        r2 |   n_obs |
|:------------------|:-------------------|-------------:|-------------:|---------------:|----------:|--------:|
| toxigen_toxicity  | newcomer_pop_share |  0.00624185  |  0.00756084  |      0.40906   | 0.612455  |     463 |
| toxigen_toxicity  | post_ga            | -0.004873    |  0.0134902   |      0.717932  | 0.612455  |     463 |
| toxigen_toxicity  | newcomer_x_post_ga |  0.0192578   |  0.02215     |      0.384613  | 0.612455  |     463 |
| detoxify_toxicity | newcomer_pop_share |  0.00724985  |  0.00694559  |      0.296575  | 0.594531  |     463 |
| detoxify_toxicity | post_ga            |  0.00262366  |  0.0141498   |      0.852899  | 0.594531  |     463 |
| detoxify_toxicity | newcomer_x_post_ga |  0.0067871   |  0.0221834   |      0.759639  | 0.594531  |     463 |
| detoxify_severe   | newcomer_pop_share |  5.14655e-05 |  0.000162566 |      0.75156   | 0.185737  |     463 |
| detoxify_severe   | post_ga            | -0.000338936 |  0.000569389 |      0.551667  | 0.185737  |     463 |
| detoxify_severe   | newcomer_x_post_ga |  0.00133512  |  0.000991035 |      0.177918  | 0.185737  |     463 |
| detoxify_identity | newcomer_pop_share | -0.00256366  |  0.00130901  |      0.0501752 | 0.596225  |     463 |
| detoxify_identity | post_ga            | -0.000531003 |  0.00712662  |      0.940605  | 0.596225  |     463 |
| detoxify_identity | newcomer_x_post_ga |  0.00407498  |  0.0110092   |      0.711275  | 0.596225  |     463 |
| detoxify_insult   | newcomer_pop_share |  0.00297751  |  0.00396493  |      0.452676  | 0.474907  |     463 |
| detoxify_insult   | post_ga            | -0.000475102 |  0.00778386  |      0.95133   | 0.474907  |     463 |
| detoxify_insult   | newcomer_x_post_ga |  0.00439752  |  0.0130057   |      0.735271  | 0.474907  |     463 |
| detoxify_threat   | newcomer_pop_share | -0.000776187 |  0.0016516   |      0.638383  | 0.0945143 |     463 |
| detoxify_threat   | post_ga            | -0.000344249 |  0.00184959  |      0.85235   | 0.0945143 |     463 |
| detoxify_threat   | newcomer_x_post_ga | -0.000107467 |  0.00270071  |      0.968259  | 0.0945143 |     463 |

## Cohort follow-up analog

A-D+ pooled cohort means over all examined Voat posts; columns are activity-weighted means.

| cohort   | label             |   active_users |   activity_count |   activity_mean |
|:---------|:------------------|---------------:|-----------------:|----------------:|
| Before A | toxigen_toxicity  |            348 |            57879 |      0.0610818  |
| Before A | detoxify_toxicity |            348 |            57879 |      0.0569266  |
| Before A | detoxify_insult   |            348 |            57879 |      0.0266838  |
| Before A | detoxify_threat   |            348 |            57879 |      0.00174038 |
| A-B      | toxigen_toxicity  |          18247 |           131408 |      0.166025   |
| A-B      | detoxify_toxicity |          18247 |           131408 |      0.145064   |
| A-B      | detoxify_insult   |          18247 |           131408 |      0.0726267  |
| A-B      | detoxify_threat   |          18247 |           131408 |      0.0035968  |
| C-D      | toxigen_toxicity  |           8533 |           111277 |      0.117962   |
| C-D      | detoxify_toxicity |           8533 |           111277 |      0.0964317  |
| C-D      | detoxify_insult   |           8533 |           111277 |      0.0477831  |
| C-D      | detoxify_threat   |           8533 |           111277 |      0.00311913 |
| D+       | toxigen_toxicity  |            648 |             2246 |      0.151548   |
| D+       | detoxify_toxicity |            648 |             2246 |      0.139051   |
| D+       | detoxify_insult   |            648 |             2246 |      0.0642056  |
| D+       | detoxify_threat   |            648 |             2246 |      0.00483191 |

## Interpretation

- The headline ToxiGen pattern is broadly robust for general toxicity: Detoxify tracks ToxiGen strongly and preserves the broad controversial-vs-normal separation.
- Detoxify is more diagnostic about mechanism: most general toxicity signal is ordinary insult/obscene-style toxicity, while severe toxicity and threats are rare.
- Identity attack is not just a relabeling of general toxicity; it concentrates most in explicitly controversial communities, with the highest means in cringeanarchy, milliondollarextreme, and mensrights. Fatpeoplehate is top for general Detoxify toxicity, but not for identity attack.
- Threat is too sparse to carry the main paper toxicity argument by itself. Treat it as a tail-risk diagnostic rather than a replacement outcome.
- Because this run scores Voat posts only, the current evidence supports a robustness/sensitivity statement for Voat-side toxicity, not a full replacement of the paper's Reddit-vs-Voat toxicity panels.
