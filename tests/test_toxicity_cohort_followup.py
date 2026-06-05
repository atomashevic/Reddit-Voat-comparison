import unittest
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.toxicity_cohort_followup import (
    assign_cohorts_from_first_seen,
    calculate_sliding_timeseries,
    cohort_from_first_seen,
    summarize_adplus_period,
)


class ToxicityCohortFollowupTests(unittest.TestCase):
    def test_cohort_from_first_seen_uses_chronological_boundaries(self):
        self.assertEqual(cohort_from_first_seen(pd.Timestamp("2015-06-09")), "beforeA")
        self.assertEqual(cohort_from_first_seen(pd.Timestamp("2015-06-10")), "betweenA-B")
        self.assertEqual(cohort_from_first_seen(pd.Timestamp("2016-11-23")), "betweenB-C")
        self.assertEqual(cohort_from_first_seen(pd.Timestamp("2018-09-12")), "betweenC-D")
        self.assertEqual(cohort_from_first_seen(pd.Timestamp("2020-06-29")), "afterD")

    def test_assign_cohorts_recomputes_from_pooled_first_seen(self):
        data = pd.DataFrame(
            {
                "user_id": ["u1", "u1", "u2"],
                "dt_time": pd.to_datetime(["2015-06-09", "2020-07-01", "2020-07-01"]),
            }
        )
        out = assign_cohorts_from_first_seen(data)

        self.assertEqual(list(out[out["user_id"] == "u1"]["cohort"]), ["beforeA", "beforeA"])
        self.assertEqual(out[out["user_id"] == "u2"]["cohort"].iloc[0], "afterD")

    def test_sliding_timeseries_keeps_user_and_activity_means_only(self):
        data = pd.DataFrame(
            {
                "user_id": ["u1", "u1", "u2", "u3"],
                "dt_time": pd.to_datetime(
                    ["2015-06-10", "2015-06-11", "2015-06-10", "2015-06-15"]
                ),
                "cohort": ["betweenA-B", "betweenA-B", "betweenA-B", "beforeA"],
                "toxicity_toxigen": [0.0, 1.0, 1.0, 0.2],
            }
        )
        out = calculate_sliding_timeseries(data, "funny", window_days=2)
        row = out[
            (out["window_tmin"] == "2015-06-10") & (out["cohort"] == "betweenA-B")
        ].iloc[0]

        self.assertEqual(row["active_users"], 2)
        self.assertEqual(row["activity_count"], 3)
        self.assertAlmostEqual(row["mean_toxigen_probability_user"], 0.75)
        self.assertAlmostEqual(row["mean_toxigen_probability_activity"], 2 / 3)
        self.assertAlmostEqual(row["mean_toxigen_probability_user_se"], 0.25)
        self.assertAlmostEqual(row["mean_toxigen_probability_activity_se"], 1 / 6)
        self.assertNotIn("toxicity_sum", out.columns)

    def test_adplus_summary_uses_a_through_end_period(self):
        data = pd.DataFrame(
            {
                "user_id": ["old", "old", "new"],
                "dt_time": pd.to_datetime(["2015-06-09", "2015-06-10", "2020-07-01"]),
                "cohort": ["beforeA", "beforeA", "afterD"],
                "toxicity_toxigen": [1.0, 0.2, 0.8],
            }
        )
        out = summarize_adplus_period(data, "funny")
        before = out[out["cohort"] == "beforeA"].iloc[0]
        after = out[out["cohort"] == "afterD"].iloc[0]

        self.assertEqual(before["activity_count"], 1)
        self.assertAlmostEqual(before["mean_toxigen_probability_activity"], 0.2)
        self.assertEqual(after["activity_count"], 1)
        self.assertEqual(before["period"], "A-D+")


if __name__ == "__main__":
    unittest.main()
