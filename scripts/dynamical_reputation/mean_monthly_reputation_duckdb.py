#!/usr/bin/env python3
"""Stream monthly core/periphery reputation aggregates with DuckDB.

This companion script avoids loading massive per-user reputation dumps into pandas.
It reads the daily reputation Parquet/CSV with DuckDB, joins monthly core/periphery
labels, and emits the same monthly CSV schema expected by downstream panel plots.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
from typing import Optional, Tuple

import duckdb
import pandas as pd

MIN_SAFE_DUCKDB_BYTES = 512 * 1024 * 1024  # 512MB
DEFAULT_MEM_FRACTION = 0.5
MAX_MEM_FRACTION = 0.8
MIN_RECOMMENDED_AVAILABLE = 2 * 1024 * 1024 * 1024  # 2GB
DEFAULT_MEMORY_FALLBACK = "8GB"


def _find_case_insensitive(res_dir: str, filename: str) -> str:
    """Return the path to filename ignoring case, or raise FileNotFoundError."""
    lower_target = filename.lower()
    for candidate in os.listdir(res_dir):
        if candidate.lower() == lower_target:
            return os.path.join(res_dir, candidate)
    raise FileNotFoundError(f"{filename} not found in {res_dir}")


def _read_cp_files(cp_base_dir: str, platform: str, community: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    plat = platform.lower()
    comm = community.lower()
    res_dir = os.path.join(cp_base_dir, plat, "results")
    labels_name = f"{plat}_{comm}_cp_labels.csv"
    block_name = f"{plat}_{comm}_cp_block_stats.csv"
    labels_fp = _find_case_insensitive(res_dir, labels_name)
    block_fp = _find_case_insensitive(res_dir, block_name)
    if not os.path.isfile(labels_fp):
        raise FileNotFoundError(f"CP labels not found: {labels_fp}")
    if not os.path.isfile(block_fp):
        raise FileNotFoundError(f"CP block stats not found: {block_fp}")
    labels = pd.read_csv(labels_fp)
    blocks = pd.read_csv(block_fp)
    need_lab = {"community", "window", "node_id", "label"}
    miss_lab = [c for c in need_lab if c not in labels.columns]
    if miss_lab:
        raise ValueError(f"CP labels missing columns {miss_lab}; got {list(labels.columns)}")
    need_blk = {"community", "window", "ns_core", "ns_peri"}
    miss_blk = [c for c in need_blk if c not in blocks.columns]
    if miss_blk:
        raise ValueError(f"CP block stats missing columns {miss_blk}; got {list(blocks.columns)}")
    return labels, blocks


def _resolve_reputation_file(
    reputation_base: str,
    platform: str,
    community: str,
    explicit_file: Optional[str],
) -> Tuple[str, str]:
    candidates: list[str] = []
    if explicit_file:
        candidates.append(explicit_file)
    plat = platform.lower()
    comm = community.lower()
    candidates.extend(
        [
            os.path.join(reputation_base, comm, plat, "results", f"{plat}_{comm}_user_daily_reputation.parquet"),
            os.path.join(reputation_base, comm, plat, "results", f"{plat}_{comm}_user_daily_reputation.csv"),
            os.path.join(reputation_base, plat, comm, plat, "results", f"{plat}_{comm}_user_daily_reputation.parquet"),
            os.path.join(reputation_base, plat, comm, plat, "results", f"{plat}_{comm}_user_daily_reputation.csv"),
            os.path.join(reputation_base, plat, "results", f"{plat}_{comm}_user_daily_reputation.parquet"),
            os.path.join(reputation_base, plat, "results", f"{plat}_{comm}_user_daily_reputation.csv"),
        ]
    )
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        lower = path.lower()
        if lower.endswith(".parquet") or lower.endswith(".parquet.gz"):
            return path, "parquet"
        if lower.endswith(".csv") or lower.endswith(".csv.gz"):
            return path, "csv"
    raise FileNotFoundError(
        "Could not locate reputation file in expected locations; pass --reputation-file explicitly"
    )


def _escape_literal(value: str) -> str:
    return value.replace("'", "''")


def _available_memory_bytes() -> Optional[int]:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) * 1024
    except FileNotFoundError:
        return None
    return None


def _human_readable_bytes(num: int) -> str:
    if num <= 0:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = min(int(math.log(num, 1024)), len(units) - 1) if num else 0
    if idx == 0:
        return f"{int(num)}B"
    value = num / (1024 ** idx)
    return f"{value:.1f}{units[idx]}"


def _parse_size(spec: Optional[str]) -> Optional[int]:
    if not spec:
        return None
    text = spec.strip().lower()
    if not text:
        return None
    units = {
        "kb": 1024,
        "k": 1024,
        "mb": 1024 ** 2,
        "m": 1024 ** 2,
        "gb": 1024 ** 3,
        "g": 1024 ** 3,
        "tb": 1024 ** 4,
        "t": 1024 ** 4,
        "b": 1,
    }
    for suffix in sorted(units, key=len, reverse=True):
        if text.endswith(suffix):
            number = text[: -len(suffix)] or "0"
            try:
                value = float(number)
            except ValueError:
                return None
            return max(int(value * units[suffix]), 0)
    try:
        value = float(text)
    except ValueError:
        return None
    return max(int(value), 0)


def _format_duckdb_limit(bytes_value: int) -> str:
    mb = max(1, math.ceil(bytes_value / (1024 * 1024)))
    return f"{mb}MB"


def _select_memory_limit(
    user_limit: Optional[str],
    available_bytes: Optional[int],
) -> Tuple[int, str]:
    user_bytes = _parse_size(user_limit)
    if user_limit and user_bytes is None:
        logging.warning("Invalid DuckDB memory limit '%s'; falling back to automatic selection.", user_limit)
    if available_bytes is None:
        base_bytes = user_bytes or _parse_size(DEFAULT_MEMORY_FALLBACK) or MIN_SAFE_DUCKDB_BYTES
        base_bytes = max(base_bytes, MIN_SAFE_DUCKDB_BYTES)
        return base_bytes, _format_duckdb_limit(base_bytes)
    safe_bytes = max(int(available_bytes * DEFAULT_MEM_FRACTION), MIN_SAFE_DUCKDB_BYTES)
    max_bytes = max(int(available_bytes * MAX_MEM_FRACTION), MIN_SAFE_DUCKDB_BYTES)
    limit_bytes = safe_bytes if user_bytes is None else user_bytes
    if limit_bytes > max_bytes:
        logging.warning(
            "Requested DuckDB memory %s exceeds %.0f%% of available (%s); clamping.",
            _format_duckdb_limit(limit_bytes),
            MAX_MEM_FRACTION * 100,
            _human_readable_bytes(available_bytes),
        )
        limit_bytes = max_bytes
    if limit_bytes < MIN_SAFE_DUCKDB_BYTES:
        logging.info(
            "Raising DuckDB memory limit to %s to stay above minimum.",
            _format_duckdb_limit(MIN_SAFE_DUCKDB_BYTES),
        )
        limit_bytes = MIN_SAFE_DUCKDB_BYTES
    return limit_bytes, _format_duckdb_limit(limit_bytes)


def _configure_duckdb(
    con: duckdb.DuckDBPyConnection,
    memory_limit: str,
    threads: Optional[int],
    temp_dir: Optional[str],
) -> None:
    if threads:
        con.execute(f"PRAGMA threads={int(threads)}")
    con.execute(f"PRAGMA memory_limit='{memory_limit}'")
    if temp_dir:
        os.makedirs(temp_dir, exist_ok=True)
        con.execute(f"PRAGMA temp_directory='{_escape_literal(temp_dir)}'")


def _register_small_tables(
    con: duckdb.DuckDBPyConnection,
    labels_df: pd.DataFrame,
    blocks_df: pd.DataFrame,
) -> None:
    lab = labels_df.rename(columns={"window": "month", "node_id": "user_id"}).copy()
    lab["month"] = lab["month"].astype(str).str.strip()
    lab["user_id"] = lab["user_id"].astype(str).str.strip()
    lab["label"] = pd.to_numeric(lab["label"], errors="coerce")
    lab = lab[lab["label"].isin([0, 1])]
    if lab.empty:
        raise ValueError("No usable core/periphery labels after filtering")
    lab["label"] = lab["label"].astype(int)
    con.register("labels_input", lab[["month", "user_id", "label"]])
    con.execute("CREATE TEMP TABLE labels AS SELECT month, user_id, label FROM labels_input")

    blk = blocks_df.copy()
    month_col = "month" if "month" in blk.columns else "window"
    if month_col not in blk.columns:
        raise ValueError("Block stats missing 'month' or 'window' column")
    blk["month"] = blk[month_col].astype(str).str.strip()
    blk["ns_core"] = pd.to_numeric(blk["ns_core"], errors="coerce")
    blk["ns_peri"] = pd.to_numeric(blk["ns_peri"], errors="coerce")
    con.register("blocks_input", blk[["month", "ns_core", "ns_peri"]])
    con.execute("CREATE TEMP TABLE blocks AS SELECT month, ns_core, ns_peri FROM blocks_input")


def _build_timestamp_expression(columns: set[str]) -> str:
    exprs: list[str] = []
    if "date" in columns:
        exprs.append("try_cast(date AS TIMESTAMP)")
    if "t_min" in columns:
        base = (
            "TIMESTAMP '1970-01-01' + "
            "((try_cast(t_min AS DOUBLE) / CASE WHEN t_min > 100000000000 THEN 1000 ELSE 1 END) * INTERVAL '1 second')"
        )
        if "day" in columns:
            base = f"{base} + coalesce(try_cast(day AS DOUBLE), 0) * INTERVAL '1 day'"
        exprs.append(base)
    if not exprs:
        raise ValueError("Reputation file missing usable timestamp hints (expected 'date' or 't_min').")
    return "COALESCE(" + ", ".join(exprs) + ")"


def compute_monthly_means_duckdb(
    labels_df: pd.DataFrame,
    blocks_df: pd.DataFrame,
    reputation_path: str,
    reputation_format: str,
    memory_limit: str,
    temp_dir: Optional[str],
    threads: Optional[int],
) -> pd.DataFrame:
    con = duckdb.connect(database=":memory:")
    try:
        _configure_duckdb(con, memory_limit, threads, temp_dir)
        _register_small_tables(con, labels_df, blocks_df)

        escaped = _escape_literal(reputation_path)
        if reputation_format == "parquet":
            con.execute(
                f"CREATE TEMP VIEW rep_source AS "
                f"SELECT * FROM read_parquet('{escaped}', union_by_name=True)"
            )
        elif reputation_format == "csv":
            con.execute(
                f"CREATE TEMP VIEW rep_source AS "
                f"SELECT * FROM read_csv_auto('{escaped}', header=True)"
            )
        else:
            raise ValueError(f"Unsupported reputation format: {reputation_format}")

        cols = {c.lower() for c in con.sql("SELECT * FROM rep_source LIMIT 0").columns}
        required = {"user_id", "reputation"}
        missing = required - cols
        if missing:
            raise ValueError(f"Reputation file missing required columns: {', '.join(sorted(missing))}")
        ts_expr = _build_timestamp_expression(cols)

        con.execute(
            f"""
            CREATE TEMP VIEW rep_prepared AS
            WITH base AS (
                SELECT
                    CAST(user_id AS VARCHAR) AS user_id,
                    TRY_CAST(reputation AS DOUBLE) AS reputation,
                    {ts_expr} AS ts
                FROM rep_source
            )
            SELECT
                user_id,
                reputation,
                DATE_TRUNC('day', ts) AS date,
                STRFTIME('%Y-%m', ts) AS month
            FROM base
            WHERE reputation IS NOT NULL AND ts IS NOT NULL
            """
        )

        con.execute(
            """
            CREATE TEMP VIEW rep_joined AS
            SELECT
                r.month,
                l.label,
                r.user_id,
                r.date,
                r.reputation
            FROM rep_prepared r
            JOIN labels l
              ON l.month = r.month AND l.user_id = r.user_id
            WHERE r.reputation >= 1
            """
        )

        query = """
