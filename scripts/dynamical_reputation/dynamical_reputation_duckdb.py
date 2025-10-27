import argparse
import csv
import datetime
import gc
import math
import os
import sys
import time
from glob import glob
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from concurrent.futures import ProcessPoolExecutor, as_completed

import duckdb
import numpy as np
import pandas as pd
import psutil
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.dynamical_reputation import dynamical_reputation_inline as inline


# --- Reputation core -----------------------------------------------------

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

    times_array = np.asarray(times, dtype=np.int64)
    if times_array.size > 1 and np.any(times_array[1:] < times_array[:-1]):
        times_array = np.sort(times_array, kind="mergesort")

    timestamps = pd.to_datetime(times_array, unit="s")
    day_offsets = ((timestamps - base_ts) / np.timedelta64(1, "D")).astype(int)

    Ru: dict[int, float] = {}
    first_day = int(day_offsets[0])
    first_date = pd.Timestamp(timestamps[0])
    A = 1
    Ru[first_day] = Ib + Ib * alpha * (1.0 - 1.0 / (A + 1))
    last_day = int(first_day)
    last_activity_date = first_date
    last_activity_day = int(first_day)
    decay_flag = _normalize_decay_flag(decay_per_day)

    for idx in range(1, len(timestamps)):
        curr_day = int(day_offsets[idx])
        curr_activity_date = pd.Timestamp(timestamps[idx])
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


# --- Utilities -----------------------------------------------------------

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


def default_filename(community: str | None, platform: str | None, fmt: str, partition_id: int | None = None, partitions: int | None = None) -> str:
    comm = (community or "global").lower()
    plat_prefix = f"{(platform or 'compare').lower()}_"
    base = f"{plat_prefix}{comm}_user_daily_reputation"
    if partition_id is not None and partitions and partitions > 1:
        width = max(len(str(partitions - 1)), 2)
        base += f"_part{partition_id:0{width}d}of{partitions:0{width}d}"
    return f"{base}.{fmt}"


def clone_args(args: argparse.Namespace, **updates) -> argparse.Namespace:
    data = vars(args).copy()
    data.update(updates)
    return argparse.Namespace(**data)


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


def decide_engine(args, row_count: int | None) -> str:
    if args.engine != "auto":
        return args.engine
    if args.partition_id is not None:
        return "duckdb"
    if args.partitions > 1 or args.auto_partitions:
        return "duckdb"
    if row_count is not None and row_count <= args.inline_row_threshold:
        return "pandas"
    return "duckdb"


def decide_partitions(args, row_count: int | None, engine: str) -> int:
    if engine == "pandas":
        return 1
    if args.partition_id is not None:
        return max(1, args.partitions)
    if args.auto_partitions and row_count is not None:
        target = max(1, args.auto_partition_rows)
        max_parts = args.max_auto_partitions or (os.cpu_count() or 1)
        auto_parts = max(1, math.ceil(row_count / target))
        return max(1, min(auto_parts, max_parts))
    return max(1, args.partitions)


def process_user(
    user_id: str,
    times: Sequence[int],
    base_ts: pd.Timestamp,
    day_max: int,
    beta: float,
    Ib: float,
    alpha: float,
    decay_per_day: bool,
) -> List[Tuple[str, int, float]]:
    if not times:
        return []
    return _compute_user_ru(user_id, times, base_ts, day_max, beta, Ib, alpha, decay_per_day)


