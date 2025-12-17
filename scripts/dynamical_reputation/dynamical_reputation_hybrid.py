#!/usr/bin/env python3
"""
Hybrid DuckDB + Parallel Processing for Dynamical Reputation

This combines:
- DuckDB's efficient I/O and streaming (single process, memory-controlled)
- Parallel user-batch processing via ProcessPoolExecutor (15 workers)

Memory budget: ~55GB (45% of 125GB)
- DuckDB process: 10GB
- Worker pool: 15 workers × ~3GB = 45GB

CPU usage: 15 workers (31% of 48 cores)
"""

import argparse
import csv
import gc
import math
import os
import sys
import time
from collections import defaultdict
from glob import glob
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from concurrent.futures import ProcessPoolExecutor, as_completed, wait, FIRST_COMPLETED

import duckdb
import numpy as np
import pandas as pd
import psutil
import pyarrow as pa
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.dynamical_reputation import dynamical_reputation_inline as inline


# --- Reputation core (reused from duckdb version) ---------------------------

def _sec_to_datetime(ts: int) -> pd.Timestamp:
    return pd.to_datetime(int(ts), unit="s")


def _normalize_decay_flag(flag) -> bool:
    if isinstance(flag, str):
        return flag.lower() == "true"
    return bool(flag)


def update_reputation_inactive(
    R,
    inactive_date,
    last_activity_date,
    last_activity_day,
    last_day,
    beta=0.999,
    decay_per_day=True,
):
    decay_flag = _normalize_decay_flag(decay_per_day)
    dt = (inactive_date - last_activity_date) / np.timedelta64(1, "D")
    if decay_flag:
        D = R[last_day] * np.power(beta, dt)
    else:
        D = R[last_activity_day] * np.power(beta, dt)
    R[last_day + 1] = D


def update_reputation(
    R,
    A,
    curr_date,
    last_activity_date,
    last_day,
    last_activity_day,
    curr_day,
    beta=0.999,
    Ib=1,
    alpha=2,
    decay_per_day=True,
):
    decay_flag = _normalize_decay_flag(decay_per_day)
    dt = (curr_date - last_activity_date) / np.timedelta64(1, "D")
    In = Ib + Ib * alpha * (1.0 - 1.0 / (A + 1))
    if (not decay_flag) and (A == 1):
        D = R[last_activity_day] * np.power(beta, dt)
    else:
        D = R[last_day] * np.power(beta, dt)
    y = R.get(curr_day, 0.0)
    y = In + D
    R[curr_day] = y


