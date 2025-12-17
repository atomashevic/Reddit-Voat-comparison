#!/bin/bash
#
# Minimal alternative pipeline: build metrics, bootstrap bands, newcomer partition,
# merge monthly metrics, and render a single 8-panel overview figure.
# All outputs under: results/alternative/{community}/
#
# Usage:
#   bash scripts/run_alternative_pipeline.sh funny
#

set -euo pipefail  # Exit on error and unset vars

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

COMMUNITY="${1:-}"
if [[ -z "$COMMUNITY" ]]; then
    echo "❌ Error: Community name required"
    echo "Usage: bash scripts/run_alternative_pipeline.sh <community>"
    exit 1
fi

# Unified output directory
RESULTS_ROOT="results"
# Prefer writing figures where the LaTeX paper expects them.
if [[ -d "paper" ]]; then
    FIGURES_ROOT="paper/figures"
else
    FIGURES_ROOT="figures"
fi

RES_REDDIT="${RESULTS_ROOT}/reddit/${COMMUNITY}"
RES_VOAT="${RESULTS_ROOT}/voat/${COMMUNITY}"
RES_COMPARE="${RESULTS_ROOT}/compare/${COMMUNITY}"
FIG_COMPARE="${FIGURES_ROOT}/compare/${COMMUNITY}"

# Ensure directories exist
mkdir -p "$RES_REDDIT" "$RES_VOAT" "$RES_COMPARE" "$FIG_COMPARE"

# NOTE: legacy BASIC_ROOT variables removed (unused in current pipeline).

# Bootstrap parameters (only for toxicity/sentiment bands)
BOOTSTRAP_ITERATIONS=40
RANDOM_SEED=2025

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo ""
    echo -e "${PURPLE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${PURPLE}  $1${NC}"
    echo -e "${PURPLE}════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${CYAN}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_file_exists() {
    local file="$1"
    local description="$2"

    if [[ -f "$file" ]]; then
        local size=$(du -h "$file" | cut -f1)
        print_success "$description exists ($size)"
        return 0
    else
        print_error "$description NOT FOUND: $file"
        return 1
    fi
}

run_python_script() {
    local script="$1"
    local description="$2"
    shift 2

    print_step "$description"

    if python "$script" "$@"; then
        print_success "Completed: $description"
        return 0
    else
        print_error "Failed: $description"
        return 1
    fi
}

# ============================================================================
# Pre-flight Checks
# ============================================================================

print_header "Pre-flight Checks for ${COMMUNITY}"

# Check Python environment
print_step "Checking Python environment..."
if command -v pyenv &> /dev/null; then
    if pyenv version | grep -q "python13"; then
        print_success "pyenv environment: python13"
    else
        print_warning "pyenv active but not python13. Attempting to activate..."
        eval "$(pyenv init -)"
        pyenv activate python13 || print_warning "Could not activate python13"
    fi
else
    print_warning "pyenv not found, using system Python: $(python --version)"
fi

# Check required directories
print_step "Checking data directories..."
DATA_DIR="data"
NETWORKS_DIR="results/networks"

if [[ ! -d "$DATA_DIR" ]]; then
    print_error "Data directory not found: $DATA_DIR"
    exit 1
fi

# Check for parquet files
REDDIT_PARQUET="${DATA_DIR}/reddit_${COMMUNITY}_madoc.parquet"
VOAT_PARQUET="${DATA_DIR}/voat_${COMMUNITY}_madoc.parquet"

if [[ ! -f "$REDDIT_PARQUET" ]]; then
    print_error "Reddit parquet not found: $REDDIT_PARQUET"
    exit 1
fi

if [[ ! -f "$VOAT_PARQUET" ]]; then
    print_error "Voat parquet not found: $VOAT_PARQUET"
    exit 1
fi

print_success "Reddit parquet: $REDDIT_PARQUET ($(du -h "$REDDIT_PARQUET" | cut -f1))"
print_success "Voat parquet: $VOAT_PARQUET ($(du -h "$VOAT_PARQUET" | cut -f1))"

