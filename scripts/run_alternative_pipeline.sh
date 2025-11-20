#!/bin/bash
#
# Run complete alternative (non-core-periphery) analysis pipeline for a single community.
#
# Usage:
#   bash scripts/run_alternative_pipeline.sh funny
#   bash scripts/run_alternative_pipeline.sh funny --skip-phase-1
#
# All outputs centralized under: results/alternative/{community}/
#

set -e  # Exit on error

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

COMMUNITY="$1"
SKIP_PHASE_1=false
SKIP_PHASE_2=false
SKIP_PHASE_3=false
SKIP_PHASE_4=false

# Parse arguments
if [[ -z "$COMMUNITY" ]]; then
    echo "❌ Error: Community name required"
    echo "Usage: bash scripts/run_alternative_pipeline.sh <community> [--skip-phase-N]"
    echo "Example: bash scripts/run_alternative_pipeline.sh funny"
    exit 1
fi

shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-phase-1) SKIP_PHASE_1=true; shift ;;
        --skip-phase-2) SKIP_PHASE_2=true; shift ;;
        --skip-phase-3) SKIP_PHASE_3=true; shift ;;
        --skip-phase-4) SKIP_PHASE_4=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Unified output directory
ALT_ROOT="results/alternative/${COMMUNITY}"
ALT_REDDIT="${ALT_ROOT}/reddit"
ALT_VOAT="${ALT_ROOT}/voat"
ALT_COMPARE="${ALT_ROOT}/compare"
ALT_FIGURES="${ALT_ROOT}/figures"
ALT_NETWORKS_REDDIT="${ALT_ROOT}/networks/reddit"
ALT_NETWORKS_VOAT="${ALT_ROOT}/networks/voat"

# Legacy results directory (for reuse from previous runs)
BASIC_ROOT="results/basic/${COMMUNITY}"
BASIC_REDDIT="${BASIC_ROOT}/reddit/results"
BASIC_VOAT="${BASIC_ROOT}/voat/results"

# Bootstrap parameters
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
mkdir -p "$ALT_REDDIT" "$ALT_VOAT" "$ALT_COMPARE" "$ALT_FIGURES"
mkdir -p "$ALT_NETWORKS_REDDIT" "$ALT_NETWORKS_VOAT"
print_success "Output root: $ALT_ROOT"

# ============================================================================
# PHASE 1: Build Metrics
# ============================================================================

if [[ "$SKIP_PHASE_1" == true ]]; then
    print_warning "Skipping Phase 1 (as requested)"
