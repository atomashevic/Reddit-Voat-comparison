
import sys
import os

# Add repo root to path
repo_root = "/home/atomasevic/socio/2025-Reddit-Voat"
sys.path.insert(0, repo_root)

try:
    from scripts.dynamical_reputation import dynamical_reputation_duckdb
    print("Import successful")
except ImportError as e:
    print(f"Import failed: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
