import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.summarize_detoxify_toxigen_correlations import summarize_sources


class SummarizeDetoxifyToxigenCorrelationsTests(unittest.TestCase):
    def write_source(self, path: Path, group_col: str, rows: list[dict[str, object]]) -> None:
        pd.DataFrame(
            [
                {
                    group_col: row["group"],
                    "toxigen_col": "toxicity_toxigen",
                    "detoxify_col": row.get("detoxify_col", "detoxify_toxicity"),
                    "n": row["n"],
                    "toxigen_mean": row["toxigen_mean"],
                    "detoxify_mean": row["detoxify_mean"],
                    "pearson_r": row["pearson_r"],
                    "pearson_p": 0.0,
                    "spearman_rho": row["spearman_rho"],
                    "spearman_p": 0.0,
                }
                for row in rows
            ]
        ).to_csv(path, index=False)

    def test_summarize_sources_extracts_detoxify_toxicity_with_provenance(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_source(
                root / "voat_detoxify_unbiased_all_posts_correlations_global.csv",
                "scope",
                [
                    {
                        "group": "global",
                        "n": 100,
                        "toxigen_mean": 0.1,
                        "detoxify_mean": 0.11,
                        "pearson_r": 0.7,
                        "spearman_rho": 0.6,
                    }
                ],
            )
            self.write_source(
                root / "voat_detoxify_unbiased_all_comments_correlations_global.csv",
                "scope",
                [
                    {
                        "group": "global",
                        "n": 200,
                        "toxigen_mean": 0.2,
                        "detoxify_mean": 0.21,
                        "pearson_r": 0.8,
                        "spearman_rho": 0.7,
                    }
                ],
            )
            self.write_source(
                root / "voat_detoxify_unbiased_1k_post_sample_correlations_global.csv",
                "scope",
                [
                    {
                        "group": "global",
                        "n": 50,
                        "toxigen_mean": 0.3,
                        "detoxify_mean": 0.31,
                        "pearson_r": 0.9,
                        "spearman_rho": 0.8,
                    }
                ],
            )
            for interaction in ["posts", "comments"]:
                self.write_source(
                    root
                    / f"voat_detoxify_unbiased_all_{interaction}_correlations_by_type.csv",
                    "community_type",
                    [
                        {
                            "group": "controversial",
                            "n": 30,
                            "toxigen_mean": 0.4,
                            "detoxify_mean": 0.41,
                            "pearson_r": 0.65,
                            "spearman_rho": 0.66,
                        },
                        {
                            "group": "normal",
                            "n": 40,
                            "toxigen_mean": 0.5,
                            "detoxify_mean": 0.51,
                            "pearson_r": 0.75,
                            "spearman_rho": 0.76,
                        },
                    ],
                )

            out = summarize_sources(root)

        self.assertEqual(len(out), 7)
        self.assertIn("source_file", out.columns)
        posts = out[
            (out["scope"] == "global")
            & (out["stratum"] == "all")
            & (out["interaction_scope"] == "all_posts")
        ].iloc[0]
        self.assertEqual(posts["n"], 100)
        self.assertAlmostEqual(posts["pearson_correlation"], 0.7)
        self.assertEqual(
            posts["source_file"],
            "voat_detoxify_unbiased_all_posts_correlations_global.csv",
        )


if __name__ == "__main__":
    unittest.main()