WITH daily AS (
    SELECT
        month,
        date,
        label,
        SUM(reputation) AS sum_rep,
        COUNT(DISTINCT user_id) AS active_users
    FROM rep_joined
    GROUP BY 1,2,3
),
daily_means AS (
    SELECT
        month,
        label,
        AVG(sum_rep / NULLIF(active_users, 0)) AS mean_rep_active,
        AVG(active_users) AS active_daily_avg
    FROM daily
    WHERE active_users > 0
    GROUP BY 1,2
),
user_month AS (
    SELECT
        month,
        label,
        user_id,
        AVG(reputation) AS user_mean_rep
    FROM rep_joined
    GROUP BY 1,2,3
),
user_median AS (
    SELECT
        month,
        label,
        median(user_mean_rep) AS median_rep_active
    FROM user_month
    GROUP BY 1,2
),
monthly_active AS (
    SELECT
        month,
        label,
        COUNT(DISTINCT user_id) AS active_users
    FROM rep_joined
    GROUP BY 1,2
)
SELECT
    b.month,
    dm_core.mean_rep_active AS core_mean_rep_active,
    dm_peri.mean_rep_active AS periphery_mean_rep_active,
    med_core.median_rep_active AS core_median_rep_active,
    med_peri.median_rep_active AS periphery_median_rep_active,
    dm_core.active_daily_avg AS core_active_daily_avg,
    dm_peri.active_daily_avg AS periphery_active_daily_avg,
    ma_core.active_users AS core_active_users,
    ma_peri.active_users AS periphery_active_users,
    CAST(b.ns_core AS BIGINT) AS n_core,
    CAST(b.ns_peri AS BIGINT) AS n_periphery
