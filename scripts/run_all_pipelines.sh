#!/bin/bash
set -e

COMMUNITIES="funny gaming technology videos gifs pics"

# Run pipeline for each community
for comm in $COMMUNITIES; do
    echo "Running pipeline for $comm..."
    bash scripts/run_alternative_pipeline.sh "$comm"
done

echo "All community pipelines complete."

# Ensure global supporting inputs exist (used by the global summary plot)
echo "Computing event-period toxicity differences (heatmap input)..."
python scripts/compute_event_period_toxicity.py --results-root results --output-file results/global/event_period_toxicity_diff.csv

echo "Computing newcomer degree dynamics (global + per-community)..."
python scripts/compute_newcomer_degree_dynamics.py --networks-dir results/networks --labels-dir results/voat --output-dir results/voat

# Run Global Aggregation
echo "Running Global Aggregation..."
python scripts/aggregate_global_metrics.py --results-root results --output-dir results/global

# Run Global Summary Plot
echo "Plotting Global Summary..."
if [[ -d "paper" ]]; then
    OUTDIR="paper/figures/global"
else
    OUTDIR="figures/global"
fi
python scripts/plot_global_summary.py --input-file results/global/voat_global_aggregate.csv --output-dir "$OUTDIR"

echo "Global Summary Complete."
echo "Figure saved to ${OUTDIR}/voat_global_summary.png"