def _compute_user_ru(
    user_id: str,
    times: Sequence[int],
    base_ts: pd.Timestamp,
    day_max: int,
    beta: float,
    Ib: float,
    alpha: float,
    decay_per_day: bool,
):
    if not times:
        return []

    # Optimization: Avoid concatenating if it's a list of arrays
    if isinstance(times, list) and len(times) > 0 and isinstance(times[0], np.ndarray):
        times_array = np.concatenate(times)
    else:
        times_array = np.asarray(times, dtype=np.int64)

    if times_array.size > 1 and np.any(times_array[1:] < times_array[:-1]):
        times_array = np.sort(times_array, kind="mergesort")

    # Optimization: Use integer arithmetic instead of pandas datetime conversion
    # timestamps = pd.to_datetime(times_array, unit="s")
    # day_offsets = ((timestamps - base_ts) / np.timedelta64(1, "D")).astype(int)
    
    base_ts_sec = int(base_ts.timestamp())
    day_offsets = (times_array - base_ts_sec) // 86400
    
    # Reconstruct timestamps only when needed (for first_date)
    # But we only need first_date for last_activity_date logic.
    # actually last_activity_date is a Timestamp.
    # Let's keep using Timestamps for the logic but avoid creating the huge Index.
    
    # We need to map index to timestamp for the loop
    # timestamps array is needed?
    # The loop uses: curr_activity_date = pd.Timestamp(timestamps[idx])
    # This is slow if we do it for every item.
    # But creating the whole Index is memory heavy.
    # We can create timestamps on the fly.
    
    Ru: dict[int, float] = {}
    first_day = int(day_offsets[0])
    # first_date = pd.Timestamp(timestamps[0]) 
    first_date = base_ts + pd.to_timedelta(times_array[0], unit="s") - pd.to_timedelta(base_ts_sec, unit="s")
    # Wait, base_ts is Timestamp. 
    # first_date = pd.to_datetime(times_array[0], unit="s")
    first_date = pd.Timestamp(times_array[0], unit="s")

    A = 1
    Ru[first_day] = Ib + Ib * alpha * (1.0 - 1.0 / (A + 1))
    last_day = int(first_day)
    last_activity_date = first_date
    last_activity_day = int(first_day)
    decay_flag = _normalize_decay_flag(decay_per_day)

    for idx in range(1, len(times_array)):
        curr_day = int(day_offsets[idx])
        # curr_activity_date = pd.Timestamp(timestamps[idx])
        curr_activity_date = pd.Timestamp(times_array[idx], unit="s")
        if curr_day > (last_day + 1):
            gaps = curr_day - last_day - 1
            if gaps > 0:
                for _ in range(gaps):
                    inactive_date = base_ts + pd.to_timedelta(int(last_day) + 2, unit="D")
                    update_reputation_inactive(
                        Ru,
                        inactive_date,
                        last_activity_date,
                        last_activity_day,
                        last_day,
                        beta=beta,
                        decay_per_day=decay_flag,
                    )
                    last_day += 1
                    A = 0
        A += 1
        update_reputation(
            Ru,
            A,
            curr_activity_date,
            last_activity_date,
            last_day,
            last_activity_day,
            curr_day,
            beta=beta,
            Ib=Ib,
            alpha=alpha,
            decay_per_day=decay_flag,
        )
        last_activity_date = curr_activity_date
        last_activity_day = curr_day
        last_day = curr_day

    rest_days = int(day_max - last_day)
    if rest_days > 0:
        for _ in range(rest_days):
            inactive_date = base_ts + pd.to_timedelta(int(last_day) + 2, unit="D")
            update_reputation_inactive(
                Ru,
                inactive_date,
                last_activity_date,
                last_activity_day,
                last_day,
                beta=beta,
                decay_per_day=decay_flag,
            )
            last_day += 1

    rows = [
        (str(user_id), int(day), float(val))
        for day, val in Ru.items()
        if int(day) >= first_day
    ]
    return rows


# --- Batch processing worker function ---------------------------------------

def process_user_batch(
    batch_data: Tuple[List[Tuple[str, List[np.ndarray]]], pd.Timestamp, int, float, float, float, bool]
) -> List[Tuple[str, int, float]]:
    """
    Process a batch of users in parallel.

    Args:
        batch_data: Tuple of (user_list, base_ts, day_max, beta, Ib, alpha, decay_per_day)
            where user_list is [(user_id, [times]), ...]

    Returns:
        List of (user_id, day, reputation) tuples for all users in batch
    """
    user_list, base_ts, day_max, beta, Ib, alpha, decay_per_day = batch_data

    all_rows = []
    for user_id, times in user_list:
        rows = _compute_user_ru(user_id, times, base_ts, day_max, beta, Ib, alpha, decay_per_day)
        all_rows.extend(rows)

    return all_rows


# --- Utilities ---------------------------------------------------------------

def extract_community_from_filename(filepath: str) -> str:
    basename = os.path.basename(filepath)
    name = basename.replace("reddit_", "").replace("voat_", "")
    name = name.replace("_madoc.parquet", "").replace(".parquet", "")
    return name


def build_output_paths(base_output: str, community: str | None, platform: str | None) -> Tuple[str, str]:
    comm = community.lower() if community else "global"
    plat = platform.lower() if platform else "compare"
    root = os.path.join(base_output, comm, plat)
    results_dir = os.path.join(root, "results")
    figures_dir = os.path.join(root, "figures")
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)
    return results_dir, figures_dir


def default_filename(community: str | None, platform: str | None, fmt: str) -> str:
    comm = (community or "global").lower()
    plat_prefix = f"{(platform or 'compare').lower()}_"
    base = f"{plat_prefix}{comm}_user_daily_reputation"
    return f"{base}.{fmt}"


