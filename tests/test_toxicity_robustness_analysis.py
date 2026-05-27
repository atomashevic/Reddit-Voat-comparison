import unittest

import pandas as pd

from scripts.toxicity_robustness_analysis import (
    dynamic_monthly_user_type,
    epoch_to_datetime,
    event_week_index,
    monday_week_start,
    summarize_with_all_user_type,
    weighted_mean,
)


class ToxicityRobustnessAnalysisTests(unittest.TestCase):
    def test_epoch_to_datetime_accepts_seconds_and_milliseconds(self):
        out = epoch_to_datetime(pd.Series([1_430_000_000, 1_430_000_000_000]))
        self.assertEqual(out.iloc[0], out.iloc[1])
        self.assertEqual(out.iloc[0].year, 2015)

    def test_dynamic_monthly_user_type_uses_exact_event_boundary(self):
        self.assertEqual(
            dynamic_monthly_user_type(
                pd.Timestamp("2015-06-09 23:59:59"), pd.Period("2015-06", "M")
            ),
            "existing",
        )
        self.assertEqual(
            dynamic_monthly_user_type(
                pd.Timestamp("2015-06-10 00:00:00"), pd.Period("2015-06", "M")
            ),
            "newcomer",
        )
        self.assertEqual(
            dynamic_monthly_user_type(
                pd.Timestamp("2016-11-22 23:59:59"), pd.Period("2016-11", "M")
            ),
            "existing",
        )
        self.assertEqual(
            dynamic_monthly_user_type(
                pd.Timestamp("2016-11-23 00:00:00"), pd.Period("2016-11", "M")
            ),
            "newcomer",
        )

    def test_event_week_index_uses_monday_event_week(self):
        timestamps = pd.Series(pd.to_datetime(["2018-09-03", "2018-09-10", "2018-09-17"]))
        starts = monday_week_start(timestamps)
        out = event_week_index(starts, pd.Timestamp("2018-09-12"))
        self.assertEqual(list(out), [-1, 0, 1])

    def test_weighted_mean_and_all_user_summary(self):
        df = pd.DataFrame(
            {
                "community": ["funny", "funny"],
                "month": ["2018-09", "2018-09"],
                "user_id": ["u1", "u2"],
                "user_type": ["existing", "newcomer"],
                "mean_toxicity": [0.2, 0.8],
                "activity_count": [1, 3],
            }
        )
        self.assertAlmostEqual(weighted_mean(df["mean_toxicity"], df["activity_count"]), 0.65)

        out = summarize_with_all_user_type(df, ["community", "month"])
        all_row = out[out["user_type"] == "all"].iloc[0]
        self.assertEqual(all_row["active_user_periods"], 2)
        self.assertAlmostEqual(all_row["mean_toxigen_probability_equal_user"], 0.5)
        self.assertAlmostEqual(all_row["mean_toxigen_probability_activity_weighted"], 0.65)


if __name__ == "__main__":
    unittest.main()
