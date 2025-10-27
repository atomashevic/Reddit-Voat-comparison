#!/bin/bash
# Batch processing of dynamical reputation for all Reddit communities
# Processes each community separately to avoid OOM issues

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/dynamical_reputation_inline.py"
DATA_DIR="${PROJECT_ROOT}/data"
PLATFORM="reddit"
OUTPUT_FORMAT="parquet"
WORKERS=3  # Conservative for large files to avoid memory issues

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print memory usage
print_memory() {
    local prefix="$1"
    local mem_used=$(free -h | awk 'NR==2{print $3}')
    local mem_total=$(free -h | awk 'NR==2{print $2}')
    local mem_pct=$(free | awk 'NR==2{printf "%.1f", $3/$2*100}')
    echo -e "${BLUE}[MEMORY]${NC} ${prefix} - Used: ${mem_used}/${mem_total} (${mem_pct}%)"
}

# Function to extract community name from filename
get_community_name() {
    local filepath="$1"
    # Extract: reddit_COMMUNITY_madoc.parquet -> COMMUNITY
    basename "$filepath" | sed 's/^reddit_//;s/_madoc\.parquet$//'
}

# Activate Python environment
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
pyenv activate python13

# Main processing
echo "========================================="
echo "  Dynamical Reputation Batch Processing"
echo "========================================="
echo ""
echo "Platform: ${PLATFORM}"
echo "Workers: ${WORKERS}"
echo "Output format: ${OUTPUT_FORMAT}"
echo ""
print_memory "Initial"
echo ""

# Find all Reddit parquet files, sorted by size (smallest first)
mapfile -t FILES < <(du -b "${DATA_DIR}"/reddit_*_madoc.parquet | sort -n | cut -f2)

TOTAL_FILES=${#FILES[@]}
COMPLETED=0
FAILED=0

echo "Found ${TOTAL_FILES} communities to process"
echo "========================================="
echo ""

# Process each file
for filepath in "${FILES[@]}"; do
    COMMUNITY=$(get_community_name "$filepath")
    FILESIZE=$(du -h "$filepath" | cut -f1)
    ((COMPLETED++))

    echo -e "${YELLOW}[${COMPLETED}/${TOTAL_FILES}]${NC} Processing: ${GREEN}${COMMUNITY}${NC} (${FILESIZE})"
    print_memory "Before"

    # Track start time
    START_TIME=$(date +%s)

    # Run the Python script
    if python "$PYTHON_SCRIPT" \
        --input "$filepath" \
        --platform "$PLATFORM" \
        --community "$COMMUNITY" \
        --workers "$WORKERS" \
        --output-format "$OUTPUT_FORMAT"; then

        END_TIME=$(date +%s)
        ELAPSED=$((END_TIME - START_TIME))

        echo -e "${GREEN}✓ Completed${NC} in ${ELAPSED}s"
        print_memory "After"
        echo ""
    else
        echo -e "${RED}✗ Failed${NC} - ${COMMUNITY}"
        ((FAILED++))
        print_memory "After failure"
        echo ""
    fi

    # Brief pause to allow memory cleanup
    sleep 2
done

echo "========================================="
echo "  Processing Complete"
echo "========================================="
echo "Total: ${TOTAL_FILES}"
echo -e "${GREEN}Succeeded: $((TOTAL_FILES - FAILED))${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Failed: ${FAILED}${NC}"
fi
print_memory "Final"