class BaseWriter:
    def write_rows(self, rows: Iterable[Tuple[str, int, float, int, int, pd.Timestamp]]) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class CsvWriter(BaseWriter):
    def __init__(self, path: str):
        self._fh = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(["user_id", "day", "reputation", "t_min", "t_max", "date"])

    def write_rows(self, rows: Iterable[Tuple[str, int, float, int, int, pd.Timestamp]]) -> None:
        iterable = list(rows)
        if not iterable:
            return
        formatted = [
            (user, day, rep, tmin, tmax, date.isoformat())
            for user, day, rep, tmin, tmax, date in iterable
        ]
        self._writer.writerows(formatted)

    def close(self) -> None:
        self._fh.close()


class ParquetWriter(BaseWriter):
    def __init__(self, path: str):
        self._schema = pa.schema(
            [
                ("user_id", pa.string()),
                ("day", pa.int64()),
                ("reputation", pa.float64()),
                ("t_min", pa.int64()),
                ("t_max", pa.int64()),
                ("date", pa.timestamp("ns")),
            ]
        )
        self._writer = pq.ParquetWriter(path, self._schema)

    def write_rows(self, rows: Iterable[Tuple[str, int, float, int, int, pd.Timestamp]]) -> None:
        iterable = list(rows)
        if not iterable:
            return
        columns = list(zip(*iterable))
        arrays = []
        for field, col in zip(self._schema, columns):
            if field.name == "date":
                arrays.append(pa.array([pd.Timestamp(x) for x in col], type=field.type))
            else:
                arrays.append(pa.array(col, type=field.type))
        table = pa.Table.from_arrays(arrays, schema=self._schema)
        self._writer.write_table(table)

    def close(self) -> None:
        self._writer.close()


def get_memory_info() -> str:
    rss_gb = psutil.Process().memory_info().rss / (1024 ** 3)
    return f"{rss_gb:.2f}GB"


def sanitize_literal(value: str) -> str:
    return value.replace("'", "''")


def detect_epoch_is_ms(rel: duckdb.DuckDBPyRelation) -> bool:
    sample = rel.project("publish_date AS ts").limit(1000).fetchdf()
    if sample.empty:
        return False
    try:
        median = sample["ts"].astype("float64").median()
    except Exception:
        return False
    return bool(median and median > 1e11)


