import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fixed_cohort_retention_analysis import (
    build_manuscript_table,
    normalize_publish_dates,
    read_degrees,
    read_first_seen,
    summarize_hubs,
)


def test_normalize_publish_dates_accepts_epoch_milliseconds():
    millis = int(pd.Timestamp("2015-06-10").timestamp() * 1000)

    parsed = normalize_publish_dates(pd.Series([millis]))

    assert parsed.iloc[0] == pd.Timestamp("2015-06-10")


def test_read_first_seen_uses_millisecond_publish_dates(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    millis = int(pd.Timestamp("2015-06-11").timestamp() * 1000)
    pd.DataFrame({"user_id": ["u1"], "publish_date": [millis]}).to_parquet(
        data_dir / "voat_funny_madoc.parquet"
    )

    first_seen = read_first_seen(data_dir, "funny")

    assert first_seen.loc[0, "first_seen_dt"] == pd.Timestamp("2015-06-11")
    assert first_seen.loc[0, "fixed_cohort"] == "fph_pg"


def test_read_degrees_skips_empty_edge_file(tmp_path):
    edge_file = tmp_path / "funny_2015-06.txt"
    edge_file.write_text("")

    degrees = read_degrees(edge_file)

    assert degrees.empty


def test_build_manuscript_table_combines_primary_and_hub_summaries():
    primary = pd.DataFrame(
        {
            "fixed_cohort": ["fph_pg"],
            "n_users": [10],
            "n_high_toxicity": [3],
            "km_survival_3m_high_minus_lower": [0.2],
            "km_survival_12m_high_minus_lower": [0.1],
        }
    )
    hubs = pd.DataFrame(
        {
            "fixed_cohort": ["fph_pg"],
            "hub_fraction": [0.10],
            "median_degree_share_ratio": [0.9],
            "mean_ever_hub_rate": [0.08],
            "high_activity_ever_hub_rate": [0.3],
        }
    )

    table = build_manuscript_table(primary, hubs)

    assert table.to_dict("records") == [
        {
            "cohort": "fph_pg",
            "n_users": 10,
            "n_high_early_toxicity": 3,
            "km_3m_high_minus_lower": 0.2,
            "km_12m_high_minus_lower": 0.1,
            "median_degree_share_ratio": 0.9,
            "mean_ever_hub_rate_top10": 0.08,
            "hub_rate_equality_baseline_top10": 0.1,
            "high_activity_ever_hub_rate_top10": 0.3,
        }
    ]


def test_summarize_hubs_counts_user_community_rows():
    users = pd.DataFrame(
        {
            "community": ["funny", "gaming"],
            "user_id": ["u1", "u1"],
            "fixed_cohort": ["fph_pg", "fph_pg"],
            "activity_group": ["lower_activity", "high_activity"],
            "ever_hub_top5": [False, True],
            "ever_hub_top10": [False, True],
            "ever_hub_top20": [False, True],
        }
    )
    monthly = pd.DataFrame(
        {
            "fixed_cohort": ["fph_pg"],
            "degree_share_ratio": [0.9],
        }
    )

    hubs = summarize_hubs(users, monthly)
    top10 = hubs[hubs["hub_fraction"] == 0.10].iloc[0]

    assert top10["n_users"] == 2
    assert top10["mean_ever_hub_rate"] == 0.5
