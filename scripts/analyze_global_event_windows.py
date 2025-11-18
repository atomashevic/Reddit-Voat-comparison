#!/usr/bin/env python3
"""Analyze metrics around key migration events (A, B, C).

Computes mean metrics for 3-month windows before and after each event
for both Reddit and Voat, calculating the 'Jump' (Post - Pre).
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Add scripts dir to path to import utils
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.migration_utils import EVENTS, METRICS, load_monthly_aggregates, get_event_window

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", required=True)
    parser.add_argument("--compare-dir", type=Path, required=True)
    parser.add_argument("--networks-dir", type=Path, help="Unused but kept for compat")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()

def analyze_event(
    reddit_df: pd.DataFrame, voat_df: pd.DataFrame, event_key: str, event_date: pd.Timestamp
):
    results = []
    
    for metric in METRICS:
        # Reddit
        r_pre, r_post = get_event_window(reddit_df, event_date)
        if not r_pre.empty and not r_post.empty:
            r_diff = r_post[metric].mean() - r_pre[metric].mean()
            results.append({
                "event": event_key,
                "platform": "reddit",
                "metric": metric,
                "pre_mean": r_pre[metric].mean(),
                "post_mean": r_post[metric].mean(),
                "jump": r_diff
            })
            
        # Voat
        v_pre, v_post = get_event_window(voat_df, event_date)
        if not v_pre.empty and not v_post.empty:
            v_diff = v_post[metric].mean() - v_pre[metric].mean()
            results.append({
                "event": event_key,
                "platform": "voat",
                "metric": metric,
                "pre_mean": v_pre[metric].mean(),
                "post_mean": v_post[metric].mean(),
                "jump": v_diff
            })
            
    return results

def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    
    # Load data (using compare dir which usually has the bootstrap aggregates, 
    # but we'll use the raw monthly aggregates for this analysis)
    # Actually, run_alternative_pipeline passes --compare-dir but the raw files
    # are in --basic-dir (alternative/reddit/results).
    # We'll deduce the paths relative to output-dir or use the utils loader.
    
    # HACK: The pipeline passes --compare-dir which is results/alternative/community/compare.
    # We need results/alternative/community.
    base_dir = args.compare_dir.parent
    
    try:
        reddit_df = load_monthly_aggregates(base_dir, "reddit", args.community)
        voat_df = load_monthly_aggregates(base_dir, "voat", args.community)
    except FileNotFoundError as e:
        logging.error(e)
        return

    all_results = []
    for key, date in EVENTS.items():
        logging.info(f"Analyzing Event {key} ({date.date()})...")
        all_results.extend(analyze_event(reddit_df, voat_df, key, date))
        
    if not all_results:
        logging.warning("No results generated (insufficient data around events)")
        return

    df = pd.DataFrame(all_results)
    
    output_dir = args.output_dir if args.output_dir else args.compare_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / f"{args.community}_global_event_window_summary.csv"
    df.to_csv(out_path, index=False)
    logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()