def fetch_time_bounds(rel: duckdb.DuckDBPyRelation, ms_epoch: bool) -> Tuple[int, int]:
    tmin_raw, tmax_raw = rel.aggregate("min(publish_date), max(publish_date)").fetchone()
    if tmin_raw is None or tmax_raw is None:
        raise ValueError("Unable to determine publish_date bounds")
    if ms_epoch:
        return int(tmin_raw // 1000), int(tmax_raw // 1000)
    return int(tmin_raw), int(tmax_raw)


def create_writer(path: str, fmt: str) -> BaseWriter:
    if fmt == "csv":
        return CsvWriter(path)
    if fmt == "parquet":
        return ParquetWriter(path)
    raise ValueError(f"Unsupported format: {fmt}")


def rows_with_metadata(rows: List[Tuple[str, int, float]], tmin: int, tmax: int) -> List[Tuple[str, int, float, int, int, pd.Timestamp]]:
    if not rows:
        return []
    base = _sec_to_datetime(tmin)
    return [
        (user, day, rep, tmin, tmax, base + pd.to_timedelta(day, unit="D"))
        for user, day, rep in rows
    ]


def count_rows(filepath: str, args) -> int:
    con = duckdb.connect(database=":memory:")
    try:
        rel = load_relation(con, filepath, args)
        count_val = rel.aggregate("count(*)").fetchone()[0]
        return int(count_val or 0)
    finally:
        con.close()


def load_relation(con: duckdb.DuckDBPyConnection, filepath: str, args) -> duckdb.DuckDBPyRelation:
    rel = con.read_parquet(filepath, union_by_name=True)
    rel = rel.filter("publish_date IS NOT NULL AND user_id IS NOT NULL")
    rel = rel.filter("lower(interaction_type) IN ('post','comment')")
    if args.platform:
        rel = rel.filter(f"lower(platform) = '{sanitize_literal(args.platform.lower())}'")
    if args.community:
        rel = rel.filter(f"lower(community) = '{sanitize_literal(args.community.lower())}'")
    return rel


# --- Hybrid streaming + parallel processing ---------------------------------

def process_file_hybrid(filepath: str, args) -> dict:
    """
    Hybrid approach:
    1. Use DuckDB to stream sorted data (user_id, publish_ts)
    2. Collect users into batches of N users
    3. Process batches in parallel with ProcessPoolExecutor
    4. Stream results to output as they complete
    """
    community = args.community or extract_community_from_filename(filepath)
    filesize = os.path.getsize(filepath) / (1024 ** 3)

    print(f"\n{'=' * 60}")
    print(f"Community: {community} ({filesize:.2f}GB)")
    print(f"File: {filepath}")
    print(f"Engine: hybrid (DuckDB streaming + parallel processing)")
    print(f"Workers: {args.workers}")
    print(f"Batch size: {args.batch_users} users")
    print(f"Memory before: {get_memory_info()}")

    start = time.time()

    # Setup DuckDB connection with conservative memory limit
    con = duckdb.connect(database=":memory:")
    if args.duckdb_threads:
        con.execute(f"PRAGMA threads={int(args.duckdb_threads)}")
    con.execute(f"PRAGMA memory_limit='{args.duckdb_memory_limit}'")
    if args.duckdb_temp_dir:
        con.execute(f"PRAGMA temp_directory='{sanitize_literal(args.duckdb_temp_dir)}'")

    # Load and prepare data
    rel = load_relation(con, filepath, args)
    epoch_ms = detect_epoch_is_ms(rel)
    tmin, tmax = fetch_time_bounds(rel, epoch_ms)

    print(f"publish_date unit: {'ms' if epoch_ms else 's'}")
    print(f"Time range: {_sec_to_datetime(tmin)} -> {_sec_to_datetime(tmax)}")

    # Stream sorted data from DuckDB
    rel.create_view("_filtered_source", replace=True)
    ts_expr = "CAST(floor(publish_date / 1000) AS BIGINT)" if epoch_ms else "CAST(publish_date AS BIGINT)"
    query = f"""
        SELECT CAST(user_id AS VARCHAR) AS user_id,
               {ts_expr} AS publish_ts
        FROM _filtered_source
        ORDER BY 1, 2
    """
    relation = con.sql(query)

    # Setup output writer
    results_dir, _ = build_output_paths(args.output_dir, community, args.platform)
    fname = default_filename(community, args.platform, args.output_format)
    output_path = os.path.join(results_dir, fname)
    writer = create_writer(output_path, args.output_format)

    # Setup parallel processing
    base_ts = _sec_to_datetime(tmin)
    day_max = max((_sec_to_datetime(tmax) - base_ts).days, 0)
    decay_flag = _normalize_decay_flag(args.decay_per_day)

    # Counters
    rows_total = 0
    users_total = 0
    events_total = 0
    batches_submitted = 0
    batches_completed = 0

    # Stream data and collect    # Stream and batch users
    current_user = None
    buffer_times: List[np.ndarray] = []
    user_batch: List[Tuple[str, List[np.ndarray]]] = []

    proc = psutil.Process()

    try:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {}

            # Use arrow iterator for efficient streaming
            if hasattr(relation, "fetch_arrow_reader"):
                reader = relation.fetch_arrow_reader(batch_size=args.chunk_rows)

                def next_batch():
                    try:
                        batch = reader.read_next_batch()
                        if batch is None:
                            return None
                        if hasattr(batch, "num_rows") and batch.num_rows == 0:
                            return next_batch()
                        return batch
                    except StopIteration:
                        return None
            elif hasattr(relation, "arrow_iterator"):
                arrow_iter = relation.arrow_iterator(batch_size=args.chunk_rows)

                def next_batch():
                    try:
                        batch = next(arrow_iter)
                        if hasattr(batch, "num_rows") and batch.num_rows == 0:
                            return next_batch()
                        return batch
                    except StopIteration:
                        return None
            else:
                # Fallback
                def next_batch():
                    batch = relation.fetch_record_batch(args.chunk_rows)
                    if batch is None or (hasattr(batch, "num_rows") and batch.num_rows == 0):
                        return None
                    return batch

            # Stream and batch users
            while True:
                batch = next_batch()
                if batch is None:
                    break

                batch_size = batch.num_rows
                events_total += batch_size

                # Extract user_ids and timestamps
                # Extract user_ids and timestamps
                # Use run_end_encode for efficient grouping
                encoded_users = pc.run_end_encode(batch.column(0))
                run_ends = encoded_users.run_ends.to_numpy(zero_copy_only=False)
                values = encoded_users.values
                
                # Timestamps array for the whole batch
                times_array = batch.column(1).to_numpy(zero_copy_only=False)
                
                start_idx = 0
                for value_index in range(len(values)):
                    uid = values[value_index].as_py()
                    end_idx = int(run_ends[value_index])
                    
                    if current_user is None:
                        current_user = uid
                    
                    if uid != current_user:
                        # Finished current user, add to batch
                        user_batch.append((current_user, buffer_times))
                        users_total += 1
                        buffer_times = []
                        current_user = uid
                        
                        # Submit batch if full
                        if len(user_batch) >= args.batch_users:
                            # CRITICAL: Limit concurrent futures to prevent memory explosion
                            # Wait if we have too many in-flight batches
                            max_concurrent = args.workers * 2  # 2x workers = 30 concurrent batches
                            while len(futures) >= max_concurrent:
                                # Block and wait for at least one to complete
                                done_set, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)
                                for done in done_set:
                                    batch_id = futures.pop(done)
                                    rows = done.result()
                                    writer.write_rows(rows_with_metadata(rows, tmin, tmax))
                                    rows_total += len(rows)
                                    batches_completed += 1
                                    del rows
                                    
                                    if batches_completed % 10 == 0:
                                        rss = proc.memory_info().rss / (1024 ** 3)
                                        print(
                                            f"  batches: {batches_completed}/{batches_submitted} | "
                                            f"users={users_total:,} events={events_total:,} rows={rows_total:,} rss={rss:.2f}GB"
                                        )
                                        if args.max_memory_gb is not None and rss > args.max_memory_gb:
                                            raise MemoryError(
                                                f"RSS {rss:.2f}GB exceeded limit {args.max_memory_gb:.2f}GB"
                                            )
                                gc.collect()
                            
                            batch_data = (
                                user_batch.copy(),
                                base_ts,
                                day_max,
                                args.beta,
                                args.Ib,
                                args.alpha,
                                decay_flag,
                            )
                            future = executor.submit(process_user_batch, batch_data)
                            futures[future] = batches_submitted
                            batches_submitted += 1
                            user_batch = []
                    
                    if end_idx > start_idx:
                        segment = times_array[start_idx:end_idx]
                        if segment.size:
                            # Append numpy array segment directly
                            buffer_times.append(segment)
                    start_idx = end_idx

                # Process completed futures (non-blocking check)
                done_futures = [f for f in futures if f.done()]
                for future in done_futures:
                    batch_id = futures.pop(future)
                    rows = future.result()
                    writer.write_rows(rows_with_metadata(rows, tmin, tmax))
                    rows_total += len(rows)
                    batches_completed += 1
                    del rows

                    if batches_completed % 10 == 0:
                        rss = proc.memory_info().rss / (1024 ** 3)
                        print(
                            f"  batches: {batches_completed}/{batches_submitted} | "
                            f"users={users_total:,} events={events_total:,} rows={rows_total:,} rss={rss:.2f}GB"
                        )
                        if args.max_memory_gb is not None and rss > args.max_memory_gb:
                            raise MemoryError(
                                f"RSS {rss:.2f}GB exceeded limit {args.max_memory_gb:.2f}GB"
                            )

                gc.collect()

            # Handle last user
            if current_user is not None and buffer_times:
                user_batch.append((current_user, buffer_times))
                users_total += 1

            # Submit final partial batch
            if user_batch:
                batch_data = (
                    user_batch,
                    base_ts,
                    day_max,
                    args.beta,
                    args.Ib,
                    args.alpha,
                    decay_flag,
                )
                future = executor.submit(process_user_batch, batch_data)
                futures[future] = batches_submitted
                batches_submitted += 1

            # Wait for all remaining futures
            for future in as_completed(futures):
                batch_id = futures[future]
                rows = future.result()
                writer.write_rows(rows_with_metadata(rows, tmin, tmax))
                rows_total += len(rows)
                batches_completed += 1

    finally:
        writer.close()
        con.close()

    elapsed = time.time() - start

    print(
        f"✓ Finished {community}: events={events_total:,}, rows={rows_total:,}, users={users_total:,}"
    )
    print(f"  Output: {output_path}")
    print(f"  Time: {elapsed:.1f}s | Memory after: {get_memory_info()}")

    gc.collect()

    return {
        "community": community,
        "rows": rows_total,
        "users": users_total,
        "events": events_total,
        "output": output_path,
        "elapsed": elapsed,
        "engine": "hybrid",
    }


