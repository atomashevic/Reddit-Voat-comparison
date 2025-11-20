# Task: Optimize Reputation Pipeline Memory Usage

## Status
- [x] Optimize `scripts/dynamical_reputation/dynamical_reputation_hybrid.py` <!-- id: 0 -->
    - [x] Use `pyarrow.compute.run_end_encode` for efficient user grouping
    - [x] Accumulate timestamps as list of numpy arrays instead of list of ints
    - [x] Optimize `_compute_user_ru` to use integer arithmetic
- [x] Optimize `scripts/dynamical_reputation/dynamical_reputation_duckdb.py` <!-- id: 1 -->
    - [x] Accumulate timestamps as list of numpy arrays
    - [x] Optimize `_compute_user_ru` to use integer arithmetic
- [x] Verify changes <!-- id: 2 -->