FROM blocks b
LEFT JOIN daily_means dm_core ON dm_core.month = b.month AND dm_core.label = 0
LEFT JOIN daily_means dm_peri ON dm_peri.month = b.month AND dm_peri.label = 1
LEFT JOIN user_median med_core ON med_core.month = b.month AND med_core.label = 0
LEFT JOIN user_median med_peri ON med_peri.month = b.month AND med_peri.label = 1
LEFT JOIN monthly_active ma_core ON ma_core.month = b.month AND ma_core.label = 0
LEFT JOIN monthly_active ma_peri ON ma_peri.month = b.month AND ma_peri.label = 1
ORDER BY b.month
"""
        return con.sql(query).df()
    finally:
        con.close()


def decide_output_path(
    base_out: str,
    platform: str,
    community: str,
    rep_source_path: Optional[str] = None,
) -> str:
    plat = platform.lower()
    comm = community.lower()
    fname = f"{plat}_{comm}_cp_monthly_reputation.csv"
    if rep_source_path:
        directory = os.path.dirname(rep_source_path)
        for _ in range(5):
            if os.path.basename(directory) == "results":
                os.makedirs(directory, exist_ok=True)
                return os.path.join(directory, fname)
            parent = os.path.dirname(directory)
            if not parent or parent == directory:
                break
            directory = parent
    results_dir = os.path.join(base_out, plat, "results")
    os.makedirs(results_dir, exist_ok=True)
    return os.path.join(results_dir, fname)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--platform", required=True, choices=["voat", "reddit"], help="Platform")
    ap.add_argument("--community", required=True, help="Community name (subreddit/subverse)")
    ap.add_argument("--cp-dir", default=os.path.join("results", "core-periphery"), help="Core-periphery results base directory")
    ap.add_argument("--reputation-dir", default=os.path.join("results", "reputation"), help="Base directory for precomputed reputation outputs")
    ap.add_argument("--reputation-file", help="Explicit path to per-user daily reputation CSV/Parquet (optional)")
    ap.add_argument("--output-dir", default=os.path.join("results", "reputation"), help="Base output directory (category root)")
    ap.add_argument("--duckdb-memory-limit", help="Override DuckDB memory_limit (e.g., 12GB or 2048MB)")
    ap.add_argument("--duckdb-threads", type=int, help="Optional PRAGMA threads value for DuckDB")
    ap.add_argument("--duckdb-temp-dir", default=os.path.join("tmp", "duckdb_spill"), help="Directory for DuckDB temp files when spilling")
    ap.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    labels_df, blocks_df = _read_cp_files(args.cp_dir, args.platform, args.community)
    rep_path, rep_format = _resolve_reputation_file(
        args.reputation_dir,
        args.platform,
        args.community,
        explicit_file=args.reputation_file,
    )

    filesize = os.path.getsize(rep_path)
    logging.info("Reputation source: %s (%s)", rep_path, _human_readable_bytes(filesize))

    avail_bytes = _available_memory_bytes()
    if avail_bytes is None:
        logging.info("MemAvailable: unknown (falling back to default DuckDB limit)")
    else:
        logging.info("MemAvailable: %s", _human_readable_bytes(avail_bytes))
        if avail_bytes < MIN_RECOMMENDED_AVAILABLE:
            logging.warning(
                "Only %s of memory available; expect DuckDB to spill to disk.",
                _human_readable_bytes(avail_bytes),
            )

    limit_bytes, limit_str = _select_memory_limit(args.duckdb_memory_limit, avail_bytes)
    logging.info("DuckDB memory limit: %s (%s)", limit_str, _human_readable_bytes(limit_bytes))

    temp_dir = args.duckdb_temp_dir or None
    out_df = compute_monthly_means_duckdb(
        labels_df,
        blocks_df,
        rep_path,
        rep_format,
        limit_str,
        temp_dir,
        args.duckdb_threads,
    )

    out_path = decide_output_path(
        args.output_dir,
        args.platform,
        args.community,
        rep_source_path=rep_path if args.reputation_file else None,
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_df.to_csv(out_path, index=False)

    logging.info("Wrote %s (%d rows)", out_path, len(out_df))


if __name__ == "__main__":
    main()
