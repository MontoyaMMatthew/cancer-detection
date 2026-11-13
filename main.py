"""Run the whole pipeline from raw inputs to saved results. Run: python3 main.py

    download  ->  cohort  ->  split, train, predict, evaluate

Each stage lives in the `rcc` package; this file only connects them. Downloads are
resumable, and the download and cohort stages are skipped once data/processed/ exists.
"""

import pandas as pd

from rcc import config as C
from rcc.data import download as D
from rcc.data.cohort import build_cohort
from rcc.train import run

PROCESSED_FILES = ["cohort.parquet", "X_img.npy", "X_rna.npy"]


def download():
    """Fetch the two remote inputs. Table S1 (labels) ships with the project."""
    # TITAN first: it is small, and a missing Hugging Face login fails here
    # rather than after the 4 GB RNA download.
    print("TITAN features:", D.fetch_titan())
    # The committed manifest fixes exactly which GDC file is used for each patient.
    selected = pd.read_csv(C.MANIFESTS / "rna_selected.csv")
    print("RNA files:", D.fetch_rna(selected))


def main():
    if all((C.PROCESSED / name).exists() for name in PROCESSED_FILES):
        print(f"Using existing cohort in {C.PROCESSED}")
    else:
        download()
        build_cohort(labels="ricketts")
    run()  # writes outputs/results.csv and outputs/results.png
    print(f"Saved {C.ROOT / 'outputs' / 'results.csv'} and results.png")


if __name__ == "__main__":
    main()