# Create output directories
print_step "Creating output directories..."
# Already created above
print_success "Output roots: $RES_REDDIT, $RES_VOAT, $RES_COMPARE"

# ============================================================================
# STEP 1: Build user-month metrics (with reputation) and monthly aggregates
# ============================================================================

print_header "STEP 1: Build metrics and aggregates"

# Reddit user-month metrics
TARGET="${RES_REDDIT}/reddit_${COMMUNITY}_user_month_metrics.parquet"
if [[ -s "$TARGET" ]]; then
    print_success "Reddit user-month metrics already exist"
else
    run_python_script \
        "scripts/build_global_monthly_metrics_lowmem.py" \
        "Building Reddit user-month metrics" \
        --community "$COMMUNITY" \
        --platform reddit \
        --output-dir "$RES_REDDIT" \
        --log-level INFO
fi
check_file_exists "$TARGET" "Reddit user-month metrics"

# Voat user-month metrics
TARGET="${RES_VOAT}/voat_${COMMUNITY}_user_month_metrics.parquet"
if [[ -s "$TARGET" ]]; then
    print_success "Voat user-month metrics already exist"
else
    run_python_script \
        "scripts/build_global_monthly_metrics_lowmem.py" \
        "Building Voat user-month metrics" \
        --community "$COMMUNITY" \
        --platform voat \
        --output-dir "$RES_VOAT" \
        --log-level INFO
fi
check_file_exists "$TARGET" "Voat user-month metrics"

# Ensure network metrics present; compute if missing for either platform
print_step "Ensuring network metrics exist..."
REDDIT_NET_CSV="${RES_REDDIT}/reddit_${COMMUNITY}_global_metrics.csv"
VOAT_NET_CSV="${RES_VOAT}/voat_${COMMUNITY}_global_metrics.csv"

if [[ ! -f "$REDDIT_NET_CSV" || ! -f "$VOAT_NET_CSV" ]]; then
    run_python_script \
        "scripts/compute_global_network_metrics.py" \
        "Computing network metrics (Reddit & Voat)" \
        --communities "$COMMUNITY" \
        --platforms reddit voat \
        --networks-dir "results/networks" \
        --verbose
        
    # Copy to community folders
    cp "results/networks/reddit/results/reddit_${COMMUNITY}_global_metrics.csv" "$RES_REDDIT/" 2>/dev/null || true
    cp "results/networks/voat/results/voat_${COMMUNITY}_global_metrics.csv" "$RES_VOAT/" 2>/dev/null || true
fi

# Monthly aggregates (merge network metrics)
TARGET="${RES_REDDIT}/reddit_${COMMUNITY}_monthly_aggregates.csv"
# Always re-run aggregation as it's fast and might need updates from network metrics
run_python_script \
    "scripts/aggregate_monthly_metrics_global.py" \
    "Aggregating Reddit monthly metrics" \
    --community "$COMMUNITY" \
    --platform reddit \
    --basic-dir "results" \
    --networks-dir "results" \
    --output-dir "$RES_REDDIT" \
    --input-file "${RES_REDDIT}/reddit_${COMMUNITY}_user_month_metrics.parquet" \
    --log-level INFO
check_file_exists "$TARGET" "Reddit monthly aggregates"

TARGET="${RES_VOAT}/voat_${COMMUNITY}_monthly_aggregates.csv"
run_python_script \
    "scripts/aggregate_monthly_metrics_global.py" \
    "Aggregating Voat monthly metrics" \
    --community "$COMMUNITY" \
    --platform voat \
    --basic-dir "results" \
    --networks-dir "results" \
    --output-dir "$RES_VOAT" \
    --input-file "${RES_VOAT}/voat_${COMMUNITY}_user_month_metrics.parquet" \
    --log-level INFO
check_file_exists "$TARGET" "Voat monthly aggregates"

