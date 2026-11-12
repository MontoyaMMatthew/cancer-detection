"""Shared constants: seed, paths, class map. Imported by every module."""

from __future__ import annotations

from pathlib import Path

SEED = 42

# TCGA projects and subtype classes
PROJECTS = ("TCGA-KIRC", "TCGA-KIRP", "TCGA-KICH")
CLASSES = ("clear_cell", "papillary", "chromophobe")
CLASS_TO_INDEX = {name: i for i, name in enumerate(CLASSES)}

MODALITIES = ("image", "rna")
ANALYSES = ("metrics", "bootstrap", "confounding", "sensitivity")

# TITAN embeddings (gated Hugging Face repo)
HF_REPO = "MahmoodLab/TITAN"
TITAN_FILE = "TCGA_TITAN_features.pkl"
HF_TOKEN_ENV = "HF_TOKEN"

# Directories
ARTIFACTS_DIR = Path("artifacts")  # gitignored, except data/manifests
DATA_DIR = ARTIFACTS_DIR / "data"
MANIFEST_DIR = DATA_DIR / "manifests"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = Path("outputs")
REPORTS_DIR = Path("reports")

# Files passed between commands
COHORT_PATH = PROCESSED_DIR / "cohort.parquet"
SPLITS_PATH = PROCESSED_DIR / "splits.json"
PREDS_PATH = OUTPUT_DIR / "preds.parquet"
DISAGREEMENT_PATH = OUTPUT_DIR / "disagreement.parquet"