else
    print_header "PHASE 1: Build Metrics (Smart Resume)"

    # --- Step 1.1: Reddit User Metrics ---
    TARGET_FILE="${ALT_REDDIT}/reddit_${COMMUNITY}_user_month_metrics.parquet"
    SOURCE_FILE="${BASIC_REDDIT}/reddit_${COMMUNITY}_user_month_metrics.parquet"
    
    if [[ -f "$TARGET_FILE" ]]; then
        print_success "1.1: Reddit user metrics already exist"
    elif [[ -f "$SOURCE_FILE" ]]; then
        print_step "1.1: Found legacy Reddit metrics in basic/. Copying..."
        cp "$SOURCE_FILE" "$TARGET_FILE"
        print_success "Copied to alternative pipeline"
    else
        run_python_script \
            "scripts/build_global_monthly_metrics_lowmem.py" \
            "1.1: Building Reddit user-month metrics" \
            --community "$COMMUNITY" \
            --platform reddit \
            --output-dir "$ALT_REDDIT" \
            --log-level INFO
    fi
    
    check_file_exists "$TARGET_FILE" "Reddit user-month metrics"

    # --- Step 1.2: Voat User Metrics ---
    TARGET_FILE="${ALT_VOAT}/voat_${COMMUNITY}_user_month_metrics.parquet"
    SOURCE_FILE="${BASIC_VOAT}/voat_${COMMUNITY}_user_month_metrics.parquet"

    if [[ -f "$TARGET_FILE" ]]; then
        print_success "1.2: Voat user metrics already exist"
    elif [[ -f "$SOURCE_FILE" ]]; then
        print_step "1.2: Found legacy Voat metrics in basic/. Copying..."
        cp "$SOURCE_FILE" "$TARGET_FILE"
        print_success "Copied to alternative pipeline"
    else
    run_python_script \
        "scripts/build_global_monthly_metrics_lowmem.py" \
        "1.2: Building Voat user-month metrics" \
        --community "$COMMUNITY" \
        --platform voat \
        --output-dir "$ALT_VOAT" \
        --log-level INFO
    fi

    check_file_exists "$TARGET_FILE" "Voat user-month metrics"

    # --- Step 1.3: Network Metrics ---
    print_step "1.3: Checking global network metrics..."

    # Check if network edge lists exist
    REDDIT_NET_DIR="${NETWORKS_DIR}/reddit/${COMMUNITY}_monthly"
    VOAT_NET_DIR="${NETWORKS_DIR}/voat/${COMMUNITY}_monthly"

    if [[ ! -d "$REDDIT_NET_DIR" ]] && [[ ! -d "$VOAT_NET_DIR" ]]; then
        print_warning "Network edge lists not found. Skipping network metrics."
    else
        # Check if metrics already exist in the central networks directory
        REDDIT_NET_CSV="${NETWORKS_DIR}/reddit/results/reddit_${COMMUNITY}_global_metrics.csv"
        VOAT_NET_CSV="${NETWORKS_DIR}/voat/results/voat_${COMMUNITY}_global_metrics.csv"
        
        # Only run computation if BOTH are missing (safest approach) or if you want to force update
        if [[ -f "$REDDIT_NET_CSV" ]] || [[ -f "$VOAT_NET_CSV" ]]; then
             print_success "Network metrics found in ${NETWORKS_DIR}. Skipping re-computation."
        else
             # Compute network metrics (only if missing)
            run_python_script \
                "scripts/compute_global_network_metrics.py" \
                "1.3a: Computing network metrics (Reddit & Voat)" \
                --communities "$COMMUNITY" \
                --platforms reddit voat \
                --networks-dir "$NETWORKS_DIR" \
                --verbose
        fi

        # Copy network metrics to alternative directory
        if [[ -f "$REDDIT_NET_CSV" ]]; then
            cp "$REDDIT_NET_CSV" "$ALT_NETWORKS_REDDIT/"
            print_success "Copied Reddit network metrics to $ALT_NETWORKS_REDDIT"
        fi

        if [[ -f "$VOAT_NET_CSV" ]]; then
            cp "$VOAT_NET_CSV" "$ALT_NETWORKS_VOAT/"
            print_success "Copied Voat network metrics to $ALT_NETWORKS_VOAT"
        fi
    fi

    # --- Step 1.4: Aggregate Reddit ---
    TARGET_FILE="${ALT_REDDIT}/reddit_${COMMUNITY}_monthly_aggregates.csv"
    SOURCE_FILE="${BASIC_REDDIT}/reddit_${COMMUNITY}_monthly_aggregates.csv"
    
    if [[ -f "$TARGET_FILE" ]]; then
        print_success "1.4: Reddit aggregates already exist"
    elif [[ -f "$SOURCE_FILE" ]]; then
         print_step "1.4: Found legacy Reddit aggregates. Copying..."
         cp "$SOURCE_FILE" "$TARGET_FILE"
         print_success "Copied from basic results"
    else
        # Pass the explicit path to the user metrics we just built in Step 1.1
        USER_METRICS_FILE="${ALT_REDDIT}/reddit_${COMMUNITY}_user_month_metrics.parquet"
        
        run_python_script \
            "scripts/aggregate_monthly_metrics_global.py" \
            "1.4: Aggregating Reddit monthly metrics" \
            --community "$COMMUNITY" \
            --platform reddit \
            --basic-dir "results/alternative" \
            --networks-dir "$ALT_ROOT/networks" \
            --output-dir "$ALT_REDDIT" \
            --input-file "$USER_METRICS_FILE" \
            --log-level INFO
    fi

    check_file_exists "$TARGET_FILE" "Reddit monthly aggregates"

    # --- Step 1.5: Aggregate Voat ---
    TARGET_FILE="${ALT_VOAT}/voat_${COMMUNITY}_monthly_aggregates.csv"
    SOURCE_FILE="${BASIC_VOAT}/voat_${COMMUNITY}_monthly_aggregates.csv"

    if [[ -f "$TARGET_FILE" ]]; then
        print_success "1.5: Voat aggregates already exist"
    elif [[ -f "$SOURCE_FILE" ]]; then
         print_step "1.5: Found legacy Voat aggregates. Copying..."
         cp "$SOURCE_FILE" "$TARGET_FILE"
         print_success "Copied from basic results"
    else
        # Pass explicit path to the user metrics we built in Step 1.2
        USER_METRICS_FILE="${ALT_VOAT}/voat_${COMMUNITY}_user_month_metrics.parquet"

        run_python_script \
            "scripts/aggregate_monthly_metrics_global.py" \
            "1.5: Aggregating Voat monthly metrics" \
            --community "$COMMUNITY" \
            --platform voat \
            --basic-dir "results/alternative" \
            --networks-dir "$ALT_ROOT/networks" \
            --output-dir "$ALT_VOAT" \
            --input-file "$USER_METRICS_FILE" \
            --log-level INFO
    fi

    check_file_exists "$TARGET_FILE" "Voat monthly aggregates"

    print_success "Phase 1 complete: Metrics built"