def process_file_pandas(
    filepath: str,
    args,
    community: str,
    row_count: int | None,
) -> dict:
    filesize = os.path.getsize(filepath) / (1024 ** 3)
    print(f"\n{'=' * 60}")
    print(f"Community: {community} ({filesize:.2f}GB)")
    if row_count is not None:
        print(f"Rows (events): {row_count:,}")
    print(f"Engine: pandas (inline)")
    print(f"File: {filepath}")
    print(f"Memory before: {get_memory_info()}")

    start = time.time()
    inline_workers = inline.decide_workers(args.inline_workers)
    df = inline.read_and_filter_parquet(
        filepath,
        platform=args.platform,
        community=args.community,
    )
    out_df, tmin, tmax = inline.compute_reputation_parallel(
        df,
        beta=args.beta,
        Ib=args.Ib,
        alpha=args.alpha,
        decay_per_day=args.decay_per_day,
        workers=inline_workers,
    )
    rows = list(
        zip(
            out_df["user_id"].astype(str).tolist(),
            out_df["day"].astype(int).tolist(),
            out_df["reputation"].astype(float).tolist(),
        )
    )
    results_dir, _ = build_output_paths(args.output_dir, community, args.platform)
    fname = default_filename(community, args.platform, args.output_format)
    output_path = os.path.join(results_dir, fname)
    writer = create_writer(output_path, args.output_format)
    try:
        writer.write_rows(rows_with_metadata(rows, tmin, tmax))
    finally:
        writer.close()
    elapsed = time.time() - start
    users_total = out_df["user_id"].nunique()
    events_total = row_count or len(df)
    print(f"✓ Finished {community}: events={events_total:,}, rows={len(rows):,}, users={users_total:,}")
    print(f"  Output: {output_path}")
    print(f"  Time: {elapsed:.1f}s | Memory after: {get_memory_info()}")
    del df
    del out_df
    gc.collect()
    return {
        "community": community,
        "rows": len(rows),
        "users": users_total,
        "events": events_total,
        "output": output_path,
        "elapsed": elapsed,
        "engine": "pandas",
        "partition_id": None,
        "partitions": 1,
    }


def stream_reputation(
    con: duckdb.DuckDBPyConnection,
    rel: duckdb.DuckDBPyRelation,
    args,
    community: str,
    tmin: int,
    tmax: int,
    ms_epoch: bool,
) -> dict:
    rel.create_view("_filtered_source", replace=True)
    if args.duckdb_temp_dir:
        con.execute(f"PRAGMA temp_directory='{sanitize_literal(args.duckdb_temp_dir)}'")
    ts_expr = "CAST(floor(publish_date / 1000) AS BIGINT)" if ms_epoch else "CAST(publish_date AS BIGINT)"
    partition_clause = ""
    if args.partitions > 1:
        partition_clause = (
            f"WHERE mod(hash(user_id), {args.partitions}) = {args.partition_id}"
        )
    query = f"""
        SELECT CAST(user_id AS VARCHAR) AS user_id,
               {ts_expr} AS publish_ts
        FROM _filtered_source
        {partition_clause}
        ORDER BY 1, 2
    """
    relation = con.sql(query)
    if hasattr(relation, "arrow_iterator"):
        arrow_iter = relation.arrow_iterator(batch_size=args.chunk_rows)

        def next_batch() -> pa.RecordBatch | None:
            try:
                batch = next(arrow_iter)
            except StopIteration:
                return None
            if hasattr(batch, "num_rows") and batch.num_rows == 0:
                return next_batch()
            return batch

    else:
        # Fallback for very old DuckDB versions
        def next_batch() -> pa.RecordBatch | None:
            batch = relation.fetch_record_batch(args.chunk_rows)
            if batch is None:
                return None
            if hasattr(batch, "num_rows") and batch.num_rows == 0:
                return next_batch()
            if hasattr(batch, "read_next_batch"):
                reader = batch
                inner = reader.read_next_batch()
                if inner is None:
                    return next_batch()
                if hasattr(inner, "num_rows") and inner.num_rows == 0:
                    return next_batch()
                return inner
            return batch

    results_dir, _ = build_output_paths(args.output_dir, community, args.platform)
    fname = default_filename(
        community,
        args.platform,
        args.output_format,
        partition_id=args.partition_id if args.partitions > 1 else None,
        partitions=args.partitions if args.partitions > 1 else None,
    )
    output_path = os.path.join(results_dir, fname)
    writer = create_writer(output_path, args.output_format)

    rows_total = 0
    users_total = 0
    events_total = 0
    current_user = None
    buffer_times: List[int] = []
    proc = psutil.Process()
    chunk_index = 0
    progress_every = max(1, args.progress_every)
    base_ts = _sec_to_datetime(tmin)
    day_max = max((_sec_to_datetime(tmax) - base_ts).days, 0)
    decay_flag = _normalize_decay_flag(args.decay_per_day)

    try:
        while True:
            batch = next_batch()
            if batch is None:
                break
            chunk_index += 1
            batch_size = batch.num_rows
            events_total += batch_size

            times_array = batch.column(1).to_numpy(zero_copy_only=False)
            encoded_users = pc.run_end_encode(batch.column(0))
            run_ends = encoded_users.run_ends.to_numpy(zero_copy_only=False)
            values = encoded_users.values

            start_idx = 0
            for value_index in range(len(values)):
                uid = values[value_index].as_py()
                end_idx = int(run_ends[value_index])

                if current_user is None:
                    current_user = uid

                if uid != current_user:
                    rows = process_user(
                        current_user,
                        buffer_times,
                        base_ts,
                        day_max,
                        args.beta,
                        args.Ib,
                        args.alpha,
                        decay_flag,
                    )
                    writer.write_rows(rows_with_metadata(rows, tmin, tmax))
                    rows_total += len(rows)
                    users_total += 1
                    buffer_times = []
                    current_user = uid

                if end_idx > start_idx:
                    segment = times_array[start_idx:end_idx]
                    if segment.size:
                        buffer_times.extend(int(ts) for ts in segment)
                start_idx = end_idx
            if chunk_index % progress_every == 0:
                rss = proc.memory_info().rss / (1024 ** 3)
                print(
                    f"  chunk {chunk_index}: events={events_total:,} users={users_total:,} rows={rows_total:,} rss={rss:.2f}GB"
                )
                if args.max_memory_gb is not None and rss > args.max_memory_gb:
                    raise MemoryError(
                        f"RSS {rss:.2f}GB exceeded limit {args.max_memory_gb:.2f}GB while processing {community}"
                    )
            gc.collect()

        if current_user is not None and buffer_times:
            rows = process_user(
                current_user,
                buffer_times,
                base_ts,
                day_max,
                args.beta,
                args.Ib,
                args.alpha,
                decay_flag,
            )
            writer.write_rows(rows_with_metadata(rows, tmin, tmax))
            rows_total += len(rows)
            users_total += 1
    finally:
        writer.close()

    return {
        "rows": rows_total,
        "users": users_total,
        "events": events_total,
        "output": output_path,
        "partition_id": args.partition_id,
        "partitions": args.partitions,
    }


