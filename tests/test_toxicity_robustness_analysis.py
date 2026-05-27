import unittest

import pandas as pd

from scripts.toxicity_robustness_analysis import (
    ar1_effective_n,
    dynamic_monthly_user_type,
    epoch_to_datetime,
    event_week_index,
    lag1_autocorrelation,
    monday_week_start,
    monthly_paired_interval_summary,
    moving_block_bootstrap_mean_ci,
    newey_west_mean_ci,
    weekly_activity_spike_summary,
    weekly_activity_window_summary,
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

    def test_autocorrelation_interval_helpers_are_deterministic(self):
        series = pd.Series([1.0, 2.0, 3.0, 4.0])

        self.assertAlmostEqual(lag1_autocorrelation(series), 1.0)
        self.assertEqual(ar1_effective_n(10, 0.0), 10.0)

        low, high = moving_block_bootstrap_mean_ci(
            pd.Series([0.5, 0.5, 0.5]),
            block_length=2,
            iterations=100,
            seed=1,
        )
        self.assertAlmostEqual(low, 0.5)
        self.assertAlmostEqual(high, 0.5)

        hac_se, hac_low, hac_high = newey_west_mean_ci(series, max_lag=1)
        self.assertGreaterEqual(hac_se, 0.0)
        self.assertLess(hac_low, series.mean())
        self.assertGreater(hac_high, series.mean())

    def test_monthly_paired_interval_summary_includes_expected_comparisons(self):
        monthly = pd.DataFrame(
            {
                "period_type": ["month"] * 8,
                "community": ["global"] * 8,
                "month": ["2020-01", "2020-01", "2020-02", "2020-02"] * 2,
                "cohort": ["existing", "newcomer", "existing", "newcomer"] * 2,
                "active_user_periods": [1] * 8,
                "activity_count": [1] * 8,
                "mean_toxigen_probability_equal_user": [
                    0.1,
                    0.2,
                    0.2,
                    0.3,
                    0.1,
                    0.2,
                    0.2,
                    0.3,
                ],
                "mean_toxigen_probability_activity_weighted": [
                    0.2,
                    0.4,
                    0.4,
                    0.6,
                    0.2,
                    0.4,
                    0.4,
                    0.6,
                ],
            }
        ).drop_duplicates(subset=["community", "month", "cohort"])

        out = monthly_paired_interval_summary(
            monthly,
            block_length=2,
            bootstrap_iterations=100,
            hac_lags=1,
            seed=1,
        )

        self.assertIn("mbb_mean_ci_low", out.columns)
        self.assertIn("hac_mean_ci_high", out.columns)
        self.assertIn("activity_weighted_minus_equal_user", set(out["comparison"]))
        self.assertIn("newcomer_minus_existing", set(out["comparison"]))

    def test_weekly_activity_spike_summary_reports_prepost_ratios(self):
        weekly_users = pd.DataFrame(
            {
                "community": ["funny"] * 6,
                "event_key": ["fph"] * 6,
                "event_label": ["FPH"] * 6,
                "event_date": ["2015-06-10"] * 6,
                "week_start": pd.to_datetime(
                    [
                        "2015-05-25",
                        "2015-06-01",
                        "2015-06-08",
                        "2015-06-15",
                        "2015-05-25",
                        "2015-06-08",
                    ]
                ),
                "week_index": [-2, -1, 0, 1, -2, 0],
                "user_id": ["u1", "u1", "u1", "u1", "u2", "u2"],
                "user_type": [
                    "existing",
                    "existing",
                    "existing",
                    "existing",
                    "newcomer",
                    "newcomer",
                ],
                "activity_count": [2, 4, 10, 6, 2, 8],
            }
        )

        weekly = weekly_activity_window_summary(weekly_users)
        out = weekly_activity_spike_summary(weekly)
        row = out[(out["community"] == "global") & (out["cohort"] == "all")].iloc[0]

        self.assertEqual(row["pre_weeks_observed"], 2)
        self.assertEqual(row["post_weeks_observed"], 2)
        self.assertAlmostEqual(row["pre_mean_weekly_activity_count"], 4.0)
        self.assertAlmostEqual(row["event_week_activity_count"], 18.0)
        self.assertAlmostEqual(row["post_mean_weekly_activity_count"], 12.0)
        self.assertAlmostEqual(row["post_pre_activity_ratio"], 3.0)
        self.assertAlmostEqual(row["event_pre_activity_ratio"], 4.5)
        self.assertEqual(row["max_post_week_index"], 0)


if __name__ == "__main__":
    unittest.main()