fi

# ============================================================================
# PHASE 2: Reddit-Voat Comparison
# ============================================================================

if [[ "$SKIP_PHASE_2" == true ]]; then
    print_warning "Skipping Phase 2 (as requested)"
else
    print_header "PHASE 2: Reddit-Voat Comparison (3 steps)"

    # Step 2.1: Bootstrap
    # Pass explicit paths to user metrics from Phase 1
    REDDIT_METRICS_FILE="${ALT_REDDIT}/reddit_${COMMUNITY}_user_month_metrics.parquet"
    VOAT_METRICS_FILE="${ALT_VOAT}/voat_${COMMUNITY}_user_month_metrics.parquet"

    run_python_script \
        "scripts/compare_global_bootstrap.py" \
        "2.1: Generating activity-matched bootstrap samples" \
        --community "$COMMUNITY" \
        --basic-dir "results/alternative" \
        --output-dir "$ALT_COMPARE" \
        --reddit-metrics "$REDDIT_METRICS_FILE" \
        --voat-metrics "$VOAT_METRICS_FILE" \
        --bootstrap-iterations "$BOOTSTRAP_ITERATIONS" \
        --seed "$RANDOM_SEED" \
        --log-level INFO

    check_file_exists \
        "${ALT_COMPARE}/${COMMUNITY}_global_monthly_metrics.csv" \
        "Combined monthly metrics"

    check_file_exists \
        "${ALT_COMPARE}/${COMMUNITY}_global_bootstrap_samples.csv" \
        "Bootstrap samples"

    check_file_exists \
        "${ALT_COMPARE}/${COMMUNITY}_global_bootstrap_summary.csv" \
        "Bootstrap summary (percentiles)"

    # Step 2.2: Event windows
    run_python_script \
        "scripts/analyze_global_event_windows.py" \
        "2.2: Analyzing event windows (Events A, B, C)" \
        --community "$COMMUNITY" \
        --compare-dir "$ALT_COMPARE" \
        --networks-dir "$ALT_ROOT/networks" \
        --output-dir "$ALT_COMPARE" \
        --log-level INFO

    check_file_exists \
        "${ALT_COMPARE}/${COMMUNITY}_global_event_window_summary.csv" \
        "Event window summary"

    # Step 2.3: Significance testing
    run_python_script \
        "scripts/global_significance_testing.py" \
        "2.3: Statistical significance testing" \
        --community "$COMMUNITY" \
        --compare-dir "$ALT_COMPARE" \
        --output-dir "$ALT_COMPARE" \
        --log-level INFO

    check_file_exists \
        "${ALT_COMPARE}/${COMMUNITY}_global_significance_summary.csv" \
        "Significance summary"

    print_success "Phase 2 complete: Reddit-Voat comparison done"
fi

# ============================================================================
# PHASE 3: Voat Newcomer Analysis
# ============================================================================

if [[ "$SKIP_PHASE_3" == true ]]; then
    print_warning "Skipping Phase 3 (as requested)"
else
    print_header "PHASE 3: Voat Newcomer Analysis (3 steps)"

    # Step 3.1: Identify newcomers
    run_python_script \
        "scripts/identify_voat_newcomers.py" \
        "3.1: Identifying Voat newcomers (from Event A)" \
        --community "$COMMUNITY" \
        --basic-dir "results/alternative" \
        --output-dir "$ALT_VOAT" \
        --log-level INFO

    check_file_exists \
        "${ALT_VOAT}/voat_${COMMUNITY}_newcomer_labels.csv" \
        "Newcomer labels"

    # Step 3.2: Month-by-month analysis
    print_step "3.2: Analyzing monthly newcomer dynamics..."
    print_warning "  Note: This step requires network edge lists"
    print_warning "  If network files are missing, partition metrics will be NaN"

    run_python_script \
        "scripts/analyze_monthly_newcomers.py" \
        "3.2: Monthly newcomer vs existing analysis" \
        --community "$COMMUNITY" \
        --basic-dir "results/alternative" \
        --networks-dir "$NETWORKS_DIR" \
        --output-dir "$ALT_VOAT" \
        --log-level INFO

    check_file_exists \
        "${ALT_VOAT}/voat_${COMMUNITY}_monthly_newcomer_analysis.csv" \
        "Monthly newcomer analysis"

    # Step 3.3: Cumulative period analysis
    run_python_script \
        "scripts/analyze_cumulative_newcomers.py" \
        "3.3: Cumulative period newcomer analysis (A→B, B→C, C→End)" \
        --community "$COMMUNITY" \
        --basic-dir "results/alternative" \
        --networks-dir "$NETWORKS_DIR" \
        --output-dir "$ALT_VOAT" \
        --log-level INFO

    check_file_exists \
        "${ALT_VOAT}/voat_${COMMUNITY}_cumulative_newcomer_analysis.csv" \
        "Cumulative newcomer analysis"

    print_success "Phase 3 complete: Newcomer analysis done"
