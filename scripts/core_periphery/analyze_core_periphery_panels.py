#!/usr/bin/env python3
import os
# Prevent math/array libs from oversubscribing threads per process
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("BLIS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("ARROW_NUM_THREADS", "1")

import argparse
import logging
from typing import List, Tuple

import pandas as pd
import pyarrow.parquet as pq
from scipy import stats
import numpy as np


def _compute_ci_with_t_dist(
    mean_values: pd.Series,
    std_values: pd.Series,
    member_counts: pd.Series,
    confidence_level: float = 0.95,
) -> pd.DataFrame:
    """Compute confidence intervals using t-distribution for per-user monthly means.

    Returns DataFrame with ci_lower and ci_upper columns.
    For N < 2, returns NaN (insufficient data for variance estimation).
    """
    ci = pd.DataFrame(index=mean_values.index, data={'ci_lower': np.nan, 'ci_upper': np.nan})

    if mean_values.empty or std_values.empty or member_counts.empty:
        return ci

    # Align all series
    aligned = pd.concat({
        'mean': mean_values,
        'std': std_values,
        'count': member_counts
    }, axis=1).dropna(subset=['mean', 'std', 'count'])

    if aligned.empty:
        return ci

    # Only compute CI for N >= 2
    valid = aligned[aligned['count'] >= 2].copy()

    if valid.empty:
        return ci

    # Compute standard error
    valid['se'] = valid['std'] / np.sqrt(valid['count'])

    # Compute t critical value for each sample size (df = N - 1)
    valid['t_crit'] = valid['count'].apply(
        lambda n: stats.t.ppf((1 + confidence_level) / 2, df=n - 1)
    )

    # Compute CI bounds
    half_width = valid['t_crit'] * valid['se']
    ci.loc[valid.index, 'ci_lower'] = (valid['mean'] - half_width).astype(float)
    ci.loc[valid.index, 'ci_upper'] = (valid['mean'] + half_width).astype(float)

    return ci


def _load_key_events(notes_path: str = 'notes/notes.md', three_events_only: bool = True):
    """Parse notes/notes.md to extract key event months.

    When ``three_events_only`` is True (default), only keep the three migration
    events relevant to the panels (fatpeoplehate, pizzagate, GreatAwakening)
    and relabel them A, B, C. Otherwise, include the full seven-event set
    (A–G) from the notes file.

    Returns list of dicts: [{label, month_str, month_dt, desc}] sorted by month.
    """
    import re
    if three_events_only:
        events = {
            'A': '/r/fatpeoplehate',  # D -> A
            'B': '/r/pizzagate',      # E -> B  
            'C': '/r/GreatAwakening', # G -> C
        }
    else:
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
    sep = r'[-‑‒–-−]'
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
                    dt = pd.to_datetime(month + '-01', errors='coerce')
                    found.append({'label': label, 'month_str': month, 'month_dt': dt, 'desc': line.strip()})
                    break
    found.sort(key=lambda x: (x['month_dt'] if x['month_dt'] is not None else pd.Timestamp.max))
    return found


def _event_sort_key(event: dict) -> pd.Timestamp:
    """Helper to sort events by resolved month."""
    dt = event.get('month_dt')
    if pd.isna(dt) and event.get('month_str'):
        dt = pd.to_datetime(event['month_str'] + '-01', errors='coerce')
    if pd.isna(dt):
        return pd.Timestamp.max
    return dt


def _prepare_event_markers(community: str, notes_path: str, three_events_only: bool) -> List[Tuple[str, pd.Timestamp]]:
    """Return sorted (label, month_dt) event markers with gaming extra event."""
    events = list(_load_key_events(notes_path, three_events_only))
    if community.lower() == 'gaming':
        extra_event = None
        for ev in _load_key_events(notes_path, three_events_only=False):
            if ev.get('label') == 'F':
                extra_event = ev.copy()
                break
        if extra_event is None:
            extra_event = {
                'label': '*',
                'month_str': '2017-11',
                'month_dt': pd.to_datetime('2017-11-01', errors='coerce'),
                'desc': '2017-11: Reddit bans /r/incel',
            }
        else:
            # Force the additional gaming event to be labeled with '*'
            extra_event['label'] = '*'
            if pd.isna(extra_event.get('month_dt')) and extra_event.get('month_str'):
                extra_event['month_dt'] = pd.to_datetime(extra_event['month_str'] + '-01', errors='coerce')
        events.append(extra_event)
    markers: List[Tuple[str, pd.Timestamp]] = []
    for ev in sorted(events, key=_event_sort_key):
        dt = ev.get('month_dt')
        if pd.isna(dt) and ev.get('month_str'):
            dt = pd.to_datetime(ev['month_str'] + '-01', errors='coerce')
        markers.append((ev['label'], dt))
    return markers


def _sanitize_filename(name: str) -> str:
    return ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in name)


