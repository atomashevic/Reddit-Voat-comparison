#!/usr/bin/env python3
"""Follow fixed Voat arrival cohorts across later months.

This reviewer-response analysis complements the existing dynamic newcomer
definition. Users keep the cohort assigned from their first Voat activity, so
post-ban arrivals can be followed after they would otherwise be relabeled as
"existing" by the event-period analysis.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

LOGGER = logging.getLogger(__name__)

NORMAL_COMMUNITIES = ["funny", "gaming", "gifs", "pics", "technology", "videos"]


@dataclass(frozen=True)
class Event:
    key: str
    label: str
    date: pd.Timestamp


EVENTS_CHRONO = [
    Event("fph", "FPH", pd.Timestamp("2015-06-10")),
    Event("pg", "Pizzagate", pd.Timestamp("2016-11-23")),
    Event("ga", "GreatAwakening", pd.Timestamp("2018-09-12")),
    Event("td", "The_Donald", pd.Timestamp("2020-06-29")),
]

COHORT_ORDER = ["pre_fph", "fph_pg", "pg_ga", "ga_td", "td_shutdown"]
SHUTDOWN_MONTH = pd.Period("2020-12", freq="M")


def month_distance(start: pd.Period, end: pd.Period) -> int:
    """Return whole-month distance between monthly periods."""
    return (end.year - start.year) * 12 + (end.month - start.month)


def assign_fixed_cohort(first_seen: pd.Timestamp) -> str:
    """Assign a fixed chronological arrival cohort from first activity time."""
    if pd.isna(first_seen):
        return "unknown"
    if first_seen < EVENTS_CHRONO[0].date:
        return "pre_fph"
    if first_seen < EVENTS_CHRONO[1].date:
        return "fph_pg"
    if first_seen < EVENTS_CHRONO[2].date:
        return "pg_ga"
    if first_seen < EVENTS_CHRONO[3].date:
        return "ga_td"
    return "td_shutdown"


def read_first_seen(voat_parquet: Path) -> pd.DataFrame:
    """Load first activity timestamps for all users in a Voat community."""
    df = pd.read_parquet(voat_parquet, columns=["user_id", "publish_date"])
    df["user_id"] = df["user_id"].astype(str)
    publish_seconds = pd.to_numeric(df["publish_date"], errors="coerce")
    df["first_seen_dt"] = pd.to_datetime(publish_seconds, unit="s", errors="coerce")
    first_seen = (
        df.dropna(subset=["user_id", "first_seen_dt"])
        .groupby("user_id", as_index=False)["first_seen_dt"]
        .min()
    )
    first_seen["first_month"] = first_seen["first_seen_dt"].dt.to_period("M").astype(str)
    first_seen["fixed_cohort"] = first_seen["first_seen_dt"].apply(assign_fixed_cohort)
    first_seen["cohort_order"] = first_seen["fixed_cohort"].map(
        {cohort: idx for idx, cohort in enumerate(COHORT_ORDER)}
    )
    return first_seen.sort_values(["cohort_order", "first_seen_dt", "user_id"]).drop(
        columns=["cohort_order"]
    )


def read_user_month_metrics(results_root: Path, community: str) -> pd.DataFrame:
    path = results_root / "voat" / community / f"voat_{community}_user_month_metrics.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing user-month metrics: {path}")
    df = pd.read_parquet(path)
    df["user_id"] = df["user_id"].astype(str)
    df["month_period"] = pd.PeriodIndex(df["month"], freq="M")
    return df


def read_edges(edge_file: Path) -> pd.DataFrame:
    return pd.read_csv(
        edge_file,
        sep=r"\s+",
        names=["source", "target"],
        dtype=str,
        engine="python",
    ).dropna(subset=["source", "target"])


def rank_top_decile_hubs(degrees: pd.Series) -> set[str]:
    """Return deterministic top-10% degree hubs for one monthly graph."""
    if degrees.empty:
        return set()
    n_hubs = max(1, math.ceil(len(degrees) * 0.10))
    ordered = degrees.reset_index()
    ordered.columns = ["user_id", "degree"]
    ordered = ordered.sort_values(["degree", "user_id"], ascending=[False, True])
    return set(ordered.head(n_hubs)["user_id"].astype(str))


def compute_monthly_network_rows(
    community: str,
    networks_dir: Path,
    first_seen: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute cohort-month network metrics and user-month hub flags."""
    net_dir = networks_dir / "voat" / f"{community}_monthly"
    if not net_dir.exists():
        raise FileNotFoundError(f"Missing network directory: {net_dir}")

    cohort_map = first_seen.set_index("user_id")["fixed_cohort"]
    cohort_month_rows = []
    user_month_rows = []

    for edge_file in sorted(net_dir.glob(f"{community}_*.txt")):
        month = edge_file.stem.replace(f"{community}_", "")
        edges = read_edges(edge_file)
        if edges.empty:
            continue

        degrees = pd.concat([edges["source"], edges["target"]]).value_counts().astype(float)
        degrees.index = degrees.index.astype(str)
        hubs = rank_top_decile_hubs(degrees)
        total_degree = float(degrees.sum())
        n_nodes = int(len(degrees))
        n_edges = int(len(edges))
        degree_p90 = float(np.percentile(degrees.to_numpy(dtype=float), 90))

        nodes = pd.DataFrame({"user_id": degrees.index, "degree": degrees.values})
        nodes["fixed_cohort"] = nodes["user_id"].map(cohort_map).fillna("unknown")
        nodes["is_hub"] = nodes["user_id"].isin(hubs)
        user_month_rows.append(
            nodes.assign(
                community=community,
                month=month,
                hub_threshold_p90_degree=degree_p90,
            )[
                [
                    "community",
                    "month",
                    "user_id",
                    "fixed_cohort",
                    "degree",
                    "is_hub",
                    "hub_threshold_p90_degree",
                ]
            ]
        )

        for cohort in COHORT_ORDER:
            cohort_nodes = nodes[nodes["fixed_cohort"] == cohort]
            n_cohort = int(len(cohort_nodes))
            degree_sum = float(cohort_nodes["degree"].sum()) if n_cohort else 0.0
            pop_share = n_cohort / n_nodes if n_nodes else np.nan
            degree_share = degree_sum / total_degree if total_degree else np.nan
            cohort_month_rows.append(
                {
                    "community": community,
                    "month": month,
                    "fixed_cohort": cohort,
                    "n_nodes": n_nodes,
                    "n_edges": n_edges,
                    "cohort_active_nodes": n_cohort,
                    "cohort_pop_share": pop_share,
                    "cohort_degree_share": degree_share,
                    "degree_share_ratio": (
                        degree_share / pop_share if pop_share and not pd.isna(degree_share) else np.nan
                    ),
                    "mean_degree": (
                        float(cohort_nodes["degree"].mean()) if n_cohort else np.nan
                    ),
                    "median_degree": (
                        float(cohort_nodes["degree"].median()) if n_cohort else np.nan
                    ),
                    "hub_user_count": int(cohort_nodes["is_hub"].sum()),
                    "hub_rate": (
                        float(cohort_nodes["is_hub"].mean()) if n_cohort else np.nan
                    ),
                    "hub_rate_equality_baseline": 0.10,
                    "hub_threshold_p90_degree": degree_p90,
                }
            )

    cohort_month = pd.DataFrame(cohort_month_rows)
    user_month = pd.concat(user_month_rows, ignore_index=True) if user_month_rows else pd.DataFrame()
    return cohort_month, user_month


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return np.nan
    return float(np.average(values[mask], weights=weights[mask]))


