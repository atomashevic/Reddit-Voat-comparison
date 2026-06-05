# Detoxify vs ToxiGen Voat post sample

- sample_rows: 1000
- sample_seed: 20260602
- detoxify_model: unbiased
- requested_device: cuda
- model_device: cuda:0
- torch_version: 2.7.1+cu126
- cuda_available: True
- cuda_device: NVIDIA A30

## Global toxicity correlation

- n=1000; Pearson r=0.7284; Spearman rho=0.6436
- mean ToxiGen toxicity=0.1318
- mean Detoxify toxicity=0.1202

## Community sample counts

| platform   | community            | community_type   |   eligible_posts |   sample_requested_n |   sample_actual_n |
|:-----------|:---------------------|:-----------------|-----------------:|---------------------:|------------------:|
| voat       | cringeanarchy        | controversial    |              939 |                   84 |                84 |
| voat       | fatpeoplehate        | controversial    |            74806 |                   84 |                84 |
| voat       | greatawakening       | controversial    |           103156 |                   84 |                84 |
| voat       | mensrights           | controversial    |             1725 |                   84 |                84 |
| voat       | milliondollarextreme | controversial    |             7351 |                   83 |                83 |
| voat       | kotakuinaction       | controversial    |             2996 |                   83 |                83 |
| voat       | funny                | normal           |            46762 |                   83 |                83 |
| voat       | gaming               | normal           |            28646 |                   83 |                83 |
| voat       | gifs                 | normal           |             8015 |                   83 |                83 |
| voat       | pics                 | normal           |            14862 |                   83 |                83 |
| voat       | technology           | normal           |            34678 |                   83 |                83 |
| voat       | videos               | normal           |            44791 |                   83 |                83 |

## Per-community Detoxify toxicity correlations

| community_type   | community            | toxigen_col      | detoxify_col      |   n |   toxigen_mean |   detoxify_mean |   pearson_r |   pearson_p |   spearman_rho |   spearman_p |
|:-----------------|:---------------------|:-----------------|:------------------|----:|---------------:|----------------:|------------:|------------:|---------------:|-------------:|
| controversial    | cringeanarchy        | toxicity_toxigen | detoxify_toxicity |  84 |      0.319166  |       0.313149  |    0.746846 | 3.44891e-16 |       0.770072 |  1.11327e-17 |
| controversial    | fatpeoplehate        | toxicity_toxigen | detoxify_toxicity |  84 |      0.305268  |       0.227885  |    0.777383 | 3.47293e-18 |       0.707612 |  5.26252e-14 |
| controversial    | greatawakening       | toxicity_toxigen | detoxify_toxicity |  84 |      0.0682651 |       0.0560172 |    0.556984 | 3.74877e-08 |       0.644545 |  3.69419e-11 |
| controversial    | kotakuinaction       | toxicity_toxigen | detoxify_toxicity |  83 |      0.0890071 |       0.0935362 |    0.500768 | 1.42633e-06 |       0.647888 |  3.58143e-11 |
| controversial    | mensrights           | toxicity_toxigen | detoxify_toxicity |  84 |      0.167129  |       0.157885  |    0.570992 | 1.41637e-08 |       0.452257 |  1.56865e-05 |
| controversial    | milliondollarextreme | toxicity_toxigen | detoxify_toxicity |  83 |      0.195177  |       0.17224   |    0.832257 | 1.87438e-22 |       0.674455 |  2.74759e-12 |
| normal           | funny                | toxicity_toxigen | detoxify_toxicity |  83 |      0.124412  |       0.128067  |    0.750986 | 2.92942e-16 |       0.642165 |  6.02679e-11 |
| normal           | gaming               | toxicity_toxigen | detoxify_toxicity |  83 |      0.0671832 |       0.0742592 |    0.645782 | 4.34294e-11 |       0.582952 |  7.3631e-09  |
| normal           | gifs                 | toxicity_toxigen | detoxify_toxicity |  83 |      0.105733  |       0.0881883 |    0.771723 | 1.35891e-17 |       0.526299 |  3.21899e-07 |
| normal           | pics                 | toxicity_toxigen | detoxify_toxicity |  83 |      0.0408528 |       0.029528  |    0.272256 | 0.0127749   |       0.310992 |  0.00421474  |
| normal           | technology           | toxicity_toxigen | detoxify_toxicity |  83 |      0.0236445 |       0.028283  |    0.724637 | 9.63991e-15 |       0.414225 |  9.90415e-05 |
| normal           | videos               | toxicity_toxigen | detoxify_toxicity |  83 |      0.0714352 |       0.069681  |    0.597968 | 2.38659e-09 |       0.656073 |  1.66847e-11 |