def find_cp_files(base_dir: str, platform: str) -> List[Tuple[str, str, str]]:
    """Return list of (community, labels_csv, block_stats_csv) for given platform under base_dir.
    Expects files like '<platform>_<community>_cp_labels.csv' and '_cp_block_stats.csv'.
    """
    plat = platform.lower()
    res_dir = os.path.join(base_dir, plat, 'results')
    if not os.path.isdir(res_dir):
        return []
    items = {}
    for fn in os.listdir(res_dir):
        if not fn.startswith(plat + '_'):
            continue
        if fn.endswith('_cp_labels.csv'):
            comm = fn[len(plat) + 1 : -len('_cp_labels.csv')].lower()
            items.setdefault(comm, {})['labels'] = os.path.join(res_dir, fn)
        elif fn.endswith('_cp_block_stats.csv'):
            comm = fn[len(plat) + 1 : -len('_cp_block_stats.csv')].lower()
            items.setdefault(comm, {})['block'] = os.path.join(res_dir, fn)
    out = []
    for comm, d in items.items():
        if 'labels' in d and 'block' in d:
            out.append((comm, d['labels'], d['block']))
    out.sort(key=lambda x: x[0])
    return out


def _read_parquet_for_comm(data_dir: str, platform: str, community: str) -> pd.DataFrame:
    plat = platform.lower()
    comm = community.lower()
    fp = os.path.join(data_dir, f"{plat}_{comm}_madoc.parquet")
    table = pq.read_table(fp, columns=[
        'publish_date', 'user_id', 'interaction_type', 'platform', 'community',
        'sentiment_vader', 'sentiment_textblob', 'subjectivity_textblob', 'toxicity_toxigen',
    ])
    df = table.to_pandas()
    # filter to this platform/community and interaction types
    df['platform'] = df['platform'].astype(str).str.lower()
    df['community'] = df['community'].astype(str).str.lower()
    df['interaction_type'] = df['interaction_type'].astype(str).str.lower()
    df = df[(df['platform'] == plat) & (df['community'] == comm) & (df['interaction_type'].isin(['post','comment']))]
    # derive utc month
    s = pd.to_numeric(df['publish_date'], errors='coerce')
    unit = 'ms' if s.dropna().median() > 1e11 else 's'
    df['_date'] = pd.to_datetime(s, unit=unit, utc=True, errors='coerce')
    df['month'] = df['_date'].dt.strftime('%Y-%m')
    return df


def _read_reputation(results_rep_base: str, platform: str, community: str) -> pd.DataFrame | None:
    # results/reputation/<community>/<platform>/results/<platform>_<community>_user_daily_reputation.parquet
    plat = platform.lower()
    comm = community.lower()
    f1 = os.path.join(results_rep_base, comm, plat, 'results', f"{plat}_{comm}_user_daily_reputation.parquet")
    f2 = os.path.join(results_rep_base, plat, comm, plat, 'results', f"{plat}_{comm}_user_daily_reputation.parquet")
    for fp in (f1, f2):
        if os.path.isfile(fp):
            try:
                table = pq.read_table(fp, columns=['user_id','date','reputation'])
                df = table.to_pandas()
                df['month'] = pd.to_datetime(df['date'], errors='coerce', utc=True).dt.strftime('%Y-%m')
                return df
            except Exception as e:
                logging.warning("Failed to read reputation %s: %s", fp, e)
    return None


def _read_monthly_reputation(reputation_base: str, platform: str, community: str):
    """Read precomputed monthly mean reputation (CSV) for core/periphery.
    Filename: '<platform>_<community>_cp_monthly_reputation.csv'
    """
    import os
    import pandas as pd
    plat = platform.lower()
    comm = community.lower()
    fname = f"{plat}_{comm}_cp_monthly_reputation.csv"
    candidates = [
        os.path.join(reputation_base, comm, plat, 'results', fname),
        os.path.join(reputation_base, plat, comm, plat, 'results', fname),
        os.path.join(reputation_base, plat, 'results', fname),
    ]
    for fp in candidates:
        if os.path.isfile(fp):
            try:
                return pd.read_csv(fp)
            except Exception:
                pass
    return None


def to_long_monthly_rep(rep_monthly):
    # Prefer active-only mean columns if present
    if rep_monthly is not None and {'core_mean_rep_active','periphery_mean_rep_active'}.issubset(rep_monthly.columns):
        return _to_long_monthly_rep_generic(rep_monthly, "core_mean_rep_active", "periphery_mean_rep_active")
    return _to_long_monthly_rep_generic(rep_monthly, "core_mean_rep", "periphery_mean_rep")