# --- CLI ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Hybrid DuckDB streaming + parallel batch processing for dynamical reputation.",
    )
    p.add_argument("--input", "-i", required=True, help="Parquet file pattern (e.g., data/reddit_*.parquet)")
    p.add_argument("--platform", choices=["reddit", "voat"], help="Optional platform filter")
    p.add_argument("--community", help="Optional community filter")
    p.add_argument("--output-dir", default=os.path.join("results", "reputation"))
    p.add_argument("--output-format", choices=["csv", "parquet"], default="csv")

    # Hybrid-specific parameters
    p.add_argument("--workers", type=int, default=15, help="Number of parallel workers for batch processing (default: 15)")
    p.add_argument("--batch-users", type=int, default=500, help="Number of users per batch (default: 500)")
    p.add_argument("--chunk-rows", type=int, default=500_000, help="Arrow batch size for DuckDB streaming (default: 500k)")

    # Memory and resource limits
    p.add_argument("--max-memory-gb", type=float, help="Abort if RSS exceeds this many GB (default: 45%% of total RAM)")
    p.add_argument("--duckdb-threads", type=int, help="PRAGMA threads override for DuckDB")
    p.add_argument("--duckdb-memory-limit", default="10GB", help="DuckDB memory_limit (default: 10GB)")
    p.add_argument("--duckdb-temp-dir", help="Directory for DuckDB temp files")

    # Algorithm parameters
    p.add_argument("--beta", type=float, default=0.96)
    p.add_argument("--alpha", type=float, default=2.0)
    p.add_argument("--Ib", type=float, default=1.0)
    p.add_argument("--decay-per-day", action="store_true", help="Apply decay for each inactive day")

    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.chunk_rows <= 0:
        raise ValueError("--chunk-rows must be positive")
    if args.workers <= 0:
        raise ValueError("--workers must be positive")
    if args.batch_users <= 0:
        raise ValueError("--batch-users must be positive")

    files = sorted(glob(args.input))
    if not files:
        raise FileNotFoundError(f"No files matched pattern: {args.input}")
    files = sorted(files, key=lambda f: os.path.getsize(f))

    # Auto-set memory guard to 45% of total RAM
    if args.max_memory_gb is None:
        total_gb = psutil.virtual_memory().total / (1024 ** 3)
        args.max_memory_gb = max(total_gb * 0.45, 1.0)
        guard_display = f"{args.max_memory_gb:.2f} GB (auto 45% of RAM)"
    elif args.max_memory_gb <= 0:
        args.max_memory_gb = None
        guard_display = "disabled"
    else:
        guard_display = f"{args.max_memory_gb:.2f} GB"

    print("=" * 60)
    print("Hybrid DuckDB + Parallel Dynamical Reputation")
    print("=" * 60)
    print(f"Files: {len(files)} | Platform: {args.platform or 'all'}")
    print(f"Workers: {args.workers} | Batch size: {args.batch_users} users")
    print(f"DuckDB memory: {args.duckdb_memory_limit} | Chunk rows: {args.chunk_rows:,}")
    print(f"Memory guard: {guard_display}")
    print(f"Output format: {args.output_format}")

    summary = []
    for idx, filepath in enumerate(files, start=1):
        row_count = count_rows(filepath, args)
        base_name = os.path.basename(filepath)
        print(f"\n[{idx}/{len(files)}] {base_name} | rows={row_count:,}")

        info = process_file_hybrid(filepath, args)
        info["row_count"] = row_count
        summary.append(info)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for item in summary:
        print(
            f"{item['community']}: events={item['events']:,}, rows={item['rows']:,}, "
            f"users={item['users']:,}, time={item['elapsed']:.1f}s"
        )
        print(f"  Output: {item['output']}")


if __name__ == "__main__":
    main()
