import pandas as pd

from scripts.build_detoxify_lab_report import global_summary_tables


def test_global_summary_tables_reads_correlations_from_supplied_results_dir(tmp_path):
    corr_path = tmp_path / "voat_detoxify_unbiased_all_posts_correlations_global.csv"
    pd.DataFrame(
        [
            {
                "detoxify_col": "detoxify_toxicity",
                "pearson_r": 0.12,
                "spearman_rho": 0.34,
            }
        ]
    ).to_csv(corr_path, index=False)
    analyses = {
        "post": {
            "dist": pd.DataFrame(
                [
                    {
                        "scope": "global",
                        "label": label,
                        "n_rows": 10,
                        "mean": 0.1,
                        "share_gt_0_5": 0.2,
                    }
                    for label in [
                        "toxigen_toxicity",
                        "detoxify_toxicity",
                        "detoxify_severe",
                        "detoxify_identity",
                        "detoxify_insult",
                        "detoxify_threat",
                    ]
                ]
            )
        }
    }

    _, corr = global_summary_tables(analyses, tmp_path)

    assert corr.iloc[0]["Pearson r"] == "0.1200"
    assert corr.iloc[0]["Spearman rho"] == "0.3400"
