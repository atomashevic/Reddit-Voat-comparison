#!/bin/bash
set -e

COMMUNITIES="funny gaming technology videos gifs pics"

# Run pipeline for each community
for comm in $COMMUNITIES; do
    echo "Running pipeline for $comm..."
    bash scripts/run_alternative_pipeline.sh "$comm"
done

echo "All community pipelines complete."

# Run Global Aggregation
echo "Running Global Aggregation..."
python scripts/aggregate_global_metrics.py --results-root results --output-dir results/global

# Run Global Summary Plot
echo "Plotting Global Summary..."
python scripts/plot_global_summary.py --input-file results/global/voat_global_aggregate.csv --output-dir figures/global

echo "Global Summary Complete."
echo "Figure saved to figures/global/voat_global_summary.png"