def to_long_active_users(rep_monthly):
    """Convert wide monthly active user counts to long format using label 0=core, 1=periphery."""
    import pandas as pd
    if rep_monthly is None or rep_monthly.empty:
        return None
    cols = set(rep_monthly.columns)
    if not {'month'}.issubset(cols):
        return None
    # Determine available active user columns
    if {'core_active_users','periphery_active_users'}.issubset(cols):
        core_col = 'core_active_users'; peri_col = 'periphery_active_users'
    elif {'core_active_daily_avg','periphery_active_daily_avg'}.issubset(cols):
        # fallback to daily averages if totals aren't present
        core_col = 'core_active_daily_avg'; peri_col = 'periphery_active_daily_avg'
    else:
        return None
    df = rep_monthly.copy()
    core = df[['month', core_col]].rename(columns={core_col:'active_users'})
    core['label'] = 0
    peri = df[['month', peri_col]].rename(columns={peri_col:'active_users'})
    peri['label'] = 1
    out = pd.concat([core, peri], ignore_index=True)
    out['month_dt'] = pd.to_datetime(out['month'] + '-01', errors='coerce')
    return out


def _to_long_monthly_rep_generic(rep_monthly, core_col, peri_col):
    """Convert wide monthly reputation to long with label 0(core)/1(periphery).

    Also includes std_rep and member_count if available in the CSV.
    """
    import pandas as pd
    if rep_monthly is None or rep_monthly.empty:
        return None
    df = rep_monthly.copy()
    if not {'month', core_col, peri_col}.issubset(df.columns):
        return None

    # Determine available std and count columns
    core_std_col = core_col.replace('_mean_', '_std_') if '_mean_' in core_col else None
    peri_std_col = peri_col.replace('_mean_', '_std_') if '_mean_' in peri_col else None

    # Use n_core/n_periphery or active user counts as member_count
    has_std = core_std_col and peri_std_col and {core_std_col, peri_std_col}.issubset(df.columns)
    has_n_cols = {'n_core', 'n_periphery'}.issubset(df.columns)
    has_active_cols = {'core_active_users', 'periphery_active_users'}.issubset(df.columns)

    # Build core dataframe
    core_cols = ['month', core_col]
    core_rename = {core_col: 'mean_rep'}
    if has_std and core_std_col in df.columns:
        core_cols.append(core_std_col)
        core_rename[core_std_col] = 'std_rep'
    if has_n_cols:
        core_cols.append('n_core')
        core_rename['n_core'] = 'member_count'
    elif has_active_cols:
        core_cols.append('core_active_users')
        core_rename['core_active_users'] = 'member_count'

    core = df[core_cols].rename(columns=core_rename)
    core['label'] = 0

    # Build periphery dataframe
    peri_cols = ['month', peri_col]
    peri_rename = {peri_col: 'mean_rep'}
    if has_std and peri_std_col in df.columns:
        peri_cols.append(peri_std_col)
        peri_rename[peri_std_col] = 'std_rep'
    if has_n_cols:
        peri_cols.append('n_periphery')
        peri_rename['n_periphery'] = 'member_count'
    elif has_active_cols:
        peri_cols.append('periphery_active_users')
        peri_rename['periphery_active_users'] = 'member_count'

    peri = df[peri_cols].rename(columns=peri_rename)
    peri['label'] = 1

    out = pd.concat([core, peri], ignore_index=True)
    out['month_dt'] = pd.to_datetime(out['month'] + '-01', errors='coerce')
    return out



