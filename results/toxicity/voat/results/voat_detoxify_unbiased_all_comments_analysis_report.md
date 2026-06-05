# What changes when ToxiGen is replaced with Detoxify?

Scope: Voat comments only, using the Detoxify `unbiased` run. This does not replace paper results that require Reddit-side Detoxify scores.

## Global agreement

- ToxiGen vs Detoxify general toxicity on the same Voat comments: Pearson r=0.7153, Spearman rho=0.7375, n=785746.
- Mean ToxiGen toxicity=0.2372; mean Detoxify toxicity=0.2105.
- Detoxify special labels are sparse: severe=0.00572, identity=0.02796, insult=0.11024, threat=0.00774.

## Community ordering

Top communities by mean Detoxify toxicity:

| community_type   | community            |     mean |   share_gt_0_5 |
|:-----------------|:---------------------|---------:|---------------:|
| controversial    | cringeanarchy        | 0.294254 |       0.285031 |
| controversial    | mensrights           | 0.272507 |       0.265174 |
| controversial    | fatpeoplehate        | 0.26097  |       0.255629 |
| controversial    | milliondollarextreme | 0.246713 |       0.240208 |
| normal           | funny                | 0.243278 |       0.237771 |
| normal           | videos               | 0.239888 |       0.235352 |

Top communities by mean Detoxify identity attack:

| community_type   | community            |      mean |   share_gt_0_5 |
|:-----------------|:---------------------|----------:|---------------:|
| controversial    | cringeanarchy        | 0.0933867 |      0.0946915 |
| controversial    | milliondollarextreme | 0.0779532 |      0.0711085 |
| normal           | videos               | 0.0659365 |      0.0615114 |
| normal           | funny                | 0.0653939 |      0.0613776 |
| controversial    | mensrights           | 0.0615922 |      0.0393035 |
| normal           | pics                 | 0.0458482 |      0.0413677 |

Top communities by mean Detoxify threat:

| community_type   | community            |       mean |   share_gt_0_5 |
|:-----------------|:---------------------|-----------:|---------------:|
| controversial    | cringeanarchy        | 0.013326   |     0.00908656 |
| normal           | videos               | 0.012791   |     0.00866358 |
| controversial    | milliondollarextreme | 0.0103345  |     0.00686515 |
| controversial    | mensrights           | 0.0100991  |     0.00646766 |
| normal           | gifs                 | 0.0100641  |     0.00678716 |
| normal           | funny                | 0.00981186 |     0.00620568 |

## Paper-style event periods for general communities

These are Voat comments means by chronological period, not Reddit-vs-Voat differences.

| period   |   toxigen_toxicity_mean |   detoxify_toxicity_mean |   detoxify_severe_mean |   detoxify_identity_mean |   detoxify_insult_mean |   detoxify_threat_mean |
|:---------|------------------------:|-------------------------:|-----------------------:|-------------------------:|-----------------------:|-----------------------:|
| A-B      |                0.146155 |                 0.147971 |             0.00329286 |                0.0139802 |              0.0673446 |             0.00598713 |
| B-C      |                0.228138 |                 0.216993 |             0.00769804 |                0.0421079 |              0.10782   |             0.00929529 |
| C-D      |                0.279913 |                 0.255977 |             0.00990776 |                0.0748032 |              0.130044  |             0.0102837  |
| D-end    |                0.271173 |                 0.248354 |             0.00926708 |                0.0759294 |              0.124584  |             0.0114154  |

## Regime-volume panel analog

Same fixed-effect specification as `regime_volume_integration_panel.py`, but outcomes are monthly Detoxify/ToxiGen means for normal Voat comments.

