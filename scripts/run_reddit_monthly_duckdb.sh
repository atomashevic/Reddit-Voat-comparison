#!/usr/bin/env bash
# Sequentially convert Reddit daily reputation outputs into monthly core/periphery summaries
# using the DuckDB-based pipeline. Designed to be launched inside a tmux session with
# `pyenv activate python13` already sourced.

set -euo pipefail

readonly COMMUNITIES=(
  funny
  kotakuinaction
  cringeanarchy
  pics
  gaming
  technology
  videos
  gifs
  greatawakening
  milliondollarextreme
  mensrights
)

readonly PYTHON_BIN="python"
readonly SCRIPT_PATH="scripts/dynamical_reputation/mean_monthly_reputation_duckdb.py"
readonly CP_DIR="results/core-periphery"
readonly REP_DIR="results/reputation"
readonly OUT_DIR="results/reputation"
readonly SPILL_DIR="tmp/duckdb_spill"

mkdir -p tmp
mkdir -p "${SPILL_DIR}"

echo "[$(date)] Starting sequential DuckDB monthly reputation generation..."

for community in "${COMMUNITIES[@]}"; do
  log_path="tmp/${community}_duckdb.log"
  out_csv="results/reputation/reddit/results/reddit_${community}_cp_monthly_reputation.csv"

  echo "[$(date)] >>> Processing ${community}"
  echo "  Log: ${log_path}"

  : > "${log_path}"

  ${PYTHON_BIN} "${SCRIPT_PATH}" \
    --platform reddit \
    --community "${community}" \
    --cp-dir "${CP_DIR}" \
    --reputation-dir "${REP_DIR}" \
    --output-dir "${OUT_DIR}" \
    --duckdb-temp-dir "${SPILL_DIR}" \
    --duckdb-memory-limit 4000MB \
    --duckdb-threads 4 \
    >> "${log_path}" 2>&1

  if [[ -s "${out_csv}" ]]; then
    echo "[$(date)]     ✓ Output written to ${out_csv}"
  else
    echo "[$(date)]     ⚠ WARNING: Expected output ${out_csv} not found or empty." >&2
  fi

  if pgrep -f "${SCRIPT_PATH}" >/dev/null; then
    echo "[$(date)]     ⚠ Detected lingering DuckDB process; waiting for cleanup..."
    while pgrep -f "${SCRIPT_PATH}" >/dev/null; do
      sleep 2
    done
    echo "[$(date)]     ✓ Residual process exited."
  fi

  if [[ -d "${SPILL_DIR}" ]]; then
    find "${SPILL_DIR}" -type f -delete || true
  fi

  sync
  echo "[$(date)] <<< Completed ${community}"
done

echo "[$(date)] All communities processed."
