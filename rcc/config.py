"""Seed, paths, and class map. Imported by every module."""

from __future__ import annotations

import os
from pathlib import Path

SEED = 42

# Repo root; override with RCC_ROOT to keep data on another disk.
ROOT = Path(os.environ.get("RCC_ROOT", Path(__file__).resolve().parents[1]))
DATA = ROOT / "data"
MANIFESTS = DATA / "manifests"  # small, committed: what was requested from GDC
RAW = DATA / "raw"  # git-ignored: downloads exactly as received
PROCESSED = DATA / "processed"  # git-ignored: model-ready arrays and tables

RNA_DIR = RAW / "rna"
TITAN_DIR = RAW / "titan"
LABELS_DIR = RAW / "labels"

# --- sources -----------------------------------------------------------------
GDC_API = "https://api.gdc.cancer.gov"
PROJECTS = ["TCGA-KIRC", "TCGA-KIRP", "TCGA-KICH"]
TITAN_REPO = "MahmoodLab/TITAN"
TITAN_FILE = "TCGA_TITAN_features.pkl"
RICKETTS_URL = "https://doi.org/10.1016/j.celrep.2018.03.075"

# --- target ------------------------------------------------------------------
CLASSES = ["clear_cell", "papillary", "chromophobe"]
# Only used for the provisional `--labels project` mode and for audit columns.
# The project code is never a model feature.
PROJECT_TO_CLASS = {
    "TCGA-KIRC": "clear_cell",
    "TCGA-KIRP": "papillary",
    "TCGA-KICH": "chromophobe",
}
# Ricketts et al. (2018) publication-cohort totals, used as a sanity check.
RICKETTS_EXPECTED = {"clear_cell": 488, "papillary": 274, "chromophobe": 81}
# Set to the exact Table S1 column name to skip auto-detection.
LABEL_COLUMN = os.environ.get("RCC_LABEL_COLUMN") or None

# --- RNA ---------------------------------------------------------------------
RNA_VALUE_COLUMN = "tpm_unstranded"
# Annotation-based filter (not data-dependent, so safe before splitting).
# Expression-level filtering, scaling and PCA belong inside training folds.
PROTEIN_CODING_ONLY = True
