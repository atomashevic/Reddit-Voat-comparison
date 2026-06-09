import pandas as pd

from scripts.analyze_detoxify_toxicity_results import event_period_means


def test_event_period_means_uses_exact_publish_timestamp():
    scores = pd.DataFrame(
        {
            "community_type": ["normal", "normal"],
            "community": ["funny", "funny"],
            "user_id": ["u1", "u2"],
            "dt_time": pd.to_datetime(["2015-06-09", "2015-06-10"]),
            "month": ["2015-06", "2015-06"],
            "month_dt": pd.to_datetime(["2015-06-01", "2015-06-01"]),
            "toxicity_toxigen": [0.1, 0.2],
            "detoxify_toxicity": [0.2, 0.4],
            "detoxify_severe_toxicity": [0.01, 0.02],
            "detoxify_identity_attack": [0.03, 0.04],
            "detoxify_insult": [0.05, 0.06],
            "detoxify_threat": [0.07, 0.08],
        }
    )

    out = event_period_means(scores)

    assert out["activity_count"].sum() == 1
    assert out.iloc[0]["period"] == "A-B"
    assert out.iloc[0]["active_users"] == 1
    assert out.iloc[0]["detoxify_toxicity_mean"] == 0.4
