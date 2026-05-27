import unittest

import numpy as np
import pandas as pd

from scripts.regime_break_analysis import (
    break_index_for_month,
    fit_segmented_model,
    find_best_segmented_model,
)


class RegimeBreakAnalysisTests(unittest.TestCase):
    def test_bic_prefers_no_break_for_linear_series(self):
        rng = np.random.default_rng(1)
        x = np.arange(60, dtype=float)
        y = 1 + 0.2 * x + rng.normal(0, 0.5, len(x))

        no_break = find_best_segmented_model(x, y, 0, min_seg=6)
        one_break = find_best_segmented_model(x, y, 1, min_seg=6)
        two_break = find_best_segmented_model(x, y, 2, min_seg=6)

        self.assertIsNotNone(no_break)
        self.assertIsNotNone(one_break)
        self.assertIsNotNone(two_break)
        self.assertLess(no_break.bic, one_break.bic)
        self.assertLess(no_break.bic, two_break.bic)

    def test_one_break_recovery(self):
        rng = np.random.default_rng(2)
        x = np.arange(70, dtype=float)
        y = np.where(x < 30, 2 + 0.05 * x, -8 + 0.5 * x)
        y = y + rng.normal(0, 0.1, len(x))

        fit = find_best_segmented_model(x, y, 1, min_seg=6)

        self.assertIsNotNone(fit)
        self.assertEqual(fit.break_indices, (30,))

    def test_two_break_recovery(self):
        rng = np.random.default_rng(3)
        x = np.arange(80, dtype=float)
        y = np.piecewise(
            x,
            [x < 22, (x >= 22) & (x < 52), x >= 52],
            [lambda z: 1 + 0.1 * z, lambda z: 7 - 0.2 * z, lambda z: -25 + 0.4 * z],
        )
        y = y + rng.normal(0, 0.08, len(x))

        fit = find_best_segmented_model(x, y, 2, min_seg=6)

        self.assertIsNotNone(fit)
        self.assertEqual(fit.break_indices, (22, 52))

    def test_fixed_break_respects_minimum_segment_length(self):
        x = np.arange(20, dtype=float)
        y = 1 + x

        invalid = fit_segmented_model(x, y, (4,), min_seg=6)
        valid = fit_segmented_model(x, y, (10,), min_seg=6)

        self.assertIsNone(invalid)
        self.assertIsNotNone(valid)

    def test_break_index_for_month_uses_first_month_at_or_after_split(self):
        months = pd.to_datetime(["2018-07-01", "2018-08-01", "2018-10-01"])

        self.assertEqual(break_index_for_month(months, pd.Timestamp("2018-08-12")), 1)
        self.assertEqual(break_index_for_month(months, pd.Timestamp("2018-09-01")), 2)


if __name__ == "__main__":
    unittest.main()
