#!/usr/bin/env python3
"""Fixed arrival-cohort retention and structural-ascent analysis.

This reviewer-response script follows users by their first Voat activity
cohort instead of relabeling them at each Reddit ban boundary. The goal is a
compact descriptive check: do event-timed arrivals persist, and do they become
network hubs?
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
POST_BAN_COHORTS = ["fph_pg", "pg_ga", "ga_td", "td_shutdown"]
COHORT_ORDER = ["pre_fph", *POST_BAN_COHORTS]
COHORT_RANK = {cohort: idx for idx, cohort in enumerate(COHORT_ORDER)}
SHUTDOWN_MONTH = pd.Period("2020-12", freq="M")

PRIMARY_EARLY_MONTHS = 3
PRIMARY_TOXICITY_QUANTILE = 0.75
PRIMARY_HUB_FRACTION = 0.10

EARLY_MONTH_SENSITIVITY = [1, 3, 6]
TOXICITY_QUANTILE_SENSITIVITY = [0.50, 0.75, 0.90]
HUB_FRACTION_SENSITIVITY = [0.05, 0.10, 0.20]
SURVIVAL_HORIZONS = [3, 6, 12]


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


def month_distance(start: pd.Period, end: pd.Period) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def assign_fixed_cohort(first_seen: pd.Timestamp) -> str:
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


def parse_month(edge_file: Path, community: str) -> str:
    prefix = f"{community}_"
    if not edge_file.stem.startswith(prefix):
        raise ValueError(f"Unexpected edge filename for {community}: {edge_file}")
    return edge_file.stem.removeprefix(prefix)


def read_first_seen(data_dir: Path, community: str) -> pd.DataFrame:
    path = data_dir / f"voat_{community}_madoc.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing Voat data parquet: {path}")
    df = pd.read_parquet(path, columns=["user_id", "publish_date"])
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
    return first_seen


def read_user_month_metrics(results_root: Path, community: str) -> pd.DataFrame:
    path = results_root / "voat" / community / f"voat_{community}_user_month_metrics.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing user-month metrics: {path}")
    df = pd.read_parquet(path)
    df["user_id"] = df["user_id"].astype(str)
    df["month_period"] = pd.PeriodIndex(df["month"], freq="M")
    return df


def read_degrees(edge_file: Path) -> pd.Series:
    edges = pd.read_csv(
        edge_file,
        sep=r"\s+",
        names=["source", "target"],
        dtype=str,
        engine="python",
    ).dropna(subset=["source", "target"])
    if edges.empty:
        return pd.Series(dtype=float)

    pairs = edges[["source", "target"]].astype(str)
    a = pairs.min(axis=1)
    b = pairs.max(axis=1)
    unique_pairs = pd.DataFrame({"source": a, "target": b}).drop_duplicates()
    if unique_pairs.empty:
        return pd.Series(dtype=float)

    degrees = pd.concat([unique_pairs["source"], unique_pairs["target"]]).value_counts()
    degrees.index = degrees.index.astype(str)
    return degrees.astype(float)


def top_fraction_hubs(degrees: pd.Series, fraction: float) -> set[str]:
    if degrees.empty:
        return set()
    n_hubs = max(1, math.ceil(len(degrees) * fraction))
    ordered = degrees.reset_index()
    ordered.columns = ["user_id", "degree"]
    ordered = ordered.sort_values(["degree", "user_id"], ascending=[False, True])
    return set(ordered.head(n_hubs)["user_id"].astype(str))


def first_k_active_month_mean(group: pd.DataFrame, k: int) -> float:
    values = group.sort_values("month_period").head(k)["mean_toxicity"]
    return float(values.mean()) if values.notna().any() else np.nan


def kaplan_meier_curve(durations: Iterable[float], events: Iterable[bool]) -> pd.DataFrame:
    """Estimate a Kaplan-Meier curve for right-censored user spells."""
    duration_values = np.asarray(list(durations), dtype=float)
    event_values = np.asarray(list(events), dtype=bool)
    valid = np.isfinite(duration_values) & (duration_values > 0)
    duration_values = duration_values[valid]
    event_values = event_values[valid]

    survival = 1.0
    rows = [{"time_months": 0.0, "survival_probability": 1.0}]
    for time in np.sort(np.unique(duration_values[event_values])):
        at_risk = int(np.sum(duration_values >= time))
        n_events = int(np.sum((duration_values == time) & event_values))
        n_censored = int(np.sum((duration_values == time) & ~event_values))
        if at_risk <= 0:
            continue
        survival *= 1.0 - (n_events / at_risk)
        rows.append(
            {
                "time_months": float(time),
                "n_at_risk": at_risk,
                "n_events": n_events,
                "n_censored": n_censored,
                "survival_probability": float(survival),
            }
        )
    return pd.DataFrame(rows)


def survival_at(curve: pd.DataFrame, horizon: int) -> float:
    if curve.empty:
        return np.nan
    previous = curve[curve["time_months"] <= horizon]
    if previous.empty:
        return 1.0
    return float(previous.iloc[-1]["survival_probability"])


def sort_by_cohort(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["_cohort_rank"] = out["fixed_cohort"].map(COHORT_RANK)
    return out.sort_values(["_cohort_rank", *columns]).drop(columns=["_cohort_rank"])


def build_user_summary(
    community: str,
    data_dir: Path,
    results_root: Path,
) -> pd.DataFrame:
    first_seen = read_first_seen(data_dir, community)
    user_month = read_user_month_metrics(results_root, community)
    merged = user_month.merge(
        first_seen[["user_id", "first_seen_dt", "first_month", "fixed_cohort"]],
        on="user_id",
        how="left",
    )
    merged = merged[merged["fixed_cohort"].isin(COHORT_ORDER)].copy()
    merged["community"] = community

    active = merged.sort_values(["user_id", "month_period"])
    first_active = active.groupby("user_id")["month_period"].min().rename("first_active_month")
    first_month_activity = (
        active.merge(first_active, on="user_id")
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

    for k in EARLY_MONTH_SENSITIVITY:
        early = active.groupby("user_id").apply(
            first_k_active_month_mean,
            k=k,
            include_groups=False,
        )
        summary[f"early_toxicity_first{k}_months"] = summary["user_id"].map(early)

    summary["first_month_activity_count"] = summary["user_id"].map(first_month_activity).fillna(0)
    summary["survival_months"] = [
        month_distance(start, end) + 1
        for start, end in zip(summary["first_active_month"], summary["last_active_month"])
    ]
    summary["event_observed"] = summary["last_active_month"] < SHUTDOWN_MONTH
    for horizon in SURVIVAL_HORIZONS:
        summary[f"retained_{horizon}m"] = summary["survival_months"] >= (horizon + 1)

    activity_q90 = (
        summary.groupby(["community", "fixed_cohort"])["first_month_activity_count"]
        .quantile(0.90)
        .rename("activity_q90")
        .reset_index()
    )
    summary = summary.merge(activity_q90, on=["community", "fixed_cohort"], how="left")
    summary["activity_group"] = np.where(
        summary["first_month_activity_count"] >= summary["activity_q90"],
        "high_activity",
        "lower_activity",
    )
    return summary


def build_network_summary(
    community: str,
    results_root: Path,
    first_seen: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    net_dir = results_root / "networks" / "voat" / f"{community}_monthly"
    if not net_dir.exists():
        raise FileNotFoundError(f"Missing network directory: {net_dir}")

    cohort_map = first_seen.set_index("user_id")["fixed_cohort"]
    monthly_rows = []
    user_hub_rows = []

    for edge_file in sorted(net_dir.glob(f"{community}_*.txt")):
        month = parse_month(edge_file, community)
        degrees = read_degrees(edge_file)
        if degrees.empty:
            continue

        nodes = pd.DataFrame({"user_id": degrees.index, "degree": degrees.values})
        nodes["fixed_cohort"] = nodes["user_id"].map(cohort_map).fillna("unknown")
        nodes = nodes[nodes["fixed_cohort"].isin(COHORT_ORDER)].copy()
        if nodes.empty:
            continue

        total_degree = float(nodes["degree"].sum())
        n_nodes = int(len(nodes))

        for fraction in HUB_FRACTION_SENSITIVITY:
            hubs = top_fraction_hubs(degrees, fraction)
            hub_col = f"ever_hub_top{int(round(fraction * 100))}"
            hub_nodes = nodes[["user_id", "fixed_cohort"]].copy()
            hub_nodes["community"] = community
            hub_nodes["month"] = month
            hub_nodes["hub_fraction"] = fraction
            hub_nodes[hub_col] = hub_nodes["user_id"].isin(hubs)
            user_hub_rows.append(hub_nodes)

        for cohort in COHORT_ORDER:
            cohort_nodes = nodes[nodes["fixed_cohort"] == cohort]
            n_cohort = int(len(cohort_nodes))
            if not n_cohort:
                continue
            pop_share = n_cohort / n_nodes
            degree_share = float(cohort_nodes["degree"].sum()) / total_degree if total_degree else np.nan
            monthly_rows.append(
                {
                    "community": community,
                    "month": month,
                    "fixed_cohort": cohort,
                    "cohort_active_nodes": n_cohort,
                    "cohort_pop_share": pop_share,
                    "cohort_degree_share": degree_share,
                    "degree_share_ratio": degree_share / pop_share if pop_share else np.nan,
                }
            )

    monthly = pd.DataFrame(monthly_rows)
    user_hubs = pd.concat(user_hub_rows, ignore_index=True) if user_hub_rows else pd.DataFrame()
    return monthly, user_hubs


def attach_ever_hub_flags(users: pd.DataFrame, user_hubs: pd.DataFrame) -> pd.DataFrame:
    out = users.copy()
    for fraction in HUB_FRACTION_SENSITIVITY:
        pct = int(round(fraction * 100))
        col = f"ever_hub_top{pct}"
        if user_hubs.empty:
            out[col] = False
            continue
        scoped = user_hubs[user_hubs["hub_fraction"] == fraction]
        if scoped.empty or col not in scoped.columns:
            out[col] = False
            continue
        ever = scoped.groupby(["community", "user_id"])[col].max().rename(col).reset_index()
        out = out.merge(ever, on=["community", "user_id"], how="left")
        out[col] = out[col].eq(True)
    return out


def add_toxicity_groups(users: pd.DataFrame, early_months: int, quantile: float) -> pd.DataFrame:
    out = users.copy()
    tox_col = f"early_toxicity_first{early_months}_months"
    threshold_col = f"toxicity_q{int(round(quantile * 100))}_first{early_months}m"
    thresholds = (
        out.groupby(["community", "fixed_cohort"])[tox_col]
        .quantile(quantile)
        .rename(threshold_col)
        .reset_index()
    )
    out = out.merge(thresholds, on=["community", "fixed_cohort"], how="left")
    out["toxicity_group"] = np.where(
        out[tox_col] >= out[threshold_col],
        "high_toxicity",
        "lower_toxicity",
    )
    out.loc[out[tox_col].isna(), "toxicity_group"] = pd.NA
    return out


def summarize_survival_definition(
    users: pd.DataFrame,
    early_months: int,
    quantile: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    grouped_users = add_toxicity_groups(users, early_months, quantile)
    grouped_users = grouped_users[grouped_users["fixed_cohort"].isin(POST_BAN_COHORTS)].copy()
    global_users = grouped_users.copy()
    global_users["community"] = "global"
    scoped = pd.concat([grouped_users, global_users], ignore_index=True)

    summary_rows = []
    curve_rows = []
    for (community, cohort), group in scoped.groupby(["community", "fixed_cohort"]):
        group = group.dropna(subset=["toxicity_group", "survival_months"])
        if group.empty or group["toxicity_group"].nunique() < 2:
            continue

        row: dict[str, float | int | str] = {
            "community": community,
            "fixed_cohort": cohort,
            "early_months": early_months,
            "high_toxicity_quantile": quantile,
            "n_users": int(len(group)),
            "n_high_toxicity": int((group["toxicity_group"] == "high_toxicity").sum()),
            "n_lower_toxicity": int((group["toxicity_group"] == "lower_toxicity").sum()),
            "censored_rate": float((~group["event_observed"]).mean()),
        }
        for label in ["high_toxicity", "lower_toxicity"]:
            label_group = group[group["toxicity_group"] == label]
            curve = kaplan_meier_curve(
                label_group["survival_months"],
                label_group["event_observed"],
            )
            if (
                community == "global"
                and early_months == PRIMARY_EARLY_MONTHS
                and quantile == PRIMARY_TOXICITY_QUANTILE
            ):
                for _, curve_row in curve.iterrows():
                    curve_rows.append(
                        {
                            "community": community,
                            "fixed_cohort": cohort,
                            "toxicity_group": label,
                            **curve_row.to_dict(),
                        }
                    )

            prefix = "high" if label == "high_toxicity" else "lower"
            row[f"median_survival_months_{prefix}"] = float(label_group["survival_months"].median())
            for horizon in SURVIVAL_HORIZONS:
                row[f"km_survival_{horizon}m_{prefix}"] = survival_at(curve, horizon)
                row[f"retention_{horizon}m_{prefix}"] = float(label_group[f"retained_{horizon}m"].mean())

        for horizon in SURVIVAL_HORIZONS:
            row[f"km_survival_{horizon}m_high_minus_lower"] = (
                row[f"km_survival_{horizon}m_high"] - row[f"km_survival_{horizon}m_lower"]
            )
            row[f"retention_{horizon}m_high_minus_lower"] = (
                row[f"retention_{horizon}m_high"] - row[f"retention_{horizon}m_lower"]
            )
        summary_rows.append(row)

    summary = sort_by_cohort(
        pd.DataFrame(summary_rows),
        ["community", "early_months", "high_toxicity_quantile"],
    )
    curves = pd.DataFrame(curve_rows)
    return summary, curves


def summarize_sensitivity(users: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for early_months in EARLY_MONTH_SENSITIVITY:
        for quantile in TOXICITY_QUANTILE_SENSITIVITY:
            summary, _ = summarize_survival_definition(users, early_months, quantile)
            frames.append(summary[summary["community"] == "global"])
    sensitivity = pd.concat(frames, ignore_index=True)
    keep = [
        "fixed_cohort",
        "early_months",
        "high_toxicity_quantile",
        "n_users",
        "n_high_toxicity",
        "km_survival_3m_high_minus_lower",
        "km_survival_12m_high_minus_lower",
        "retention_3m_high_minus_lower",
        "retention_12m_high_minus_lower",
    ]
    return sort_by_cohort(
        sensitivity[keep],
        ["early_months", "high_toxicity_quantile"],
    )


def summarize_hubs(users: pd.DataFrame, monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for fraction in HUB_FRACTION_SENSITIVITY:
        pct = int(round(fraction * 100))
        hub_col = f"ever_hub_top{pct}"
        for cohort in POST_BAN_COHORTS:
            cohort_users = users[users["fixed_cohort"] == cohort]
            high_activity = cohort_users[cohort_users["activity_group"] == "high_activity"]
            cohort_months = monthly[monthly["fixed_cohort"] == cohort]
            rows.append(
                {
                    "fixed_cohort": cohort,
                    "hub_fraction": fraction,
                    "hub_equality_baseline": fraction,
                    "n_users": int(cohort_users["user_id"].nunique()),
                    "median_degree_share_ratio": float(cohort_months["degree_share_ratio"].median()),
                    "share_months_underrepresented": float((cohort_months["degree_share_ratio"] < 1).mean()),
                    "mean_ever_hub_rate": float(cohort_users[hub_col].mean()),
                    "high_activity_ever_hub_rate": (
                        float(high_activity[hub_col].mean()) if not high_activity.empty else np.nan
                    ),
                }
            )
    return sort_by_cohort(pd.DataFrame(rows), ["hub_fraction"])


def plot_global_km(curves: pd.DataFrame, output_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        LOGGER.warning("matplotlib is unavailable; skipping %s", output_path)
        return

    colors = {"lower_toxicity": "#2c7fb8", "high_toxicity": "#d95f0e"}
    labels = {"lower_toxicity": "Lower early toxicity", "high_toxicity": "High early toxicity"}
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True, sharey=True)

    for ax, cohort in zip(axes.ravel(), POST_BAN_COHORTS):
        cohort_df = curves[curves["fixed_cohort"] == cohort]
        for group in ["lower_toxicity", "high_toxicity"]:
            sub = cohort_df[cohort_df["toxicity_group"] == group]
            if sub.empty:
                continue
            ax.step(
                sub["time_months"],
                sub["survival_probability"],
                where="post",
                label=labels[group],
                color=colors[group],
                linewidth=1.8,
            )
        ax.set_title(cohort)
        ax.grid(alpha=0.25)
        ax.set_ylim(0, 1.02)

    for ax in axes[:, 0]:
        ax.set_ylabel("Kaplan-Meier survival")
    for ax in axes[-1, :]:
        ax.set_xlabel("Months since first active month")
    axes[0, 0].legend(frameon=False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--communities", nargs="+", default=NORMAL_COMMUNITIES)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--results-root", type=Path, default=Path("results"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/basic/compare"),
        help="Output directory containing results/ and figures/ subdirectories.",
    )
    parser.add_argument("--skip-figures", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    user_frames = []
    monthly_frames = []
    hub_frames = []
    for community in args.communities:
        LOGGER.info("Processing %s", community)
        users = build_user_summary(community, args.data_dir, args.results_root)
        first_seen = read_first_seen(args.data_dir, community)
        monthly, user_hubs = build_network_summary(community, args.results_root, first_seen)
        user_frames.append(users)
        monthly_frames.append(monthly)
        hub_frames.append(user_hubs)

    users = pd.concat(user_frames, ignore_index=True)
    monthly = pd.concat(monthly_frames, ignore_index=True)
    user_hubs = pd.concat(hub_frames, ignore_index=True)
    users = attach_ever_hub_flags(users, user_hubs)

    primary, curves = summarize_survival_definition(
        users,
        early_months=PRIMARY_EARLY_MONTHS,
        quantile=PRIMARY_TOXICITY_QUANTILE,
    )
    primary_global = primary[primary["community"] == "global"].copy()
    sensitivity = summarize_sensitivity(users)
    hubs = summarize_hubs(users, monthly)

    results_dir = args.output_dir / "results"
    figures_dir = args.output_dir / "figures"
    results_dir.mkdir(parents=True, exist_ok=True)
    primary_global.to_csv(results_dir / "fixed_cohort_survival_retention_summary.csv", index=False)
    sensitivity.to_csv(results_dir / "fixed_cohort_toxicity_definition_sensitivity.csv", index=False)
    hubs.to_csv(results_dir / "fixed_cohort_hub_sensitivity_summary.csv", index=False)

    if not args.skip_figures:
        plot_global_km(curves, figures_dir / "fixed_cohort_km_survival_by_toxicity.png")

    LOGGER.info("Wrote fixed-cohort outputs to %s", args.output_dir)


if __name__ == "__main__":
    main()
