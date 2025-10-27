#!/usr/bin/env python3
import os
# Prevent math/array libs from oversubscribing threads per process
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("BLIS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("ARROW_NUM_THREADS", "1")

import sys
import math
import glob
import argparse
import logging
import gc

import pandas as pd
import pyarrow.parquet as pq


def get_total_cpus() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except Exception:
        return os.cpu_count() or 1


def _bytes_to_human(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024.0:
            return f"{f:.1f} {u}"
        f /= 1024.0
    return f"{f:.1f} PB"


def get_memory_status() -> dict:
    """Return a dict with memory info: total, available, used, percent.

    Tries psutil if available, else falls back to Linux sysconf or /proc/meminfo.
    """
    # psutil path
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return {
            "total": int(vm.total),
            "available": int(vm.available),
            "used": int(vm.used),
            "percent": float(vm.percent),
            "source": "psutil",
        }
    except Exception:
        pass

    # Linux sysconf path
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        total_pages = os.sysconf("SC_PHYS_PAGES")
        available = int(page_size * avail_pages)
        total = int(page_size * total_pages)
        used = total - available
        percent = (used / total * 100.0) if total > 0 else 0.0
        return {
            "total": total,
            "available": available,
            "used": used,
            "percent": percent,
            "source": "sysconf",
        }
    except Exception:
        pass

    # /proc/meminfo fallback
    try:
        meminfo = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    meminfo[key] = int(val) * 1024  # kB -> bytes
        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable", 0)
        used = max(0, total - available)
        percent = (used / total * 100.0) if total > 0 else 0.0
        return {
            "total": total,
            "available": available,
            "used": used,
            "percent": percent,
            "source": "/proc/meminfo",
        }
    except Exception:
        return {"total": 0, "available": 0, "used": 0, "percent": 0.0, "source": "unknown"}


def find_parquet_files(path_or_glob: str) -> list[str]:
    if os.path.isdir(path_or_glob):
        return sorted(glob.glob(os.path.join(path_or_glob, "**", "*.parquet"), recursive=True))
    if os.path.isfile(path_or_glob) and path_or_glob.endswith(".parquet"):
        return [path_or_glob]
    files = sorted([p for p in glob.glob(path_or_glob, recursive=True) if p.endswith(".parquet")])
    return files


def _safe_to_datetime_utc(series: pd.Series) -> pd.Series:
    """Convert epoch timestamps to UTC date, handling seconds vs milliseconds.

    Heuristic:
    - If median value > 1e11, treat as milliseconds since epoch.
    - Otherwise, treat as seconds since epoch.
    """
    s = pd.to_numeric(series, errors="coerce")
    med = s.dropna().median()
    unit = "s"
    try:
        if pd.notna(med) and med > 1e11:
            unit = "ms"
    except Exception:
        unit = "s"
    dt = pd.to_datetime(s, unit=unit, utc=True, errors="coerce")
    return dt.dt.floor("D")


def _has_url_series(s: pd.Series) -> pd.Series:
    if pd.api.types.is_string_dtype(s):
        return s.notna() & s.str.strip().ne("")
    return s.notna()


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def process_single_file(
    file_path: str,
    date_col: str,
    platform_col: str,
    interaction_type_col: str,
    user_col: str,
    url_col: str,
    sentiment_col: str,
    community_col: str,
    allowed_platforms: set[str],
):
    try:
        table = pq.read_table(
            file_path,
            columns=[
                date_col,
                platform_col,
                interaction_type_col,
                user_col,
                url_col,
                sentiment_col,
                community_col,
                'sentiment_textblob',
                'subjectivity_textblob',
                'toxicity_toxigen',
                'post_id',
                'parent_id',
            ],
            use_threads=False,
        )
    except Exception as e:
        logging.error(f"Failed to read {file_path}: {e}")
        empty_agg1 = pd.DataFrame(columns=[
            "date","platform","interactions","posts","comments",
            "url_with_value","sentiment_sum","sentiment_count",
            "tb_sum","tb_count","subj_sum","subj_count","tox_sum","tox_count",
        ])
        empty_agg2 = pd.DataFrame(columns=[
            "date","platform","community","interactions","posts","comments",
            "url_with_value","sentiment_sum","sentiment_count",
            "tb_sum","tb_count","subj_sum","subj_count","tox_sum","tox_count",
        ])
        empty_uniq1 = pd.DataFrame(columns=["date","platform","user_id"])
        empty_uniq2 = pd.DataFrame(columns=["date","platform","community","user_id"])
        empty_ut1 = pd.DataFrame(columns=["date","platform","thread_id"])
        empty_ut2 = pd.DataFrame(columns=["date","platform","community","thread_id"])
        return empty_agg1, empty_agg2, empty_uniq1, empty_uniq2, empty_ut1, empty_ut2

    df = table.to_pandas()
    for c in [date_col, platform_col, interaction_type_col, user_col, url_col, sentiment_col, community_col]:
        if c not in df.columns:
            logging.warning(f"{file_path}: missing column {c}, skipping.")
            empty_agg1 = pd.DataFrame(columns=[
                "date","platform","interactions","posts","comments",
                "url_with_value","sentiment_sum","sentiment_count",
                "tb_sum","tb_count","subj_sum","subj_count","tox_sum","tox_count",
            ])
            empty_agg2 = pd.DataFrame(columns=[
                "date","platform","community","interactions","posts","comments",
                "url_with_value","sentiment_sum","sentiment_count",
                "tb_sum","tb_count","subj_sum","subj_count","tox_sum","tox_count",
            ])
            empty_uniq1 = pd.DataFrame(columns=["date","platform","user_id"])
            empty_uniq2 = pd.DataFrame(columns=["date","platform","community","user_id"])
            empty_ut1 = pd.DataFrame(columns=["date","platform","thread_id"])
            empty_ut2 = pd.DataFrame(columns=["date","platform","community","thread_id"])
            return empty_agg1, empty_agg2, empty_uniq1, empty_uniq2, empty_ut1, empty_ut2

    df[platform_col] = df[platform_col].astype(str).str.lower()
    df = df[df[platform_col].isin(allowed_platforms)]
    if df.empty:
        empty_agg1 = pd.DataFrame(columns=[
            "date","platform","interactions","posts","comments",
            "url_with_value","sentiment_sum","sentiment_count",
            "tb_sum","tb_count","subj_sum","subj_count","tox_sum","tox_count",
        ])
        empty_agg2 = pd.DataFrame(columns=[
            "date","platform","community","interactions","posts","comments",
            "url_with_value","sentiment_sum","sentiment_count",
            "tb_sum","tb_count","subj_sum","subj_count","tox_sum","tox_count",
        ])
        empty_uniq1 = pd.DataFrame(columns=["date","platform","user_id"])
        empty_uniq2 = pd.DataFrame(columns=["date","platform","community","user_id"])
        empty_ut1 = pd.DataFrame(columns=["date","platform","thread_id"])
        empty_ut2 = pd.DataFrame(columns=["date","platform","community","thread_id"])
        return empty_agg1, empty_agg2, empty_uniq1, empty_uniq2, empty_ut1, empty_ut2

    df["_date"] = _safe_to_datetime_utc(df[date_col])
    df = df[df["_date"].notna()]
    if df.empty:
        empty_agg1 = pd.DataFrame(columns=[
            "date","platform","interactions","posts","comments",
            "url_with_value","sentiment_sum","sentiment_count",
            "tb_sum","tb_count","subj_sum","subj_count","tox_sum","tox_count",
        ])
        empty_agg2 = pd.DataFrame(columns=[
            "date","platform","community","interactions","posts","comments",
            "url_with_value","sentiment_sum","sentiment_count",
            "tb_sum","tb_count","subj_sum","subj_count","tox_sum","tox_count",
        ])
        empty_uniq1 = pd.DataFrame(columns=["date","platform","user_id"])
        empty_uniq2 = pd.DataFrame(columns=["date","platform","community","user_id"])
        empty_ut1 = pd.DataFrame(columns=["date","platform","thread_id"])
        empty_ut2 = pd.DataFrame(columns=["date","platform","community","thread_id"])
        return empty_agg1, empty_agg2, empty_uniq1, empty_uniq2, empty_ut1, empty_ut2

    itype = df[interaction_type_col].astype(str).str.lower()
    df["_is_post"] = itype.isin(["post", "submission", "link", "self", "story", "thread"]).astype("int64")
    df["_is_comment"] = itype.isin(["comment", "reply"]).astype("int64")

    df["_has_url"] = _has_url_series(df[url_col]).astype("int64")

    # Sentiment metrics (VADER + TextBlob + Subjectivity + Toxicity)
    sent = _coerce_numeric(df[sentiment_col])
    df["_sentiment_sum"] = sent.fillna(0.0)
    df["_sentiment_count"] = sent.notna().astype("int64")

    tb = _coerce_numeric(df.get('sentiment_textblob'))
    df["_tb_sum"] = tb.fillna(0.0) if tb is not None else 0
    df["_tb_count"] = tb.notna().astype('int64') if tb is not None else 0

    subj = _coerce_numeric(df.get('subjectivity_textblob'))
    df["_subj_sum"] = subj.fillna(0.0) if subj is not None else 0
    df["_subj_count"] = subj.notna().astype('int64') if subj is not None else 0

    tox = _coerce_numeric(df.get('toxicity_toxigen'))
    df["_tox_sum"] = tox.fillna(0.0) if tox is not None else 0
    df["_tox_count"] = tox.notna().astype('int64') if tox is not None else 0

    # Thread identifiers: thread_id = post_id for posts; parent_id for comments
    try:
        df['_thread_id'] = df['post_id']
        df.loc[df['_is_comment'] == 1, '_thread_id'] = df['parent_id']
    except Exception:
        df['_thread_id'] = None

    df["_one"] = 1

    g1 = (
        df.groupby(["_date", platform_col], observed=True, sort=False)
          .agg(
              interactions=("_one", "sum"),
              posts=("_is_post", "sum"),
              comments=("_is_comment", "sum"),
              url_with_value=("_has_url", "sum"),
              sentiment_sum=("_sentiment_sum", "sum"),
              sentiment_count=("_sentiment_count", "sum"),
              tb_sum=("_tb_sum", "sum"),
              tb_count=("_tb_count", "sum"),
              subj_sum=("_subj_sum", "sum"),
              subj_count=("_subj_count", "sum"),
              tox_sum=("_tox_sum", "sum"),
              tox_count=("_tox_count", "sum"),
          )
          .reset_index()
          .rename(columns={"_date": "date", platform_col: "platform"})
    )

    g2 = (
        df.groupby(["_date", platform_col, community_col], observed=True, sort=False)
          .agg(
              interactions=("_one", "sum"),
              posts=("_is_post", "sum"),
              comments=("_is_comment", "sum"),
              url_with_value=("_has_url", "sum"),
              sentiment_sum=("_sentiment_sum", "sum"),
              sentiment_count=("_sentiment_count", "sum"),
              tb_sum=("_tb_sum", "sum"),
              tb_count=("_tb_count", "sum"),
              subj_sum=("_subj_sum", "sum"),
              subj_count=("_subj_count", "sum"),
              tox_sum=("_tox_sum", "sum"),
              tox_count=("_tox_count", "sum"),
          )
          .reset_index()
          .rename(columns={"_date": "date", platform_col: "platform", community_col: "community"})
    )

    if user_col in df.columns:
        uniq1 = (
            df.loc[df[user_col].notna(), ["_date", platform_col, user_col]]
              .drop_duplicates()
              .rename(columns={"_date": "date", platform_col: "platform", user_col: "user_id"})
        )
        uniq2 = (
            df.loc[df[user_col].notna(), ["_date", platform_col, community_col, user_col]]
              .drop_duplicates()
              .rename(columns={"_date": "date", platform_col: "platform", community_col: "community", user_col: "user_id"})
        )
    else:
        uniq1 = pd.DataFrame(columns=["date","platform","user_id"])
        uniq2 = pd.DataFrame(columns=["date","platform","community","user_id"])

    # Unique threads per day
    if '_thread_id' in df.columns:
        ut1 = (
            df.loc[df['_thread_id'].notna(), ["_date", platform_col, '_thread_id']]
              .drop_duplicates()
              .rename(columns={"_date": "date", platform_col: "platform", '_thread_id': 'thread_id'})
        )
        ut2 = (
            df.loc[df['_thread_id'].notna(), ["_date", platform_col, community_col, '_thread_id']]
              .drop_duplicates()
              .rename(columns={"_date": "date", platform_col: "platform", community_col: "community", '_thread_id': 'thread_id'})
        )
    else:
        ut1 = pd.DataFrame(columns=['date','platform','thread_id'])
        ut2 = pd.DataFrame(columns=['date','platform','community','thread_id'])

    return g1, g2, uniq1, uniq2, ut1, ut2




def _sanitize_filename(name):
    s = str(name) if name is not None else 'unknown'
    return ''.join(c if (c.isalnum() or c in ('-','_')) else '_' for c in s)



def _community_from_filename(path: str) -> str:
    """Best-effort parse of community name from dataset filenames like
    'data/reddit_MensRights_madoc.parquet'.
    Returns lowercased community string for logging, or 'unknown'.
    """
    base = os.path.basename(path)
    if not base.endswith('.parquet'):
        return 'unknown'
    stem = base[:-8]
    # Expect pattern: <platform>_<community>_<suffix>
    parts = stem.split('_')
    if len(parts) < 3:
        return 'unknown'
    # Trim first (platform) and last (suffix), rejoin middle for community
    community = '_'.join(parts[1:-1])
    return community or 'unknown'



def _load_key_events(notes_path: str = 'notes/notes.md'):
    """Parse notes/notes.md to extract key event months A–G.
    We match lines that contain target subreddit strings and start with an optional bullet and a date.
    Supports various hyphen/dash separators in dates.
    Returns list of dicts: [{label, month_str, month_dt, desc}] sorted by month.
    """
    import re
    import pandas as pd
    events = {
        'A': '/r/beatingwomen',
        'B': '/r/TheFappening',
        'C': '/r/nigger',
        'D': '/r/fatpeoplehate',
        'E': '/r/pizzagate',
        'F': '/r/incel',
        'G': '/r/GreatAwakening',
    }
    try:
        text = open(notes_path, 'r', encoding='utf-8').read()
    except Exception:
        return []
    # allow ASCII hyphen, non-breaking hyphen, en dash, em dash, minus
    sep = r'[-‑‒–—−]'
    pat = re.compile(rf"^\s*[-*]?\s*(\d{{4}}){sep}(\d{{2}})(?:{sep}(\d{{2}}))?:.*$", re.MULTILINE)
    found = []
    for label, sub in events.items():
        # find first line containing subreddit
        for line in text.splitlines():
            if sub in line:
                m = pat.match(line)
                if m:
                    y, mo = m.group(1), m.group(2)
                    month = f"{y}-{mo}"
                    desc = line.strip()
                    dt = pd.to_datetime(month + '-01', errors='coerce')
                    found.append({'label': label, 'month_str': month, 'month_dt': dt, 'desc': desc})
                    break
    found.sort(key=lambda x: (x['month_dt'] if x['month_dt'] is not None else pd.Timestamp.max))
    return found


def plot_community_panels(output_dir: str, monthly_comm_df, notes_path: str = 'notes/notes.md'):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception as e:
        logging.warning("Skipping figure generation (matplotlib not available): %s", e)
        return
    import os
    import pandas as pd
    figdir = os.path.join(output_dir, 'figures')
    os.makedirs(figdir, exist_ok=True)
    df = monthly_comm_df.copy()
    key_events = _load_key_events(notes_path)
    # Build month datetimes for event lines
    ev_months = [(ev['label'], pd.to_datetime(ev['month_str']+'-01', errors='coerce')) for ev in key_events]
    # Ensure datetime for x-axis
    df['month_dt'] = pd.to_datetime(df['month'], format='%Y-%m', errors='coerce')
    for comm, sub in df.groupby('community', dropna=False):
        if sub['month_dt'].notna().sum() == 0:
            continue
        sub = sub.sort_values('month_dt')
        title_comm = str(comm) if pd.notna(comm) else 'unknown'
        fname = _sanitize_filename(title_comm)
        # Activity summary (3 panels)
        fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
        axes[0].plot(sub['month_dt'], sub['interactions'], label='interactions')
        axes[0].plot(sub['month_dt'], sub['posts'], label='posts')
        axes[0].plot(sub['month_dt'], sub['comments'], label='comments')
        axes[0].set_title(f"{title_comm} — Activity (monthly)")
        axes[0].legend(loc='upper left')

        axes[1].plot(sub['month_dt'], sub['unique_users'], label='unique_users')
        axes[1].plot(sub['month_dt'], sub['active_unique_threads'], label='active_unique_threads')
        axes[1].legend(loc='upper left')
        axes[1].set_ylabel('count')

        axes[2].plot(sub['month_dt'], sub['avg_thread_length'], label='avg_thread_length')
        axes[2].plot(sub['month_dt'], sub['avg_posts_per_user'], label='avg_posts_per_user')
        axes[2].legend(loc='upper left')
        axes[2].set_ylabel('average')
        axes[2].set_xlabel('month')

        # Event lines (A–G)
        for lab, evdt in ev_months:
            if pd.notna(evdt) and sub['month_dt'].min() <= evdt <= sub['month_dt'].max():
                for ax in axes:
                    ax.axvline(evdt, ls='--', lw=1, color='k', alpha=0.5)
                axes[0].text(evdt, axes[0].get_ylim()[1]*0.95, lab, fontsize=9, ha='center', va='top', rotation=0)

        fig.autofmt_xdate()
        plt.tight_layout()
        fig.savefig(os.path.join(figdir, f"{fname}_activity.png"), dpi=150)
        plt.close(fig)

        # Affect summary (3 panels)
        fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
        axes[0].plot(sub['month_dt'], sub['mean_toxicity_toxigen'], color='C3', label='toxicity')
        axes[0].legend(loc='upper left')
        axes[0].set_title(f"{title_comm} — Toxicity, Sentiment, Subjectivity (monthly)")

        axes[1].plot(sub['month_dt'], sub['mean_sentiment_vader'], label='sentiment_vader')
        axes[1].plot(sub['month_dt'], sub['mean_sentiment_textblob'], label='sentiment_textblob')
        axes[1].legend(loc='upper left')

        axes[2].plot(sub['month_dt'], sub['mean_subjectivity_textblob'], label='subjectivity_textblob')
        axes[2].legend(loc='upper left')
        axes[2].set_xlabel('month')

        # Event lines (A–G)
        for lab, evdt in ev_months:
            if pd.notna(evdt) and sub['month_dt'].min() <= evdt <= sub['month_dt'].max():
                for ax in axes:
                    ax.axvline(evdt, ls='--', lw=1, color='k', alpha=0.5)
                axes[0].text(evdt, axes[0].get_ylim()[1]*0.95, lab, fontsize=9, ha='center', va='top', rotation=0)

        fig.autofmt_xdate()
        plt.tight_layout()
        fig.savefig(os.path.join(figdir, f"{fname}_affect.png"), dpi=150)
        plt.close(fig)
def finalize_and_write(agg1_parts, agg2_parts, uniq1_parts, uniq2_parts, uniqt1_parts, uniqt2_parts, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)

    agg1 = pd.concat(agg1_parts, ignore_index=True) if agg1_parts else pd.DataFrame(columns=[
        "date","platform","interactions","posts","comments",
        "url_with_value","sentiment_sum","sentiment_count",
        "tb_sum","tb_count","subj_sum","subj_count","tox_sum","tox_count",
    ])
    agg2 = pd.concat(agg2_parts, ignore_index=True) if agg2_parts else pd.DataFrame(columns=[
        "date","platform","community","interactions","posts","comments",
        "url_with_value","sentiment_sum","sentiment_count",
        "tb_sum","tb_count","subj_sum","subj_count","tox_sum","tox_count",
    ])

    agg1 = agg1.groupby(["date","platform"], as_index=False, observed=True).sum(numeric_only=True)
    agg2 = agg2.groupby(["date","platform","community"], as_index=False, observed=True).sum(numeric_only=True)

    uniq1 = pd.concat(uniq1_parts, ignore_index=True) if uniq1_parts else pd.DataFrame(columns=["date","platform","user_id"])
    uniq2 = pd.concat(uniq2_parts, ignore_index=True) if uniq2_parts else pd.DataFrame(columns=["date","platform","community","user_id"])

    if not uniq1.empty:
        uniq1 = uniq1.drop_duplicates()
        uniq1_counts = uniq1.groupby(["date","platform"], observed=True).size().reset_index(name="unique_users")
        agg1 = agg1.merge(uniq1_counts, on=["date","platform"], how="left")
    else:
        agg1["unique_users"] = 0

    if not uniq2.empty:
        uniq2 = uniq2.drop_duplicates()
        uniq2_counts = uniq2.groupby(["date","platform","community"], observed=True).size().reset_index(name="unique_users")
        agg2 = agg2.merge(uniq2_counts, on=["date","platform","community"], how="left")
    else:
        agg2["unique_users"] = 0

    # Unique threads per day (counts)
    if uniqt1_parts:
        ut1 = pd.concat(uniqt1_parts, ignore_index=True).drop_duplicates()
        ut1_counts = ut1.groupby(['date','platform'], observed=True).size().reset_index(name='active_unique_threads')
        agg1 = agg1.merge(ut1_counts, on=['date','platform'], how='left')
    else:
        agg1['active_unique_threads'] = 0

    if uniqt2_parts:
        ut2 = pd.concat(uniqt2_parts, ignore_index=True).drop_duplicates()
        ut2_counts = ut2.groupby(['date','platform','community'], observed=True).size().reset_index(name='active_unique_threads')
        agg2 = agg2.merge(ut2_counts, on=['date','platform','community'], how='left')
    else:
        agg2['active_unique_threads'] = 0

    # Derived metrics
    for df in (agg1, agg2):
        df["url_pct"] = (df["url_with_value"] / df["interactions"]).where(df["interactions"] > 0, 0.0) * 100.0
        df["mean_sentiment_vader"] = (df["sentiment_sum"] / df["sentiment_count"]).where(df["sentiment_count"] > 0)
        df["mean_sentiment_textblob"] = (df.get('tb_sum', 0) / df.get('tb_count', 0)).where(df.get('tb_count', 0) > 0)
        df["mean_subjectivity_textblob"] = (df.get('subj_sum', 0) / df.get('subj_count', 0)).where(df.get('subj_count', 0) > 0)
        df["mean_toxicity_toxigen"] = (df.get('tox_sum', 0) / df.get('tox_count', 0)).where(df.get('tox_count', 0) > 0)
        df["avg_thread_length"] = (df["interactions"] / df["active_unique_threads"]).where(df["active_unique_threads"] > 0)
        df["avg_posts_per_user"] = (df["posts"] / df["unique_users"]).where(df["unique_users"] > 0)
        # Convert date to YYYY-MM-DD string for CSV
        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce").dt.strftime("%Y-%m-%d")

    # Select and order columns
    out1 = agg1[[
        "date","platform","interactions","posts","comments","unique_users",
        "active_unique_threads","avg_thread_length","avg_posts_per_user",
        "url_pct","mean_sentiment_vader","mean_sentiment_textblob","mean_subjectivity_textblob","mean_toxicity_toxigen",
    ]].sort_values(["date","platform"])\
     .reset_index(drop=True)

    out2 = agg2[[
        "date","platform","community","interactions","posts","comments","unique_users",
        "active_unique_threads","avg_thread_length","avg_posts_per_user",
        "url_pct","mean_sentiment_vader","mean_sentiment_textblob","mean_subjectivity_textblob","mean_toxicity_toxigen",
    ]].sort_values(["date","platform","community"], na_position="last")\
     .reset_index(drop=True)

    results_dir = os.path.join(output_dir, 'results')
    os.makedirs(results_dir, exist_ok=True)
    out_path1 = os.path.join(results_dir, "daily_platform.csv")
    out_path2 = os.path.join(results_dir, "daily_platform_community.csv")

    out1.to_csv(out_path1, index=False)
    out2.to_csv(out_path2, index=False)

    # Monthly aggregates (calendar months)
    agg1_month = agg1.copy()
    agg1_month['month'] = pd.to_datetime(agg1_month['date'], utc=True, errors='coerce').dt.to_period('M')
    m1 = (
        agg1_month.groupby(['month','platform'], as_index=False, observed=True)
            .agg(
                interactions=('interactions','sum'),
                posts=('posts','sum'),
                comments=('comments','sum'),
                url_with_value=('url_with_value','sum'),
                sentiment_sum=('sentiment_sum','sum'),
                sentiment_count=('sentiment_count','sum'),
                tb_sum=('tb_sum','sum'),
                tb_count=('tb_count','sum'),
                subj_sum=('subj_sum','sum'),
                subj_count=('subj_count','sum'),
                tox_sum=('tox_sum','sum'),
                tox_count=('tox_count','sum'),
            )
    )

    if not uniq1.empty:
        u1m = uniq1.copy()
        u1m['month'] = pd.to_datetime(u1m['date'], utc=True, errors='coerce').dt.to_period('M')
        u1m = u1m.dropna(subset=['month']).drop_duplicates(subset=['month','platform','user_id'])
        u1_counts = u1m.groupby(['month','platform'], observed=True).size().reset_index(name='unique_users')
        m1 = m1.merge(u1_counts, on=['month','platform'], how='left')
    else:
        m1['unique_users'] = 0

    if uniqt1_parts:
        ut1m = pd.concat(uniqt1_parts, ignore_index=True).drop_duplicates()
        ut1m['month'] = pd.to_datetime(ut1m['date'], utc=True, errors='coerce').dt.to_period('M')
        ut1m = ut1m.dropna(subset=['month']).drop_duplicates(subset=['month','platform','thread_id'])
        ut1_counts = ut1m.groupby(['month','platform'], observed=True).size().reset_index(name='active_unique_threads')
        m1 = m1.merge(ut1_counts, on=['month','platform'], how='left')
    else:
        m1['active_unique_threads'] = 0

    m1['url_pct'] = (m1['url_with_value'] / m1['interactions']).where(m1['interactions'] > 0, 0.0) * 100.0
    m1['mean_sentiment_vader'] = (m1['sentiment_sum'] / m1['sentiment_count']).where(m1['sentiment_count'] > 0)
    m1['mean_sentiment_textblob'] = (m1.get('tb_sum', 0) / m1.get('tb_count', 0)).where(m1.get('tb_count', 0) > 0)
    m1['mean_subjectivity_textblob'] = (m1.get('subj_sum', 0) / m1.get('subj_count', 0)).where(m1.get('subj_count', 0) > 0)
    m1['mean_toxicity_toxigen'] = (m1.get('tox_sum', 0) / m1.get('tox_count', 0)).where(m1.get('tox_count', 0) > 0)
    m1['avg_thread_length'] = (m1['interactions'] / m1['active_unique_threads']).where(m1['active_unique_threads'] > 0)
    m1['avg_posts_per_user'] = (m1['posts'] / m1['unique_users']).where(m1['unique_users'] > 0)

    m1['month'] = m1['month'].astype(str)
    outm1 = m1[['month','platform','interactions','posts','comments','unique_users','active_unique_threads','avg_thread_length','avg_posts_per_user','url_pct','mean_sentiment_vader','mean_sentiment_textblob','mean_subjectivity_textblob','mean_toxicity_toxigen']].sort_values(['month','platform'])
    out_month1 = os.path.join(results_dir, 'monthly_platform.csv')
    outm1.to_csv(out_month1, index=False)

    agg2_month = agg2.copy()
    agg2_month['month'] = pd.to_datetime(agg2_month['date'], utc=True, errors='coerce').dt.to_period('M')
    m2 = (
        agg2_month.groupby(['month','platform','community'], as_index=False, observed=True)
            .agg(
                interactions=('interactions','sum'),
                posts=('posts','sum'),
                comments=('comments','sum'),
                url_with_value=('url_with_value','sum'),
                sentiment_sum=('sentiment_sum','sum'),
                sentiment_count=('sentiment_count','sum'),
                tb_sum=('tb_sum','sum'),
                tb_count=('tb_count','sum'),
                subj_sum=('subj_sum','sum'),
                subj_count=('subj_count','sum'),
                tox_sum=('tox_sum','sum'),
                tox_count=('tox_count','sum'),
            )
    )

    if not uniq2.empty:
        u2m = uniq2.copy()
        u2m['month'] = pd.to_datetime(u2m['date'], utc=True, errors='coerce').dt.to_period('M')
        u2m = u2m.dropna(subset=['month']).drop_duplicates(subset=['month','platform','community','user_id'])
        u2_counts = u2m.groupby(['month','platform','community'], observed=True).size().reset_index(name='unique_users')
        m2 = m2.merge(u2_counts, on=['month','platform','community'], how='left')
    else:
        m2['unique_users'] = 0

    if uniqt2_parts:
        ut2m = pd.concat(uniqt2_parts, ignore_index=True).drop_duplicates()
        ut2m['month'] = pd.to_datetime(ut2m['date'], utc=True, errors='coerce').dt.to_period('M')
        ut2m = ut2m.dropna(subset=['month']).drop_duplicates(subset=['month','platform','community','thread_id'])
        ut2_counts = ut2m.groupby(['month','platform','community'], observed=True).size().reset_index(name='active_unique_threads')
        m2 = m2.merge(ut2_counts, on=['month','platform','community'], how='left')
    else:
        m2['active_unique_threads'] = 0

    m2['url_pct'] = (m2['url_with_value'] / m2['interactions']).where(m2['interactions'] > 0, 0.0) * 100.0
    m2['mean_sentiment_vader'] = (m2['sentiment_sum'] / m2['sentiment_count']).where(m2['sentiment_count'] > 0)
    m2['mean_sentiment_textblob'] = (m2.get('tb_sum', 0) / m2.get('tb_count', 0)).where(m2.get('tb_count', 0) > 0)
    m2['mean_subjectivity_textblob'] = (m2.get('subj_sum', 0) / m2.get('subj_count', 0)).where(m2.get('subj_count', 0) > 0)
    m2['mean_toxicity_toxigen'] = (m2.get('tox_sum', 0) / m2.get('tox_count', 0)).where(m2.get('tox_count', 0) > 0)
    m2['avg_thread_length'] = (m2['interactions'] / m2['active_unique_threads']).where(m2['active_unique_threads'] > 0)
    m2['avg_posts_per_user'] = (m2['posts'] / m2['unique_users']).where(m2['unique_users'] > 0)

    m2['month'] = m2['month'].astype(str)
    outm2 = m2[['month','platform','community','interactions','posts','comments','unique_users','active_unique_threads','avg_thread_length','avg_posts_per_user','url_pct','mean_sentiment_vader','mean_sentiment_textblob','mean_subjectivity_textblob','mean_toxicity_toxigen']].sort_values(['month','platform','community'], na_position='last')
    out_month2 = os.path.join(results_dir, 'monthly_platform_community.csv')
    outm2.to_csv(out_month2, index=False)

    # Generate per-community panel figures from monthly data
    try:
        plot_community_panels(output_dir, outm2)
    except Exception as e:
        logging.warning('Figure generation failed: %s', e)

    return out_path1, out_path2


def main():
    parser = argparse.ArgumentParser(description="Compute daily and monthly stats/time-series sequentially (one community at a time).")
    parser.add_argument("--input", required=True, help="Parquet directory, file, or glob pattern.")
    parser.add_argument("--output-dir", required=True, help="Directory to write output CSVs.")
    parser.add_argument("--platforms", nargs="+", default=["reddit","voat"], help="Platforms to include (lowercased).")
    parser.add_argument("--log-every", type=int, default=1, help="Log progress every N files (default 1).")
    parser.add_argument("--memory-warning-pct", type=float, default=90.0, help="Warn if memory usage exceeds this percent.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    files = find_parquet_files(args.input)
    if not files:
        logging.error("No Parquet files found for input: %s", args.input)
        sys.exit(2)

    # Sort by parsed community to cluster same-community files
    files = sorted(files, key=_community_from_filename)

    ms = get_memory_status()
    logging.info(
        "Starting sequential processing of %d files. Memory: used %s / total %s (%.1f%%, src=%s)",
        len(files), _bytes_to_human(ms.get("used", 0)), _bytes_to_human(ms.get("total", 0)), ms.get("percent", 0.0), ms.get("source", "?")
    )

    allowed_platforms = set([p.lower() for p in args.platforms])

    agg1_parts, agg2_parts, uniq1_parts, uniq2_parts, uniqt1_parts, uniqt2_parts = [], [], [], [], [], []

    job_args = dict(
        date_col="publish_date",
        platform_col="platform",
        interaction_type_col="interaction_type",
        user_col="user_id",
        url_col="url",
        sentiment_col="sentiment_vader",
        community_col="community",
        allowed_platforms=allowed_platforms,
    )

    total = len(files)
    for i, fpath in enumerate(files, start=1):
        comm = _community_from_filename(fpath)
        ms = get_memory_status()
        logging.info(
            "[%d/%d] Processing community '%s' from file: %s | mem used %s / %s (%.1f%%)",
            i, total, comm, os.path.basename(fpath), _bytes_to_human(ms.get("used", 0)), _bytes_to_human(ms.get("total", 0)), ms.get("percent", 0.0)
        )

        try:
            g1, g2, u1, u2, ut1, ut2 = process_single_file(fpath, **job_args)
        except Exception as e:
            logging.exception("Failed processing %s: %s", fpath, e)
            continue

        if not g1.empty: agg1_parts.append(g1)
        if not g2.empty: agg2_parts.append(g2)
        if not u1.empty: uniq1_parts.append(u1)
        if not u2.empty: uniq2_parts.append(u2)
        if not ut1.empty: uniqt1_parts.append(ut1)
        if not ut2.empty: uniqt2_parts.append(ut2)

        # Proactive memory warning
        ms = get_memory_status()
        if ms.get("percent", 0.0) >= args.memory_warning_pct:
            logging.warning(
                "High memory usage after '%s' (%.1f%%). Consider splitting input.",
                os.path.basename(fpath), ms.get("percent", 0.0)
            )

        # Clear per-file intermediates and run GC
        del g1, g2, u1, u2, ut1, ut2
        gc.collect()

        if i % max(1, args.log_every) == 0:
            logging.info("Progress: %d/%d files complete.", i, total)

    # Derive platform-specific output base: voat/reddit/compare under the provided output-dir
    if len(allowed_platforms) == 1 and list(allowed_platforms)[0] in ('voat','reddit'):
        platform_key = list(allowed_platforms)[0]
    else:
        platform_key = 'compare'
    platform_dir = os.path.join(args.output_dir, platform_key)
    os.makedirs(os.path.join(platform_dir, 'results'), exist_ok=True)
    os.makedirs(os.path.join(platform_dir, 'figures'), exist_ok=True)

    out1, out2 = finalize_and_write(agg1_parts, agg2_parts, uniq1_parts, uniq2_parts, uniqt1_parts, uniqt2_parts, platform_dir)
    logging.info("Wrote: %s", out1)
    logging.info("Wrote: %s", out2)


if __name__ == "__main__":
    main()