def summarize_user_months(
    community: str,
    user_month: pd.DataFrame,
    first_seen: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create user-level cohort summary and cohort-month behavior summary."""
    merged = user_month.merge(first_seen, on="user_id", how="left")
    merged["community"] = community
    merged["fixed_cohort"] = merged["fixed_cohort"].fillna("unknown")
    merged = merged[merged["fixed_cohort"].isin(COHORT_ORDER)].copy()
    merged["month_period"] = pd.PeriodIndex(merged["month"], freq="M")

    def first_three_mean(group: pd.DataFrame) -> float:
        values = group.sort_values("month_period").head(3)["mean_toxicity"]
        return float(values.mean()) if values.notna().any() else np.nan

    active = merged.sort_values(["user_id", "month_period"])
    first_month = active.groupby("user_id")["month_period"].min()
    last_month = active.groupby("user_id")["month_period"].max()
    first_month_activity = (
        active.merge(first_month.rename("first_active_month"), on="user_id")
        .query("month_period == first_active_month")
        .groupby("user_id")["activity_count"]
        .sum()
    )

    summary = (
        active.groupby("user_id")
        .agg(
            community=("community", "first"),
            fixed_cohort=("fixed_cohort", "first"),
            first_month=("first_month", "first"),
            first_active_month=("month_period", "min"),
            last_active_month=("month_period", "max"),
            active_months=("month_period", "nunique"),
            total_activity=("activity_count", "sum"),
            mean_toxicity=("mean_toxicity", "mean"),
        )
        .reset_index()
    )
    early_toxicity = active.groupby("user_id").apply(first_three_mean, include_groups=False)
    summary["early_toxicity_first3_months"] = summary["user_id"].map(early_toxicity)
    summary["first_month_activity_count"] = summary["user_id"].map(first_month_activity).fillna(0)
    summary["survival_months"] = [
        month_distance(start, end) + 1
        for start, end in zip(summary["first_active_month"], summary["last_active_month"])
    ]
    summary["right_censored_shutdown"] = summary["last_active_month"] >= SHUTDOWN_MONTH
    for offset in [1, 3, 6, 12]:
        summary[f"retained_{offset}m"] = (
            summary["survival_months"] >= (offset + 1)
        )

    thresholds = (
        summary.groupby(["community", "fixed_cohort"])["first_month_activity_count"]
        .quantile(0.90)
        .rename("activity_q90")
        .reset_index()
    )
    summary = summary.merge(thresholds, on=["community", "fixed_cohort"], how="left")
    summary["activity_group"] = np.where(
        summary["first_month_activity_count"] >= summary["activity_q90"],
        "high_activity",
        "lower_activity",
    )

    toxicity_thresholds = (
        summary.groupby(["community", "fixed_cohort"])["early_toxicity_first3_months"]
        .quantile(0.75)
        .rename("early_toxicity_q75")
        .reset_index()
    )
    summary = summary.merge(toxicity_thresholds, on=["community", "fixed_cohort"], how="left")
    summary["toxicity_group"] = np.where(
        summary["early_toxicity_first3_months"] >= summary["early_toxicity_q75"],
        "high_toxicity",
        "lower_toxicity",
    )

    behavior = (
        merged.groupby(["community", "month", "fixed_cohort"])
        .apply(
            lambda g: pd.Series(
                {
                    "active_user_months": g["user_id"].nunique(),
                    "activity_count": g["activity_count"].sum(),
                    "mean_toxicity_equal_user": g["mean_toxicity"].mean(),
                    "mean_toxicity_activity_weighted": weighted_mean(
                        g["mean_toxicity"], g["activity_count"]
                    ),
                    "mean_reputation": g["mean_reputation"].mean()
                    if "mean_reputation" in g
                    else np.nan,
                    "mean_activity_count": g["activity_count"].mean(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    return summary, behavior


def attach_hub_ascent(user_summary: pd.DataFrame, network_user_month: pd.DataFrame) -> pd.DataFrame:
    if network_user_month.empty:
        user_summary["ever_hub"] = False
        user_summary["first_hub_month"] = pd.NA
        user_summary["months_to_first_hub"] = np.nan
        return user_summary

    hub_rows = network_user_month[network_user_month["is_hub"]].copy()
    first_hub = hub_rows.groupby("user_id")["month"].min().rename("first_hub_month")
    out = user_summary.merge(first_hub, on="user_id", how="left")
    out["ever_hub"] = out["first_hub_month"].notna()
    first_hub_period = pd.PeriodIndex(
        out["first_hub_month"].fillna("1900-01"), freq="M"
    )
    out["months_to_first_hub"] = [
        month_distance(start, hub) if ever else np.nan
        for start, hub, ever in zip(out["first_active_month"], first_hub_period, out["ever_hub"])
    ]
    return out


def summarize_structural_ascent(monthly: pd.DataFrame, users: pd.DataFrame) -> pd.DataFrame:
    network_users = users.groupby(["community", "fixed_cohort"]).agg(
        cohort_users=("user_id", "nunique"),
        user_ever_hub_rate=("ever_hub", "mean"),
        median_months_to_first_hub=("months_to_first_hub", "median"),
    )
    high_activity = (
        users[users["activity_group"] == "high_activity"]
        .groupby(["community", "fixed_cohort"])["ever_hub"]
        .mean()
        .rename("high_activity_ever_hub_rate")
    )
    monthly_summary = (
        monthly[monthly["cohort_active_nodes"] > 0]
        .groupby(["community", "fixed_cohort"])
        .agg(
            months_observed=("month", "nunique"),
            median_degree_share_ratio=("degree_share_ratio", "median"),
            share_months_underrepresented=("degree_share_ratio", lambda s: float((s < 1).mean())),
            mean_hub_rate=("hub_rate", "mean"),
            median_hub_rate=("hub_rate", "median"),
            mean_pop_share=("cohort_pop_share", "mean"),
            mean_degree_share=("cohort_degree_share", "mean"),
        )
    )
    return (
        monthly_summary.join(network_users, how="outer")
        .join(high_activity, how="left")
        .reset_index()
        .sort_values(["community", "fixed_cohort"])
    )


def summarize_retention_toxicity(users: pd.DataFrame) -> pd.DataFrame:
    return (
        users.groupby(["community", "fixed_cohort", "toxicity_group"])
        .agg(
            n_users=("user_id", "nunique"),
            mean_early_toxicity=("early_toxicity_first3_months", "mean"),
            median_survival_months=("survival_months", "median"),
            retained_1m_rate=("retained_1m", "mean"),
            retained_3m_rate=("retained_3m", "mean"),
            retained_6m_rate=("retained_6m", "mean"),
            retained_12m_rate=("retained_12m", "mean"),
            ever_hub_rate=("ever_hub", "mean"),
            right_censored_shutdown_rate=("right_censored_shutdown", "mean"),
        )
        .reset_index()
        .sort_values(["community", "fixed_cohort", "toxicity_group"])
    )


def summarize_proxy_noise(community: str, first_seen: pd.DataFrame) -> pd.DataFrame:
    counts = first_seen.copy()
    counts["first_month_period"] = pd.PeriodIndex(counts["first_month"], freq="M")
    month_counts = counts.groupby("first_month_period")["user_id"].nunique()

    rows = []
    for event in EVENTS_CHRONO:
        event_month = event.date.to_period("M")
        baseline_months = [event_month - i for i in range(1, 7)]
        event_window = [event_month + i for i in range(3)]
        baseline_values = [int(month_counts.get(month, 0)) for month in baseline_months]
        expected = float(np.median(baseline_values))
        observed = int(sum(month_counts.get(month, 0) for month in event_window))
        expected_window = expected * len(event_window)
        excess = max(0.0, observed - expected_window)
        rows.append(
            {
                "community": community,
                "event_key": event.key,
                "event_label": event.label,
                "event_month": str(event_month),
                "baseline_months": ",".join(str(m) for m in sorted(baseline_months)),
                "event_window_months": ",".join(str(m) for m in event_window),
                "baseline_median_monthly_first_users": expected,
                "observed_first_users_event_plus_2m": observed,
                "expected_first_users_event_plus_2m": expected_window,
                "excess_first_users": excess,
                "proxy_noise_upper_bound": (
                    1.0 - (excess / observed) if observed > 0 else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def plot_degree_share_ratio(summary: pd.DataFrame, output_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        LOGGER.warning("matplotlib unavailable; skipping %s", output_path)
        return

    cohorts = COHORT_ORDER
    pivot = summary.pivot(index="community", columns="fixed_cohort", values="median_degree_share_ratio")
    pivot = pivot.reindex(columns=cohorts)
    ax = pivot.plot(kind="bar", figsize=(11, 5), width=0.85)
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1, alpha=0.7)
    ax.set_ylabel("Median degree share / population share")
    ax.set_xlabel("Community")
    ax.set_title("Fixed arrival cohort structural representation")
    ax.legend(title="Cohort", fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def plot_retention_by_toxicity(summary: pd.DataFrame, output_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        LOGGER.warning("matplotlib unavailable; skipping %s", output_path)
        return

    plot_df = summary.groupby("toxicity_group", as_index=False)[
        ["retained_1m_rate", "retained_3m_rate", "retained_6m_rate", "retained_12m_rate"]
    ].mean()
    plot_df = plot_df.set_index("toxicity_group").T
    ax = plot_df.plot(kind="bar", figsize=(8, 5))
    ax.set_ylim(0, 1)
    ax.set_ylabel("Mean retention rate across cohort-community groups")
    ax.set_xlabel("Retention horizon")
    ax.set_title("Retention by early toxicity group")
    ax.grid(axis="y", alpha=0.25)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def process_community(
    community: str,
    data_dir: Path,
    results_root: Path,
    networks_dir: Path,
    output_dir: Path,
    write_detail_tables: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    LOGGER.info("Processing %s", community)
    first_seen = read_first_seen(data_dir / f"voat_{community}_madoc.parquet")
    user_month = read_user_month_metrics(results_root, community)
    user_summary, behavior = summarize_user_months(
        community, user_month, first_seen
    )
    network_monthly, network_user_month = compute_monthly_network_rows(
        community, networks_dir, first_seen
    )
    user_summary = attach_hub_ascent(user_summary, network_user_month)
    monthly = network_monthly.merge(
        behavior,
        on=["community", "month", "fixed_cohort"],
        how="outer",
    ).sort_values(["community", "month", "fixed_cohort"])

    if write_detail_tables:
        out_results = output_dir / "voat" / "results"
        out_results.mkdir(parents=True, exist_ok=True)
        monthly.to_csv(out_results / f"voat_{community}_fixed_cohort_monthly.csv", index=False)
        user_summary.to_csv(out_results / f"voat_{community}_fixed_cohort_users.csv", index=False)
    return monthly, user_summary, summarize_proxy_noise(community, first_seen)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--communities", nargs="+", default=NORMAL_COMMUNITIES)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--results-root", type=Path, default=Path("results"))
    parser.add_argument("--networks-dir", type=Path, default=Path("results/networks"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/basic"))
    parser.add_argument("--figures-dir", type=Path, default=Path("results/basic/compare/figures"))
    parser.add_argument(
        "--write-detail-tables",
        action="store_true",
        help="Also write per-community user/month detail tables under results/basic/voat/results.",
    )
    parser.add_argument("--skip-figures", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    all_monthly = []
    all_users = []
    all_noise = []
    for community in args.communities:
        monthly, users, noise = process_community(
            community=community,
            data_dir=args.data_dir,
            results_root=args.results_root,
            networks_dir=args.networks_dir,
            output_dir=args.output_dir,
            write_detail_tables=args.write_detail_tables,
        )
        all_monthly.append(monthly)
        all_users.append(users)
        all_noise.append(noise)

    combined_monthly = pd.concat(all_monthly, ignore_index=True)
    combined_users = pd.concat(all_users, ignore_index=True)
    combined_noise = pd.concat(all_noise, ignore_index=True)
    structural = summarize_structural_ascent(combined_monthly, combined_users)
    retention = summarize_retention_toxicity(combined_users)

    compare_results = args.output_dir / "compare" / "results"
    compare_results.mkdir(parents=True, exist_ok=True)
    structural.to_csv(
        compare_results / "fixed_cohort_structural_ascent_summary.csv", index=False
    )
    retention.to_csv(
        compare_results / "fixed_cohort_retention_toxicity_summary.csv", index=False
    )
    combined_noise.to_csv(compare_results / "postban_proxy_noise_summary.csv", index=False)

    if not args.skip_figures:
        plot_degree_share_ratio(
            structural, args.figures_dir / "fixed_cohort_degree_share_ratio.png"
        )
        plot_retention_by_toxicity(
            retention, args.figures_dir / "fixed_cohort_retention_by_toxicity.png"
        )

    LOGGER.info("Wrote fixed-cohort outputs under %s", args.output_dir)


if __name__ == "__main__":
    main()