def compute_group_metrics(labels_df: pd.DataFrame, data_df: pd.DataFrame, rep_df: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Join monthly labels with interactions and compute per (month,label) means.

    Returns (interaction_weighted, per_user_month_means, counts_inter, counts_user, active_users) where:
    - interaction_weighted: mean across all interactions of labeled users in a month.
    - per_user_month_means: per-user monthly mean first, then mean across users per group.
    - active_users: count of users with reputation >=1 per month/label (if rep_df provided)
    """
    # labels_df: columns [community, window, node_id, label]
    lab = labels_df.rename(columns={'window':'month','node_id':'user_id'})[['month','user_id','label']].copy()
    lab['label'] = lab['label'].astype(int)
    # ensure month string in data_df
    df = data_df.copy()
    for col in ['sentiment_vader','sentiment_textblob','subjectivity_textblob','toxicity_toxigen']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    j = df.merge(lab, on=['month','user_id'], how='inner')
    # interaction-weighted
    # counts per month/label
    j["_is_post"] = j["interaction_type"].astype(str).str.lower().eq("post")
    j["_is_comment"] = j["interaction_type"].astype(str).str.lower().eq("comment")
    counts_sum = j.groupby(["month","label"], as_index=False).agg(posts_sum=("_is_post","sum"), comments_sum=("_is_comment","sum"))
    members = labels_df.rename(columns={"window":"month","node_id":"user_id"})[["month","label","user_id"]].drop_duplicates()
    members_sz = members.groupby(["month","label"], as_index=False).agg(members=("user_id","nunique"))
    counts_inter = counts_sum.merge(members_sz, on=["month","label"], how="left")
    counts_inter["avg_posts_per_member"] = counts_inter["posts_sum"]/counts_inter["members"].replace(0, pd.NA)
    counts_inter["avg_comments_per_member"] = counts_inter["comments_sum"]/counts_inter["members"].replace(0, pd.NA)
    g_inter = j.groupby(['month','label'], as_index=False).agg(
        mean_toxicity=('toxicity_toxigen','mean'),
        mean_vader=('sentiment_vader','mean'),
        mean_tb=('sentiment_textblob','mean'),
        mean_subj=('subjectivity_textblob','mean'),
    )
    # per-user monthly mean
    user_month = j.groupby(['month','label','user_id'], as_index=False).agg(
        u_mean_tox=('toxicity_toxigen','mean'),
        u_mean_vader=('sentiment_vader','mean'),
        u_mean_tb=('sentiment_textblob','mean'),
        u_mean_subj=('subjectivity_textblob','mean'),
        u_posts=('_is_post','sum'),
        u_comments=('_is_comment','sum'),
    )
    g_user = user_month.groupby(['month','label'], as_index=False).agg(
        mean_toxicity=('u_mean_tox','mean'),
        std_toxicity=('u_mean_tox','std'),
        mean_vader=('u_mean_vader','mean'),
        std_vader=('u_mean_vader','std'),
        mean_tb=('u_mean_tb','mean'),
        std_tb=('u_mean_tb','std'),
        mean_subj=('u_mean_subj','mean'),
        std_subj=('u_mean_subj','std'),
        member_count=('user_id','nunique'),
    )
    counts_user = user_month.groupby(['month','label'], as_index=False).agg(
        avg_posts_per_member=('u_posts','mean'),
        avg_comments_per_member=('u_comments','mean'),
    )
    
    # Compute active users (reputation >=1) from daily reputation if provided (deprecated in favor of monthly CSV)
    active_users_df = None
    if rep_df is not None and not rep_df.empty:
        active_rep = rep_df[rep_df['reputation'] >= 1].copy()
        active_with_labels = active_rep.merge(lab, on=['month','user_id'], how='inner')
        active_users_df = active_with_labels.groupby(['month','label'], as_index=False).agg(active_users=('user_id','nunique'))
    
    return g_inter, g_user, counts_inter, counts_user, active_users_df


def compute_group_reputation(labels_df: pd.DataFrame, rep_df: pd.DataFrame) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Compute group reputation in two ways:
    - daily_row_mean: mean over all daily rows in month for labeled users (current behavior)
    - per_user_month_mean: average per user-month first, then average across users per label
    Returns (daily_row_mean, per_user_month_mean); either may be None if rep_df is empty.
    """
    if rep_df is None or rep_df.empty:
        return None, None
    lab = labels_df.rename(columns={'window':'month','node_id':'user_id'})[['month','user_id','label']].copy()
    lab['label'] = lab['label'].astype(int)
    r = rep_df[['user_id','month','reputation']].copy()
    j = r.merge(lab, on=['month','user_id'], how='inner')
    # daily-row mean (each daily row contributes equally)
    g_daily = j.groupby(['month','label'], as_index=False).agg(mean_rep=('reputation','mean'))
    # per-user monthly mean
    user_month = j.groupby(['month','label','user_id'], as_index=False).agg(u_mean_rep=('reputation','mean'))
    g_user = user_month.groupby(['month','label'], as_index=False).agg(
        mean_rep=('u_mean_rep','mean'),
        std_rep=('u_mean_rep','std'),
        member_count=('user_id','nunique'),
    )
    return g_daily, g_user


def plot_panels(
    community: str,
    platform: str,
    block_df: pd.DataFrame,
    metrics_inter: pd.DataFrame,
    metrics_user: pd.DataFrame,
    counts_inter: pd.DataFrame,
    counts_user: pd.DataFrame,
    rep_mean_long: pd.DataFrame | None,
    active_users_df: pd.DataFrame | None,
    out_fig_dir: str,
    notes_path: str = 'notes/notes.md',
    three_events_only: bool = True
):
    """Render a single, two-column panel figure per community.

    Changes from previous behavior:
    - Two-column layout instead of two separate tall figures.
    - Core/periphery mean reputation is plotted (no separate median panel).
    - Posts/comments per member panels removed.
    - Core/periphery size is plotted alongside group metrics.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception as e:
        logging.warning("Skipping figure generation (matplotlib not available): %s", e)
        return

    os.makedirs(out_fig_dir, exist_ok=True)
    ev_months = _prepare_event_markers(community, notes_path, three_events_only)

    # Prepare block stats: we will only use sizes here
    bs = block_df.copy()
    bs['month_dt'] = pd.to_datetime(bs['window'] + '-01', errors='coerce')
    bs = bs.sort_values('month_dt')

    # Prepare per-user monthly group metrics (instead of interaction-weighted)
    met_user = metrics_user.copy()
    met_user['month_dt'] = pd.to_datetime(met_user['month'] + '-01', errors='coerce')
    met_user = met_user.sort_values('month_dt')

    # Prepare mean reputation (monthly core/periphery values)
    rep_mean = None
    if rep_mean_long is not None and not rep_mean_long.empty:
        rep_mean = rep_mean_long.copy()
        if 'month_dt' not in rep_mean.columns and 'month' in rep_mean.columns:
            rep_mean['month_dt'] = pd.to_datetime(rep_mean['month'] + '-01', errors='coerce')
        rep_mean = rep_mean.sort_values('month_dt')

    # Build list of panel plotting functions and titles
    panels = []  # list of (name, plot_fn)

    # 1) Core/periphery size panel (from block stats)
    def _plot_sizes(ax):
        ax.plot(bs['month_dt'], pd.to_numeric(bs['ns_core'], errors='coerce'), label='core size')
        ax.plot(bs['month_dt'], pd.to_numeric(bs['ns_peri'], errors='coerce'), label='periphery size')
        ax.set_title(f"{community} - Core/Periphery size")
        ax.legend(loc='upper left')
    panels.append(("sizes", _plot_sizes))

    # 2) Mean reputation (monthly) if available
    if rep_mean is not None:
        def _plot_rep_mean(ax):
            # In monthly reputation long format, label 0=core, 1=periphery
            core = rep_mean[rep_mean['label'] == 0].copy()
            peri = rep_mean[rep_mean['label'] == 1].copy()

            # Plot lines
            ax.plot(core['month_dt'], core['mean_rep'], label='core (mean)', color='C0')
            ax.plot(peri['month_dt'], peri['mean_rep'], label='periphery (mean)', color='C1')

            # Add CI bands if std and member_count are available
            if {'std_rep', 'member_count'}.issubset(core.columns):
                core_ci = _compute_ci_with_t_dist(core['mean_rep'], core['std_rep'], core['member_count'])
                mask = core_ci['ci_lower'].notna() & core_ci['ci_upper'].notna()
                if mask.any():
                    ax.fill_between(
                        core.loc[mask, 'month_dt'],
                        core_ci.loc[mask, 'ci_lower'],
                        core_ci.loc[mask, 'ci_upper'],
                        color='C0', alpha=0.15, linewidth=0
                    )

            if {'std_rep', 'member_count'}.issubset(peri.columns):
                peri_ci = _compute_ci_with_t_dist(peri['mean_rep'], peri['std_rep'], peri['member_count'])
                mask = peri_ci['ci_lower'].notna() & peri_ci['ci_upper'].notna()
                if mask.any():
                    ax.fill_between(
                        peri.loc[mask, 'month_dt'],
                        peri_ci.loc[mask, 'ci_lower'],
                        peri_ci.loc[mask, 'ci_upper'],
                        color='C1', alpha=0.15, linewidth=0
                    )

            ax.set_title(f"{community} - Mean reputation (monthly)")
            ax.legend(loc='upper left')
            # No y-limit constraint for reputation (range varies by platform)
        panels.append(("rep_mean", _plot_rep_mean))

    # 3) Toxicity (per-user monthly means)
    def _plot_toxicity(ax):
        core = met_user[met_user['label'] == 0].copy()
        peri = met_user[met_user['label'] == 1].copy()

        # Plot lines
        ax.plot(core['month_dt'], core['mean_toxicity'], label='core', color='C0')
        ax.plot(peri['month_dt'], peri['mean_toxicity'], label='periphery', color='C1')

        # Add CI bands if std and member_count are available
        if {'std_toxicity', 'member_count'}.issubset(core.columns):
            core_ci = _compute_ci_with_t_dist(core['mean_toxicity'], core['std_toxicity'], core['member_count'])
            mask = core_ci['ci_lower'].notna() & core_ci['ci_upper'].notna()
            if mask.any():
                ax.fill_between(
                    core.loc[mask, 'month_dt'],
                    core_ci.loc[mask, 'ci_lower'],
                    core_ci.loc[mask, 'ci_upper'],
                    color='C0', alpha=0.15, linewidth=0
                )

        if {'std_toxicity', 'member_count'}.issubset(peri.columns):
            peri_ci = _compute_ci_with_t_dist(peri['mean_toxicity'], peri['std_toxicity'], peri['member_count'])
            mask = peri_ci['ci_lower'].notna() & peri_ci['ci_upper'].notna()
            if mask.any():
                ax.fill_between(
                    peri.loc[mask, 'month_dt'],
                    peri_ci.loc[mask, 'ci_lower'],
                    peri_ci.loc[mask, 'ci_upper'],
                    color='C1', alpha=0.15, linewidth=0
                )

        ax.set_title(f"{community} - Mean toxicity (per user/month)")
        ax.legend(loc='upper left')
        ax.set_ylim(0.0, 1.0)
    panels.append(("toxicity", _plot_toxicity))

    # 4) Sentiment VADER (per-user monthly means)
    def _plot_vader(ax):
        core = met_user[met_user['label'] == 0].copy()
        peri = met_user[met_user['label'] == 1].copy()

        # Plot lines
        ax.plot(core['month_dt'], core['mean_vader'], label='core', color='C0')
        ax.plot(peri['month_dt'], peri['mean_vader'], label='periphery', color='C1')

        # Add CI bands if std and member_count are available
        if {'std_vader', 'member_count'}.issubset(core.columns):
            core_ci = _compute_ci_with_t_dist(core['mean_vader'], core['std_vader'], core['member_count'])
            mask = core_ci['ci_lower'].notna() & core_ci['ci_upper'].notna()
            if mask.any():
                ax.fill_between(
                    core.loc[mask, 'month_dt'],
                    core_ci.loc[mask, 'ci_lower'],
                    core_ci.loc[mask, 'ci_upper'],
                    color='C0', alpha=0.15, linewidth=0
                )

        if {'std_vader', 'member_count'}.issubset(peri.columns):
            peri_ci = _compute_ci_with_t_dist(peri['mean_vader'], peri['std_vader'], peri['member_count'])
            mask = peri_ci['ci_lower'].notna() & peri_ci['ci_upper'].notna()
            if mask.any():
                ax.fill_between(
                    peri.loc[mask, 'month_dt'],
                    peri_ci.loc[mask, 'ci_lower'],
                    peri_ci.loc[mask, 'ci_upper'],
                    color='C1', alpha=0.15, linewidth=0
                )

        ax.set_title(f"{community} - Sentiment VADER (per user/month)")
        ax.legend(loc='upper left')
        ax.set_ylim(-1.0, 1.0)
    panels.append(("vader", _plot_vader))

    # 5) Sentiment TextBlob (per-user monthly means)
    def _plot_tb(ax):
        core = met_user[met_user['label'] == 0].copy()
        peri = met_user[met_user['label'] == 1].copy()

        # Plot lines
        ax.plot(core['month_dt'], core['mean_tb'], label='core', color='C0')
        ax.plot(peri['month_dt'], peri['mean_tb'], label='periphery', color='C1')

        # Add CI bands if std and member_count are available
        if {'std_tb', 'member_count'}.issubset(core.columns):
            core_ci = _compute_ci_with_t_dist(core['mean_tb'], core['std_tb'], core['member_count'])
            mask = core_ci['ci_lower'].notna() & core_ci['ci_upper'].notna()
            if mask.any():
                ax.fill_between(
                    core.loc[mask, 'month_dt'],
                    core_ci.loc[mask, 'ci_lower'],
                    core_ci.loc[mask, 'ci_upper'],
                    color='C0', alpha=0.15, linewidth=0
                )

        if {'std_tb', 'member_count'}.issubset(peri.columns):
            peri_ci = _compute_ci_with_t_dist(peri['mean_tb'], peri['std_tb'], peri['member_count'])
            mask = peri_ci['ci_lower'].notna() & peri_ci['ci_upper'].notna()
            if mask.any():
                ax.fill_between(
                    peri.loc[mask, 'month_dt'],
                    peri_ci.loc[mask, 'ci_lower'],
                    peri_ci.loc[mask, 'ci_upper'],
                    color='C1', alpha=0.15, linewidth=0
                )

        ax.set_title(f"{community} - Sentiment TextBlob (per user/month)")
        ax.legend(loc='upper left')
        ax.set_ylim(-1.0, 1.0)
    panels.append(("tb", _plot_tb))

    # 6) Subjectivity (per-user monthly means)
    def _plot_subj(ax):
        core = met_user[met_user['label'] == 0].copy()
        peri = met_user[met_user['label'] == 1].copy()

        # Plot lines
        ax.plot(core['month_dt'], core['mean_subj'], label='core', color='C0')
        ax.plot(peri['month_dt'], peri['mean_subj'], label='periphery', color='C1')

        # Add CI bands if std and member_count are available
        if {'std_subj', 'member_count'}.issubset(core.columns):
            core_ci = _compute_ci_with_t_dist(core['mean_subj'], core['std_subj'], core['member_count'])
            mask = core_ci['ci_lower'].notna() & core_ci['ci_upper'].notna()
            if mask.any():
                ax.fill_between(
                    core.loc[mask, 'month_dt'],
                    core_ci.loc[mask, 'ci_lower'],
                    core_ci.loc[mask, 'ci_upper'],
                    color='C0', alpha=0.15, linewidth=0
                )

        if {'std_subj', 'member_count'}.issubset(peri.columns):
            peri_ci = _compute_ci_with_t_dist(peri['mean_subj'], peri['std_subj'], peri['member_count'])
            mask = peri_ci['ci_lower'].notna() & peri_ci['ci_upper'].notna()
            if mask.any():
                ax.fill_between(
                    peri.loc[mask, 'month_dt'],
                    peri_ci.loc[mask, 'ci_lower'],
                    peri_ci.loc[mask, 'ci_upper'],
                    color='C1', alpha=0.15, linewidth=0
                )

        ax.set_title(f"{community} - Subjectivity (per user/month)")
        ax.legend(loc='upper left')
        ax.set_ylim(0.0, 1.0)
    panels.append(("subj", _plot_subj))

    # Determine grid: two columns
    n = len(panels)
    ncols = 2
    nrows = (n + ncols - 1) // ncols
    # width: 12 works well for two columns; height ~3 per row
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, max(3*nrows, 4)), sharex=True)
    if nrows == 1:
        axes = axes.reshape(1, -1)
    axes_flat = axes.ravel().tolist()

    # Plot panels into grid slots
    for i, (_, plot_fn) in enumerate(panels):
        ax = axes_flat[i]
        plot_fn(ax)
        # Event lines
        for lab, evdt in ev_months:
            if pd.notna(evdt):
                # Use available x-limits from any data series; fall back to bs if needed
                try:
                    xmin, xmax = ax.get_lines()[0].get_xdata().min(), ax.get_lines()[0].get_xdata().max()
                except Exception:
                    xmin = bs['month_dt'].min() if bs['month_dt'].notna().any() else None
                    xmax = bs['month_dt'].max() if bs['month_dt'].notna().any() else None
                if xmin is not None and xmax is not None and xmin <= evdt <= xmax:
                    ax.axvline(evdt, ls='--', lw=1, color='k', alpha=0.5)
                    ax.text(
                        evdt,
                        0.95,
                        lab,
                        transform=ax.get_xaxis_transform(),
                        fontsize=8,
                        ha='center',
                        va='top'
                    )

    # Hide any unused axes (in case of odd number of panels)
    for j in range(n, nrows*ncols):
        axes_flat[j].axis('off')

    # Label x-axis on bottom row
    for c in range(ncols):
        axes[nrows-1, c].set_xlabel('month')

    fig.autofmt_xdate()
    plt.tight_layout()
    fname = os.path.join(out_fig_dir, f"{platform}_{_sanitize_filename(community)}_cp_panels_2col.png")
    fig.savefig(fname, dpi=150)
    plt.close(fig)


def write_summary(community: str, platform: str, block_df: pd.DataFrame, metrics_df: pd.DataFrame, rep_df: pd.DataFrame | None, out_results_dir: str):
    os.makedirs(out_results_dir, exist_ok=True)
    lines = []
    bs = block_df.copy()
    bs['month_dt'] = pd.to_datetime(bs['window'] + '-01', errors='coerce')
    bs = bs.sort_values('month_dt')
    if bs['month_dt'].notna().any():
        start = str(bs['month_dt'].min().date())
        end = str(bs['month_dt'].max().date())
        lines.append(f"community: {community}\nplatform: {platform}\nmonths: {start} to {end}\n")
    lines.append(f"avg core size: {pd.to_numeric(bs['ns_core'], errors='coerce').mean():.2f}")
    lines.append(f"avg periphery size: {pd.to_numeric(bs['ns_peri'], errors='coerce').mean():.2f}")
    lines.append(f"avg core density p_cc: {pd.to_numeric(bs['p_cc'], errors='coerce').mean():.4f}")
    lines.append(f"avg core-periphery density p_cp: {pd.to_numeric(bs['p_cp'], errors='coerce').mean():.4f}")

    met = metrics_df.copy()
    # Labels: 0 = core, 1 = periphery
    core = met[met['label'] == 0]
    peri = met[met['label'] == 1]
    if not core.empty and not peri.empty:
        lines.append("")
        lines.append("Group metrics (per-user monthly means across months with data):")
        lines.append(f"toxicity: core {core['mean_toxicity'].mean():.4f}, peri {peri['mean_toxicity'].mean():.4f}")
        lines.append(f"vader: core {core['mean_vader'].mean():.4f}, peri {peri['mean_vader'].mean():.4f}")
        lines.append(f"textblob: core {core['mean_tb'].mean():.4f}, peri {peri['mean_tb'].mean():.4f}")
        lines.append(f"subjectivity: core {core['mean_subj'].mean():.4f}, peri {peri['mean_subj'].mean():.4f}")

    if rep_df is not None and not rep_df.empty:
        repc = rep_df[rep_df['label'] == 0]
        repp = rep_df[rep_df['label'] == 1]
        if not repc.empty and not repp.empty:
            lines.append(f"reputation: core {repc['mean_rep'].mean():.4f}, peri {repp['mean_rep'].mean():.4f}")

    out_path = os.path.join(out_results_dir, f"{platform}_{_sanitize_filename(community)}_cp_analysis_summary.txt")
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
def plot_structure_panel(community: str, platform: str, block_df: pd.DataFrame, out_fig_dir: str, notes_path: str = 'notes/notes.md', three_events_only: bool = True):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return
    os.makedirs(out_fig_dir, exist_ok=True)
    ev_months = _prepare_event_markers(community, notes_path, three_events_only)
    bs = block_df.copy()
    bs['month_dt'] = pd.to_datetime(bs['window'] + '-01', errors='coerce')
    bs = bs.sort_values('month_dt')
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    axes[0].plot(bs['month_dt'], pd.to_numeric(bs['ns_core'], errors='coerce'), label='core size')
    axes[0].plot(bs['month_dt'], pd.to_numeric(bs['ns_peri'], errors='coerce'), label='periphery size')
    axes[0].legend(loc='upper left')
    axes[0].set_title(f"{community} - Core/Periphery size & densities")
    axes[1].plot(bs['month_dt'], pd.to_numeric(bs['p_cc'], errors='coerce'), color='C2', label='core density p_cc')
    axes[1].legend(loc='upper left')
    axes[1].set_ylabel('density')
    axes[2].plot(bs['month_dt'], pd.to_numeric(bs['p_cp'], errors='coerce'), color='C4', label='core-periphery density p_cp')
    axes[2].legend(loc='upper left')
    axes[2].set_xlabel('month')
    for lab, evdt in ev_months:
        if pd.notna(evdt) and bs['month_dt'].notna().any():
            if bs['month_dt'].min() <= evdt <= bs['month_dt'].max():
                for ax in axes:
                    ax.axvline(evdt, ls='--', lw=1, color='k', alpha=0.5)
                axes[0].text(evdt, axes[0].get_ylim()[1]*0.95, lab, fontsize=9, ha='center', va='top')
    fig.autofmt_xdate()
    plt.tight_layout()
    fname1 = os.path.join(out_fig_dir, f"{platform}_{_sanitize_filename(community)}_cp_panel_structure.png")
    fig.savefig(fname1, dpi=150)
    plt.close(fig)

def main():
    ap = argparse.ArgumentParser(description="Produce core-periphery panels and summaries per community.")
    ap.add_argument('--platform', choices=['voat','reddit'], default='voat')
    ap.add_argument('--cp-output-dir', default=os.path.join('results','core-periphery'), help='Base dir where cp results live (category root)')
    ap.add_argument('--data-dir', default='data', help='Base dir with Parquet datasets')
    ap.add_argument('--reputation-dir', default=os.path.join('results','reputation'), help='Base dir with precomputed reputation outputs')
    ap.add_argument('--communities', nargs='*', help='Specific communities to process (default: all with cp files)')
    ap.add_argument('--all-events', dest='three_events_only', action='store_false', help='Plot all annotated events instead of the default three migration events')
    ap.add_argument('--three-events-only', dest='three_events_only', action='store_true', default=True, help='Limit to the three migration events (default)')
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    cp_items = find_cp_files(args.cp_output_dir, args.platform)
    if not cp_items:
        logging.error('No core-periphery files found under %s/%s/results', args.cp_output_dir, args.platform)
        return

    # Filter communities if provided
    if args.communities:
        wanted = set([c.lower() for c in args.communities])
        cp_items = [(c,l,b) for (c,l,b) in cp_items if c.lower() in wanted]
        if not cp_items:
            logging.error('None of the requested communities have cp files: %s', ','.join(wanted))
            return

    fig_dir = os.path.join(args.cp_output_dir, args.platform, 'figures')
    res_dir = os.path.join(args.cp_output_dir, args.platform, 'results')
    os.makedirs(fig_dir, exist_ok=True)
    os.makedirs(res_dir, exist_ok=True)

    for community, labels_csv, block_csv in cp_items:
        logging.info('Processing %s/%s', args.platform, community)
        # Remove only this script's figures for this community (narrow patterns)
        try:
            comm_safe = _sanitize_filename(community)
            to_remove = [
                f"{args.platform}_{comm_safe}_cp_panel_structure.png",
                f"{args.platform}_{comm_safe}_cp_panel_group_metrics.png",
                f"{args.platform}_{comm_safe}_cp_panels_2col.png",
            ]
            for fn in to_remove:
                fp = os.path.join(fig_dir, fn)
                if os.path.isfile(fp):
                    os.remove(fp)
        except Exception:
            pass
        try:
            labels = pd.read_csv(labels_csv)
            block = pd.read_csv(block_csv)
        except Exception as e:
            logging.warning('Skipping %s: failed to read CSVs: %s', community, e)
            continue
        
        # Read data and reputation
        try:
            data_df = _read_parquet_for_comm(args.data_dir, args.platform, community)
        except Exception as e:
            logging.warning('Skipping %s: failed to read data: %s', community, e)
            continue
        
        # Compute metrics from interactions; do not read daily reputation here
        metrics_inter, metrics_user, counts_inter, counts_user, _ = compute_group_metrics(labels, data_df, rep_df=None)

        # Read monthly reputation data and derive active users from monthly CSV
        rep_month = _read_monthly_reputation(args.reputation_dir, args.platform, community)
        rep_mean_long = to_long_monthly_rep(rep_month)
        active_users_df = to_long_active_users(rep_month)

        # Generate the single two-column panel figure
        plot_panels(
            community,
            args.platform,
            block,
            metrics_inter,
            metrics_user,
            counts_inter,
            counts_user,
            rep_mean_long,
            active_users_df,
            fig_dir,
            three_events_only=args.three_events_only
        )


if __name__ == '__main__':
    main()
