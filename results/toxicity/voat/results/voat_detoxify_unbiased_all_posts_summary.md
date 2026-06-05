# Detoxify vs ToxiGen Voat all-post run

- scored_rows: 368727
- detoxify_model: unbiased
- requested_device: cuda
- model_device: cuda:0
- torch_version: 2.7.1+cu126
- cuda_available: True
- cuda_device: NVIDIA A30

## Global toxicity correlation

- n=368727; Pearson r=0.6935; Spearman rho=0.6528
- mean ToxiGen toxicity=0.1311
- mean Detoxify toxicity=0.1125

## Community counts

| platform   | community            | community_type   |   eligible_posts |   scored_posts | score_file                                                       |
|:-----------|:---------------------|:-----------------|-----------------:|---------------:|:-----------------------------------------------------------------|
| voat       | cringeanarchy        | controversial    |              939 |            939 | voat_detoxify_unbiased_all_posts_cringeanarchy_scores.csv        |
| voat       | fatpeoplehate        | controversial    |            74806 |          74806 | voat_detoxify_unbiased_all_posts_fatpeoplehate_scores.csv        |
| voat       | greatawakening       | controversial    |           103156 |         103156 | voat_detoxify_unbiased_all_posts_greatawakening_scores.csv       |
| voat       | mensrights           | controversial    |             1725 |           1725 | voat_detoxify_unbiased_all_posts_mensrights_scores.csv           |
| voat       | milliondollarextreme | controversial    |             7351 |           7351 | voat_detoxify_unbiased_all_posts_milliondollarextreme_scores.csv |
| voat       | kotakuinaction       | controversial    |             2996 |           2996 | voat_detoxify_unbiased_all_posts_kotakuinaction_scores.csv       |
| voat       | funny                | normal           |            46762 |          46762 | voat_detoxify_unbiased_all_posts_funny_scores.csv                |
| voat       | gaming               | normal           |            28646 |          28646 | voat_detoxify_unbiased_all_posts_gaming_scores.csv               |
| voat       | gifs                 | normal           |             8015 |           8015 | voat_detoxify_unbiased_all_posts_gifs_scores.csv                 |
| voat       | pics                 | normal           |            14862 |          14862 | voat_detoxify_unbiased_all_posts_pics_scores.csv                 |
| voat       | technology           | normal           |            34678 |          34678 | voat_detoxify_unbiased_all_posts_technology_scores.csv           |
| voat       | videos               | normal           |            44791 |          44791 | voat_detoxify_unbiased_all_posts_videos_scores.csv               |

## Per-community Detoxify toxicity correlations

| community_type   | community            | toxigen_col      | detoxify_col      |      n |   toxigen_mean |   detoxify_mean |   pearson_r |    pearson_p |   spearman_rho |   spearman_p |
|:-----------------|:---------------------|:-----------------|:------------------|-------:|---------------:|----------------:|------------:|-------------:|---------------:|-------------:|
| controversial    | cringeanarchy        | toxicity_toxigen | detoxify_toxicity |    939 |      0.232403  |       0.211567  |    0.75595  | 1.33267e-174 |       0.72688  | 4.39576e-155 |
| controversial    | fatpeoplehate        | toxicity_toxigen | detoxify_toxicity |  74806 |      0.308141  |       0.26063   |    0.698775 | 0            |       0.756159 | 0            |
| controversial    | greatawakening       | toxicity_toxigen | detoxify_toxicity | 103156 |      0.101112  |       0.0810809 |    0.536656 | 0            |       0.604225 | 0            |
| controversial    | kotakuinaction       | toxicity_toxigen | detoxify_toxicity |   2996 |      0.0835737 |       0.0819691 |    0.549228 | 9.9944e-236  |       0.602527 | 1.38207e-295 |
| controversial    | mensrights           | toxicity_toxigen | detoxify_toxicity |   1725 |      0.12643   |       0.119085  |    0.569177 | 1.11573e-148 |       0.539971 | 3.82252e-131 |
| controversial    | milliondollarextreme | toxicity_toxigen | detoxify_toxicity |   7351 |      0.18829   |       0.164708  |    0.71586  | 0            |       0.684164 | 0            |
| normal           | funny                | toxicity_toxigen | detoxify_toxicity |  46762 |      0.107525  |       0.0916625 |    0.71073  | 0            |       0.536245 | 0            |
| normal           | gaming               | toxicity_toxigen | detoxify_toxicity |  28646 |      0.0393921 |       0.0468999 |    0.710649 | 0            |       0.554147 | 0            |
| normal           | gifs                 | toxicity_toxigen | detoxify_toxicity |   8015 |      0.0709478 |       0.0643948 |    0.720633 | 0            |       0.458218 | 0            |
| normal           | pics                 | toxicity_toxigen | detoxify_toxicity |  14862 |      0.0555673 |       0.0488833 |    0.709831 | 0            |       0.476539 | 0            |
| normal           | technology           | toxicity_toxigen | detoxify_toxicity |  34678 |      0.029395  |       0.0276596 |    0.583037 | 0            |       0.451193 | 0            |
| normal           | videos               | toxicity_toxigen | detoxify_toxicity |  44791 |      0.093776  |       0.0874666 |    0.671955 | 0            |       0.597412 | 0            |