# --- CLI ----------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compute per-user daily reputation using DuckDB streaming with safeguards.",
    )
    p.add_argument("--input", "-i", required=True, help="Parquet file pattern (e.g., data/reddit_technology_*.parquet)")
    p.add_argument("--platform", choices=["reddit", "voat"], help="Optional platform filter")
    p.add_argument("--community", help="Optional community filter (overrides filename-derived name)")
    p.add_argument("--output-dir", default=os.path.join("results", "reputation"))
    p.add_argument("--output-format", choices=["csv", "parquet"], default="csv")
    p.add_argument("--chunk-rows", type=int, default=200_000, help="Arrow batch size when streaming")
    p.add_argument("--progress-every", type=int, default=10, help="Log progress every N batches")
    p.add_argument("--max-memory-gb", type=float, help="Abort if RSS exceeds this many GB")
    p.add_argument("--duckdb-threads", type=int, help="PRAGMA threads override for DuckDB")
    p.add_argument("--duckdb-memory-limit", default="8GB", help="DuckDB memory_limit value (e.g., 8GB or 0.5GB)")
    p.add_argument("--duckdb-temp-dir", help="Directory for DuckDB temp files when spilling")
    p.add_argument("--beta", type=float, default=0.96)
    p.add_argument("--alpha", type=float, default=2.0)
    p.add_argument("--Ib", type=float, default=1.0)
    p.add_argument("--decay-per-day", action="store_true", help="Apply decay for each inactive day")
    p.add_argument("--engine", choices=["auto", "duckdb", "pandas"], default="auto", help="Computation engine (default: auto)")
    p.add_argument("--inline-workers", type=int, default=3, help="Worker count when pandas engine is used")
    p.add_argument("--inline-row-threshold", type=int, default=5_000_000, help="Row threshold to switch to pandas when --engine=auto")
    p.add_argument("--partitions", type=int, default=1, help="Total number of hash partitions to split by user_id")
    p.add_argument("--auto-partitions", action="store_true", help="Automatically increase partitions for large row counts")
    p.add_argument("--auto-partition-rows", type=int, default=30_000_000, help="Target rows per partition when auto partitioning")
    p.add_argument("--max-auto-partitions", type=int, help="Upper bound on partitions when auto partitioning")
    p.add_argument("--partition-id", type=int, help="Partition index (0 <= id < partitions). If omitted, all partitions run in parallel.")
    return p.parse_args()


