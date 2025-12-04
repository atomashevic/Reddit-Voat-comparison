#!/bin/bash
set -e

COMMUNITIES="funny gaming technology videos gifs pics"

mkdir -p results/reddit results/voat results/compare results/global
mkdir -p figures/reddit figures/voat figures/compare figures/global

for comm in $COMMUNITIES; do
    echo "Processing $comm..."
    
    # Create destination directories
    mkdir -p results/reddit/$comm
    mkdir -p results/voat/$comm
    mkdir -p results/compare/$comm
    mkdir -p figures/compare/$comm
    mkdir -p figures/reddit/$comm
    mkdir -p figures/voat/$comm

    # Source base
    SRC="results/alternative/$comm"
    
    # Move Reddit results
    if [ -d "$SRC/reddit" ]; then
        cp -r $SRC/reddit/* results/reddit/$comm/ 2>/dev/null || true
    fi
    
    # Move Voat results
    if [ -d "$SRC/voat" ]; then
        cp -r $SRC/voat/* results/voat/$comm/ 2>/dev/null || true
    fi
    
    # Move Compare results
    if [ -d "$SRC/compare" ]; then
        cp -r $SRC/compare/* results/compare/$comm/ 2>/dev/null || true
    fi
    
    # Move Network metrics
    if [ -d "$SRC/networks/reddit" ]; then
        cp $SRC/networks/reddit/*.csv results/reddit/$comm/ 2>/dev/null || true
    fi
    if [ -d "$SRC/networks/voat" ]; then
        cp $SRC/networks/voat/*.csv results/voat/$comm/ 2>/dev/null || true
    fi
    
    # Move Figures
    if [ -d "$SRC/figures" ]; then
        cp $SRC/figures/*.png figures/compare/$comm/ 2>/dev/null || true
    fi
done

# After moving, we can remove results/alternative if we are confident, 
# but I will leave it for now or move it to backup/results/alternative_old
mkdir -p backup/results
mv results/alternative backup/results/alternative_old