fi

# ============================================================================
# PHASE 4: Visualization
# ============================================================================

if [[ "$SKIP_PHASE_4" == true ]]; then
    print_warning "Skipping Phase 4 (as requested)"
else
    print_header "PHASE 4: Visualization (4 plots)"

    # Plot 4.1: Global comparison panels
    run_python_script \
        "scripts/plot_global_comparison_panels.py" \
        "4.1: Creating global comparison panels" \
        --community "$COMMUNITY" \
        --compare-dir "$ALT_COMPARE" \
        --networks-dir "$ALT_ROOT/networks" \
        --output-dir "$ALT_FIGURES"

    check_file_exists \
        "${ALT_FIGURES}/${COMMUNITY}_global_comparison_panels.png" \
        "Global comparison panels figure"

    # Plot 4.2: Newcomer dynamics
    run_python_script \
        "scripts/plot_newcomer_dynamics.py" \
        "4.2: Creating newcomer dynamics plot" \
        --community "$COMMUNITY" \
        --basic-dir "$ALT_ROOT" \
        --output-dir "$ALT_FIGURES"

    check_file_exists \
        "${ALT_FIGURES}/${COMMUNITY}_monthly_newcomer_dynamics.png" \
        "Newcomer dynamics figure"

    # Plot 4.3: Cumulative periods
    run_python_script \
        "scripts/plot_cumulative_newcomer_periods.py" \
        "4.3: Creating cumulative period comparison plot" \
        --community "$COMMUNITY" \
        --basic-dir "$ALT_ROOT" \
        --output-dir "$ALT_FIGURES"

    check_file_exists \
        "${ALT_FIGURES}/${COMMUNITY}_cumulative_newcomer_periods.png" \
        "Cumulative periods figure"

    print_success "Phase 4 complete: All visualizations created"
fi

# ============================================================================
# Final Summary
# ============================================================================

print_header "Pipeline Complete for ${COMMUNITY}"

echo -e "${GREEN}✓ All outputs saved to: ${ALT_ROOT}${NC}"
echo ""
echo "📂 Directory structure:"
echo "  $ALT_ROOT/"
echo "  ├── reddit/                    # Reddit metrics"
echo "  ├── voat/                      # Voat metrics + newcomer analysis"
echo "  ├── compare/                   # Bootstrap, events, significance"
echo "  ├── networks/                  # Network metrics"
echo "  │   ├── reddit/"
echo "  │   └── voat/"
echo "  └── figures/                   # All visualizations"
echo ""

# Count outputs
TOTAL_FILES=$(find "$ALT_ROOT" -type f | wc -l)
CSV_FILES=$(find "$ALT_ROOT" -name "*.csv" | wc -l)
PARQUET_FILES=$(find "$ALT_ROOT" -name "*.parquet" | wc -l)
PNG_FILES=$(find "$ALT_ROOT" -name "*.png" | wc -l)

echo "📊 Output summary:"
echo "  Total files: $TOTAL_FILES"
echo "  CSV files: $CSV_FILES"
echo "  Parquet files: $PARQUET_FILES"
echo "  PNG figures: $PNG_FILES"
echo ""

# List key outputs
echo "🔑 Key outputs:"
echo ""
echo "  Behavioral Metrics:"
echo "    - ${ALT_COMPARE}/${COMMUNITY}_global_monthly_metrics.csv"
echo ""
echo "  Statistical Tests:"
echo "    - ${ALT_COMPARE}/${COMMUNITY}_global_significance_summary.csv"
echo "    - ${ALT_COMPARE}/${COMMUNITY}_global_event_window_summary.csv"
echo ""
echo "  Newcomer Analysis:"
echo "    - ${ALT_VOAT}/voat_${COMMUNITY}_monthly_newcomer_analysis.csv"
echo "    - ${ALT_VOAT}/voat_${COMMUNITY}_cumulative_newcomer_analysis.csv"
echo ""
echo "  Figures:"
for fig in "${ALT_FIGURES}"/*.png; do
    if [[ -f "$fig" ]]; then
        echo "    - $(basename "$fig")"
    fi
done
echo ""

print_success "Pipeline execution completed successfully!"
echo ""
echo "To view figures:"
echo "  ls -lh ${ALT_FIGURES}/"
echo ""
echo "To run for another community:"
echo "  bash scripts/run_alternative_pipeline.sh <community>"
echo ""