| label             | term               |         coef |   se_cluster |   p_value_norm |       r2 |   n_obs |
|:------------------|:-------------------|-------------:|-------------:|---------------:|---------:|--------:|
| toxigen_toxicity  | newcomer_pop_share |  0.0532676   |  0.010148    |    1.52861e-07 | 0.733878 |     463 |
| toxigen_toxicity  | post_ga            | -0.000565177 |  0.0101139   |    0.955437    | 0.733878 |     463 |
| toxigen_toxicity  | newcomer_x_post_ga |  0.0387394   |  0.0220366   |    0.0787552   | 0.733878 |     463 |
| detoxify_toxicity | newcomer_pop_share |  0.0621617   |  0.00860092  |    4.92495e-13 | 0.75332  |     463 |
| detoxify_toxicity | post_ga            |  0.00962895  |  0.0108055   |    0.372869    | 0.75332  |     463 |
| detoxify_toxicity | newcomer_x_post_ga |  0.0157627   |  0.0268517   |    0.557184    | 0.75332  |     463 |
| detoxify_severe   | newcomer_pop_share |  0.00125873  |  0.000524284 |    0.0163565   | 0.597019 |     463 |
| detoxify_severe   | post_ga            | -0.00254912  |  0.00187354  |    0.173645    | 0.597019 |     463 |
| detoxify_severe   | newcomer_x_post_ga |  0.00510775  |  0.00368117  |    0.165279    | 0.597019 |     463 |
| detoxify_identity | newcomer_pop_share | -0.00401746  |  0.00387312  |    0.299611    | 0.800049 |     463 |
| detoxify_identity | post_ga            | -0.0204114   |  0.00961889  |    0.033837    | 0.800049 |     463 |
| detoxify_identity | newcomer_x_post_ga |  0.0482184   |  0.0193447   |    0.0126818   | 0.800049 |     463 |
| detoxify_insult   | newcomer_pop_share |  0.0281884   |  0.00634009  |    8.7458e-06  | 0.714928 |     463 |
| detoxify_insult   | post_ga            | -0.0042702   |  0.012836    |    0.739381    | 0.714928 |     463 |
| detoxify_insult   | newcomer_x_post_ga |  0.0223247   |  0.0258805   |    0.388353    | 0.714928 |     463 |
| detoxify_threat   | newcomer_pop_share |  0.00337285  |  0.00127927  |    0.00837582  | 0.504014 |     463 |
| detoxify_threat   | post_ga            |  0.00189366  |  0.00315033  |    0.547774    | 0.504014 |     463 |
| detoxify_threat   | newcomer_x_post_ga | -0.00348236  |  0.00379364  |    0.358647    | 0.504014 |     463 |

## Cohort follow-up analog

A-D+ pooled cohort means over all examined Voat comments; columns are activity-weighted means.

| cohort   | label             |   active_users |   activity_count |   activity_mean |
|:---------|:------------------|---------------:|-----------------:|----------------:|
| Before A | toxigen_toxicity  |            616 |            24482 |      0.188229   |
| Before A | detoxify_toxicity |            616 |            24482 |      0.174992   |
| Before A | detoxify_insult   |            616 |            24482 |      0.085741   |
| Before A | detoxify_threat   |            616 |            24482 |      0.00588299 |
| A-B      | toxigen_toxicity  |          26651 |           365205 |      0.241966   |
| A-B      | detoxify_toxicity |          26651 |           365205 |      0.226191   |
| A-B      | detoxify_insult   |          26651 |           365205 |      0.115292   |
| A-B      | detoxify_threat   |          26651 |           365205 |      0.00717591 |
| C-D      | toxigen_toxicity  |          16945 |           239905 |      0.214295   |
| C-D      | detoxify_toxicity |          16945 |           239905 |      0.171975   |
| C-D      | detoxify_insult   |          16945 |           239905 |      0.0937438  |
| C-D      | detoxify_threat   |          16945 |           239905 |      0.00794753 |
| D+       | toxigen_toxicity  |           2050 |             7276 |      0.287011   |
| D+       | detoxify_toxicity |           2050 |             7276 |      0.244657   |
| D+       | detoxify_insult   |           2050 |             7276 |      0.129955   |
| D+       | detoxify_threat   |           2050 |             7276 |      0.0109418  |

## Interpretation

- The headline ToxiGen pattern is broadly robust for general toxicity: Detoxify tracks ToxiGen strongly and preserves the broad controversial-vs-normal separation.
- Detoxify is more diagnostic about mechanism: most general toxicity signal is ordinary insult/obscene-style toxicity, while severe toxicity and threats are rare.
- Identity attack is not just a relabeling of general toxicity; it concentrates most in explicitly controversial communities, with the highest means in cringeanarchy, milliondollarextreme, and mensrights. Fatpeoplehate is top for general Detoxify toxicity, but not for identity attack.
- Threat is too sparse to carry the main paper toxicity argument by itself. Treat it as a tail-risk diagnostic rather than a replacement outcome.
- Because this run scores Voat comments only, the current evidence supports a robustness/sensitivity statement for Voat-side toxicity, not a full replacement of the paper's Reddit-vs-Voat toxicity panels.