def load_relation(con: duckdb.DuckDBPyConnection, filepath: str, args) -> duckdb.DuckDBPyRelation:
    rel = con.read_parquet(filepath, union_by_name=True)
    rel = rel.filter("publish_date IS NOT NULL AND user_id IS NOT NULL")
    rel = rel.filter("lower(interaction_type) IN ('post','comment')")
    if args.platform:
        rel = rel.filter(f"lower(platform) = '{sanitize_literal(args.platform.lower())}'")
    if args.community:
        rel = rel.filter(f"lower(community) = '{sanitize_literal(args.community.lower())}'")
    return rel


def count_rows(filepath: str, args) -> int:
    con = duckdb.connect(database=":memory:")
    try:
        rel = load_relation(con, filepath, args)
        count_val = rel.aggregate("count(*)").fetchone()[0]
        return int(count_val or 0)
    finally:
        con.close()


def process_file(filepath: str, args) -> dict:
    community = args.community or extract_community_from_filename(filepath)
    filesize = os.path.getsize(filepath) / (1024 ** 3)
    print(f"\n{'=' * 60}")
    print(f"Community: {community} ({filesize:.2f}GB)")
    print(f"File: {filepath}")
    if getattr(args, "row_count", None) is not None:
        print(f"Rows (events): {int(args.row_count):,}")
    print("Engine: duckdb")
    print(f"Memory before: {get_memory_info()}")
    if args.partitions > 1:
        part_idx = (args.partition_id if args.partition_id is not None else 0) + 1
        print(f"Partition: {part_idx}/{args.partitions}")
    start = time.time()

    con = duckdb.connect(database=":memory:")
    if args.duckdb_threads:
        con.execute(f"PRAGMA threads={int(args.duckdb_threads)}")
    con.execute(f"PRAGMA memory_limit='{args.duckdb_memory_limit}'")
    if args.duckdb_temp_dir:
        con.execute(f"PRAGMA temp_directory='{sanitize_literal(args.duckdb_temp_dir)}'")

    rel = load_relation(con, filepath, args)
    epoch_ms = detect_epoch_is_ms(rel)
    tmin, tmax = fetch_time_bounds(rel, epoch_ms)
    print(f"publish_date unit: {'ms' if epoch_ms else 's'}")
    print(f"Time range: {_sec_to_datetime(tmin)} -> {_sec_to_datetime(tmax)}")

    stats = stream_reputation(con, rel, args, community, tmin, tmax, epoch_ms)
    elapsed = time.time() - start

    part_note = ""
    if stats.get("partitions", 1) > 1:
        part_idx = (
            stats.get("partition_id") if stats.get("partition_id") is not None else 0
        ) + 1
        part_note = f" [partition {part_idx}/{stats['partitions']}]"
    print(
        f"✓ Finished {community}{part_note}: events={stats['events']:,}, rows={stats['rows']:,}, users={stats['users']:,}"
    )
    print(f"  Output: {stats['output']}")
    print(f"  Time: {elapsed:.1f}s | Memory after: {get_memory_info()}")

    con.close()
    gc.collect()

    return {
        "community": community,
        "rows": stats["rows"],
        "users": stats["users"],
        "events": stats["events"],
        "output": stats["output"],
        "elapsed": elapsed,
        "partition_id": stats.get("partition_id"),
        "partitions": stats.get("partitions"),
        "engine": "duckdb",
    }


