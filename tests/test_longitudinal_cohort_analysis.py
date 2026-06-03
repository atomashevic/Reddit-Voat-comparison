import unittest

import pandas as pd

from scripts.longitudinal_cohort_analysis import (
    assign_fixed_cohort,
    attach_hub_ascent,
    compute_monthly_network_rows,
    month_distance,
    rank_top_decile_hubs,
    summarize_user_months,
)


class LongitudinalCohortAnalysisTests(unittest.TestCase):
    def test_assign_fixed_cohort_uses_chronological_boundaries(self):
        cases = {
            "2015-06-09 23:59:59": "pre_fph",
            "2015-06-10 00:00:00": "fph_pg",
            "2016-11-22 23:59:59": "fph_pg",
            "2016-11-23 00:00:00": "pg_ga",
            "2018-09-12 00:00:00": "ga_td",
            "2020-06-29 00:00:00": "td_shutdown",
        }
        for timestamp, expected in cases.items():
            self.assertEqual(assign_fixed_cohort(pd.Timestamp(timestamp)), expected)

    def test_rank_top_decile_hubs_is_deterministic(self):
        degrees = pd.Series(
            {
                "u1": 1,
                "u2": 2,
                "u3": 3,
                "u4": 4,
                "u5": 5,
                "u6": 6,
                "u7": 7,
                "u8": 8,
                "u9": 9,
                "u10": 10,
                "u11": 10,
            }
        )
        self.assertEqual(rank_top_decile_hubs(degrees), {"u10", "u11"})

    def test_month_distance(self):
        self.assertEqual(month_distance(pd.Period("2015-06", "M"), pd.Period("2016-01", "M")), 7)

    def test_summarize_user_months_retention_and_groups(self):
        metrics = pd.DataFrame(
            {
                "community": ["funny"] * 5,
                "user_id": ["a", "a", "a", "b", "b"],
                "month": ["2015-06", "2015-07", "2015-09", "2015-06", "2015-07"],
                "mean_toxicity": [0.1, 0.2, 0.3, 0.8, 0.7],
                "mean_reputation": [1.0, 2.0, 3.0, 1.0, 1.5],
                "activity_count": [1, 5, 1, 10, 1],
            }
        )
        metrics["month_period"] = pd.PeriodIndex(metrics["month"], freq="M")
        first_seen = pd.DataFrame(
            {
                "user_id": ["a", "b"],
                "first_seen_dt": [pd.Timestamp("2015-06-10"), pd.Timestamp("2015-06-11")],
                "first_month": ["2015-06", "2015-06"],
                "fixed_cohort": ["fph_pg", "fph_pg"],
            }
        )
        users, behavior = summarize_user_months("funny", metrics, first_seen)
        users = users.set_index("user_id")

        self.assertEqual(users.loc["a", "survival_months"], 4)
        self.assertTrue(bool(users.loc["a", "retained_3m"]))
        self.assertFalse(bool(users.loc["b", "retained_3m"]))
        self.assertEqual(users.loc["b", "activity_group"], "high_activity")
        self.assertEqual(users.loc["b", "toxicity_group"], "high_toxicity")
        self.assertIn("mean_toxicity_activity_weighted", behavior.columns)

    def test_attach_hub_ascent(self):
        users = pd.DataFrame(
            {
                "user_id": ["a", "b"],
                "first_active_month": [pd.Period("2015-06", "M"), pd.Period("2015-06", "M")],
            }
        )
        network = pd.DataFrame(
            {
                "user_id": ["a", "a", "b"],
                "month": ["2015-06", "2015-08", "2015-06"],
                "is_hub": [False, True, False],
            }
        )
        out = attach_hub_ascent(users, network).set_index("user_id")
        self.assertTrue(bool(out.loc["a", "ever_hub"]))
        self.assertEqual(out.loc["a", "months_to_first_hub"], 2)
        self.assertFalse(bool(out.loc["b", "ever_hub"]))


if __name__ == "__main__":
    unittest.main()
