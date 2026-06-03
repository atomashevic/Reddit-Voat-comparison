import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from migration_utils import EVENTS_CHRONO
from toxicity_weekly_event_window import (
    attach_global_first_seen,
    compute_weekly_windows,
    normalize_publish_dates,
)


def test_normalize_publish_dates_accepts_epoch_milliseconds():
    event_date = EVENTS_CHRONO["A"]
    millis = int(event_date.timestamp() * 1000)

    parsed = normalize_publish_dates(pd.Series([millis]))

    assert parsed.iloc[0] == event_date


def test_first_seen_uses_unscored_earlier_activity_before_toxicity_filter():
    event_date = EVENTS_CHRONO["A"]
    data = pd.DataFrame(
        {
            "user_id": ["u1", "u1"],
            "community": ["funny", "funny"],
            "published_at": [event_date - pd.Timedelta(days=1), event_date + pd.Timedelta(days=1)],
            "toxicity_toxigen": [pd.NA, 0.8],
        }
    )

    weekly = compute_weekly_windows(attach_global_first_seen(data))
    focal = weekly[
        (weekly["community"] == "funny")
        & (weekly["event"] == "A")
        & (weekly["relative_week"] == 0)
    ]

    assert set(focal["cohort_group"]) == {"existing"}


def test_first_seen_is_global_across_communities():
    event_date = EVENTS_CHRONO["A"]
    data = pd.DataFrame(
        {
            "user_id": ["u1", "u1"],
            "community": ["funny", "gaming"],
            "published_at": [event_date - pd.Timedelta(days=1), event_date + pd.Timedelta(days=1)],
            "toxicity_toxigen": [0.2, 0.8],
        }
    )

    weekly = compute_weekly_windows(attach_global_first_seen(data))
    gaming = weekly[
        (weekly["community"] == "gaming")
        & (weekly["event"] == "A")
        & (weekly["relative_week"] == 0)
    ]
    global_post = weekly[
        (weekly["community"] == "global")
        & (weekly["event"] == "A")
        & (weekly["relative_week"] == 0)
    ]

    assert set(gaming["cohort_group"]) == {"existing"}
    assert set(global_post["cohort_group"]) == {"existing"}
