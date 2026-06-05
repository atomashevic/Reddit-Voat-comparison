# Detoxify vs ToxiGen Voat all-comment run

- scored_rows: 785746
- interaction_type: comment
- detoxify_model: unbiased
- requested_device: cuda
- model_device: cuda:0
- torch_version: 2.7.1+cu126
- cuda_available: True
- cuda_device: NVIDIA A30

## Global toxicity correlation

- n=785746; Pearson r=0.7153; Spearman rho=0.7375
- mean ToxiGen toxicity=0.2372
- mean Detoxify toxicity=0.2105

## Community counts

| platform   | community            | community_type   | interaction_type   |   eligible_rows |   scored_rows | score_file                                                          |
|:-----------|:---------------------|:-----------------|:-------------------|----------------:|--------------:|:--------------------------------------------------------------------|
| voat       | cringeanarchy        | controversial    | comment            |            2091 |          2091 | voat_detoxify_unbiased_all_comments_cringeanarchy_scores.csv        |
| voat       | fatpeoplehate        | controversial    | comment            |          277140 |        277140 | voat_detoxify_unbiased_all_comments_fatpeoplehate_scores.csv        |
| voat       | greatawakening       | controversial    | comment            |          221673 |        221673 | voat_detoxify_unbiased_all_comments_greatawakening_scores.csv       |
| voat       | mensrights           | controversial    | comment            |            2010 |          2010 | voat_detoxify_unbiased_all_comments_mensrights_scores.csv           |
| voat       | milliondollarextreme | controversial    | comment            |           13838 |         13838 | voat_detoxify_unbiased_all_comments_milliondollarextreme_scores.csv |
| voat       | kotakuinaction       | controversial    | comment            |            4857 |          4857 | voat_detoxify_unbiased_all_comments_kotakuinaction_scores.csv       |
| voat       | funny                | normal           | comment            |           97169 |         97169 | voat_detoxify_unbiased_all_comments_funny_scores.csv                |
| voat       | gaming               | normal           | comment            |           40824 |         40824 | voat_detoxify_unbiased_all_comments_gaming_scores.csv               |
| voat       | gifs                 | normal           | comment            |           13555 |         13555 | voat_detoxify_unbiased_all_comments_gifs_scores.csv                 |
| voat       | pics                 | normal           | comment            |           23690 |         23690 | voat_detoxify_unbiased_all_comments_pics_scores.csv                 |
| voat       | technology           | normal           | comment            |           48500 |         48500 | voat_detoxify_unbiased_all_comments_technology_scores.csv           |
| voat       | videos               | normal           | comment            |           40399 |         40399 | voat_detoxify_unbiased_all_comments_videos_scores.csv               |

## Per-community Detoxify toxicity correlations

| community_type   | community            | toxigen_col      | detoxify_col      |      n |   toxigen_mean |   detoxify_mean |   pearson_r |    pearson_p |   spearman_rho |   spearman_p |
|:-----------------|:---------------------|:-----------------|:------------------|-------:|---------------:|----------------:|------------:|-------------:|---------------:|-------------:|
| controversial    | cringeanarchy        | toxicity_toxigen | detoxify_toxicity |   2091 |       0.336373 |        0.294254 |    0.735386 | 0            |       0.774983 |            0 |
| controversial    | fatpeoplehate        | toxicity_toxigen | detoxify_toxicity | 277140 |       0.287322 |        0.26097  |    0.702643 | 0            |       0.753543 |            0 |
| controversial    | greatawakening       | toxicity_toxigen | detoxify_toxicity | 221673 |       0.192006 |        0.148749 |    0.676507 | 0            |       0.689628 |            0 |
| controversial    | kotakuinaction       | toxicity_toxigen | detoxify_toxicity |   4857 |       0.208045 |        0.198696 |    0.660121 | 0            |       0.730465 |            0 |
| controversial    | mensrights           | toxicity_toxigen | detoxify_toxicity |   2010 |       0.301723 |        0.272507 |    0.616778 | 5.35992e-211 |       0.748439 |            0 |
| controversial    | milliondollarextreme | toxicity_toxigen | detoxify_toxicity |  13838 |       0.274637 |        0.246713 |    0.749619 | 0            |       0.754265 |            0 |
| normal           | funny                | toxicity_toxigen | detoxify_toxicity |  97169 |       0.266822 |        0.243278 |    0.752446 | 0            |       0.752175 |            0 |
| normal           | gaming               | toxicity_toxigen | detoxify_toxicity |  40824 |       0.136666 |        0.155366 |    0.731384 | 0            |       0.676538 |            0 |
| normal           | gifs                 | toxicity_toxigen | detoxify_toxicity |  13555 |       0.188527 |        0.18804  |    0.770051 | 0            |       0.705123 |            0 |
| normal           | pics                 | toxicity_toxigen | detoxify_toxicity |  23690 |       0.206777 |        0.192264 |    0.757258 | 0            |       0.732407 |            0 |
| normal           | technology           | toxicity_toxigen | detoxify_toxicity |  48500 |       0.17299  |        0.160709 |    0.707357 | 0            |       0.677685 |            0 |
| normal           | videos               | toxicity_toxigen | detoxify_toxicity |  40399 |       0.264533 |        0.239888 |    0.748953 | 0            |       0.765674 |            0 |