print_success "Step 1 complete"

# ============================================================================
# STEP 2: Bootstrap bands (toxicity, sentiment)
# ============================================================================

print_header "STEP 2: Bootstrap bands (toxicity, sentiment)"

TARGET="${RES_COMPARE}/${COMMUNITY}_global_bootstrap_summary.csv"
if [[ -s "$TARGET" ]]; then
    print_success "Bootstrap summary already exists"
else
    run_python_script \
        "scripts/compare_global_bootstrap.py" \
        "Bootstrap toxicity/sentiment" \
        --community "$COMMUNITY" \
        --basic-dir "results" \
        --output-dir "$RES_COMPARE" \
        --reddit-metrics "${RES_REDDIT}/reddit_${COMMUNITY}_user_month_metrics.parquet" \
        --voat-metrics "${RES_VOAT}/voat_${COMMUNITY}_user_month_metrics.parquet" \
        --bootstrap-iterations "$BOOTSTRAP_ITERATIONS" \
        --seed "$RANDOM_SEED" \
        --log-level INFO
fi

check_file_exists "$TARGET" "Bootstrap summary"

print_success "Step 2 complete"

# ============================================================================
# STEP 3: Newcomer partition (Voat) - For Global Aggregate E-I
# ============================================================================

print_header "STEP 3: Newcomer partition metrics"

run_python_script \
    "scripts/identify_voat_newcomers.py" \
    "Identify Voat newcomers" \
    --community "$COMMUNITY" \
    --basic-dir "$RESULTS_ROOT" \
    --voat-metrics "${RES_VOAT}/voat_${COMMUNITY}_user_month_metrics.parquet" \
    --output-dir "$RES_VOAT" \
    --log-level INFO
check_file_exists "${RES_VOAT}/voat_${COMMUNITY}_newcomer_labels.csv" "Newcomer labels"

run_python_script \
    "scripts/analyze_monthly_newcomers.py" \
    "Monthly newcomer vs existing partition metrics" \
    --community "$COMMUNITY" \
    --basic-dir "$RESULTS_ROOT" \
    --networks-dir "results/networks" \
    --voat-metrics "${RES_VOAT}/voat_${COMMUNITY}_user_month_metrics.parquet" \
    --output-dir "$RES_VOAT" \
    --log-level INFO
check_file_exists "${RES_VOAT}/voat_${COMMUNITY}_monthly_newcomer_analysis.csv" "Monthly newcomer analysis"

print_success "Step 3 complete"

# ============================================================================
# STEP 4: Merge + Plot overview
# ============================================================================

print_header "STEP 4: Merge metrics and plot overview"

run_python_script \
    "scripts/merge_overview_metrics.py" \
    "Merging metrics for overview outputs" \
    --community "$COMMUNITY" \
    --results-root "$RESULTS_ROOT" \
    --compare-dir "$RES_COMPARE" \
    --output-dir "$RES_COMPARE"

check_file_exists "${RES_COMPARE}/${COMMUNITY}_monthly_metrics.csv" "Merged monthly metrics"
check_file_exists "${RES_COMPARE}/${COMMUNITY}_summary.csv" "Summary metrics"

run_python_script \
    "scripts/plot_overview.py" \
    "Plotting 8-panel overview" \
    --community "$COMMUNITY" \
    --monthly-file "${RES_COMPARE}/${COMMUNITY}_monthly_metrics.csv" \
    --output-dir "$FIG_COMPARE"

check_file_exists "${FIG_COMPARE}/${COMMUNITY}_overview.png" "Overview figure"

print_success "Pipeline complete for ${COMMUNITY}"
echo "Outputs:"
echo "  Monthly metrics: ${RES_COMPARE}/${COMMUNITY}_monthly_metrics.csv"
echo "  Summary metrics: ${RES_COMPARE}/${COMMUNITY}_summary.csv"
echo "  Figure: ${FIG_COMPARE}/${COMMUNITY}_overview.png"