def main() -> None:
    args = parse_args()
    if args.chunk_rows <= 0:
        raise ValueError("--chunk-rows must be positive")
    if args.progress_every <= 0:
        raise ValueError("--progress-every must be positive")
    if args.partitions <= 0:
        raise ValueError("--partitions must be positive")
    if args.partition_id is not None and not (0 <= args.partition_id < args.partitions):
        raise ValueError("--partition-id must be in [0, partitions)")
    if args.engine == "pandas" and (args.partitions > 1 or args.partition_id is not None or args.auto_partitions):
        raise ValueError("Pandas engine does not support hash partitions")
    files = sorted(glob(args.input))
    if not files:
        raise FileNotFoundError(f"No files matched pattern: {args.input}")
    files = sorted(files, key=lambda f: os.path.getsize(f))

    if args.max_memory_gb is None:
        total_gb = psutil.virtual_memory().total / (1024 ** 3)
        auto_guard = max(total_gb * 0.45, 1.0)
        args.max_memory_gb = auto_guard
        guard_display = f"{auto_guard:.2f} GB"
        auto_guard_note = " (auto 45% of RAM)"
    elif args.max_memory_gb <= 0:
        args.max_memory_gb = None
        guard_display = "disabled"
        auto_guard_note = ""
    else:
        guard_display = f"{args.max_memory_gb:.2f} GB"
        auto_guard_note = ""

    print("=" * 60)
    print("DuckDB Dynamical Reputation")
    print("=" * 60)
    partition_desc = (
        f"{args.partitions} (all partitions)"
        if args.partition_id is None and args.partitions > 1
        else f"{args.partitions} (running partition {(args.partition_id or 0) + 1})"
    )
    print(f"Files: {len(files)} | Platform: {args.platform or 'all'}")
    print(f"Partitions: {partition_desc}")
    print(f"Chunk rows: {args.chunk_rows:,} | Output format: {args.output_format}")
    print(f"Memory guard: {guard_display}{auto_guard_note}")

    summary = []
    for idx, filepath in enumerate(files, start=1):
        row_count = count_rows(filepath, args)
        engine = decide_engine(args, row_count)
        partitions = decide_partitions(args, row_count, engine)
        base_name = os.path.basename(filepath)
        print(
            f"\n[{idx}/{len(files)}] {base_name} | rows={row_count:,} | engine={engine} | partitions={partitions}"
        )

        community = args.community or extract_community_from_filename(filepath)

        if engine == "pandas":
            info = process_file_pandas(filepath, args, community, row_count)
            info["row_count"] = row_count
            summary.append(info)
            continue

        effective_partitions = partitions

        if args.partition_id is None and effective_partitions > 1:
            workers = min(effective_partitions, os.cpu_count() or effective_partitions)
            print(f"  Launching {effective_partitions} parallel workers (hash partition on user_id)")
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        process_file,
                        filepath,
                        clone_args(
                            args,
                            partition_id=pid,
                            partitions=effective_partitions,
                            row_count=row_count,
                        ),
                    ): pid
                    for pid in range(effective_partitions)
                }
                for fut in as_completed(futures):
                    info = fut.result()
                    info["row_count"] = row_count
                    summary.append(info)
        else:
            single_args = clone_args(
                args,
                partition_id=(args.partition_id or 0),
                partitions=effective_partitions,
                row_count=row_count,
            )
            info = process_file(filepath, single_args)
            info["row_count"] = row_count
            summary.append(info)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    def _summary_key(entry: dict) -> tuple:
        return (
            entry.get("community", ""),
            entry.get("partition_id") if entry.get("partitions", 1) > 1 else -1,
        )

    for item in sorted(summary, key=_summary_key):
        part_note = ""
        if item.get("partitions", 1) > 1:
            part_idx = (
                item.get("partition_id") if item.get("partition_id") is not None else 0
            ) + 1
            part_note = f" [part {part_idx}/{item['partitions']}]"
        engine = item.get("engine", "duckdb")
        row_count = item.get("row_count")
        events_val = item.get("events")
        if events_val is None:
            events_str = ""
        elif row_count is not None and row_count != events_val:
            events_str = f", events={events_val:,}/{row_count:,}"
        else:
            events_str = f", events={events_val:,}"
        print(
            f"{item['community']}{part_note}: engine={engine}{events_str}, rows={item['rows']:,}, users={item['users']:,}, time={item['elapsed']:.1f}s, output={item['output']}"
        )


if __name__ == "__main__":
    main()
