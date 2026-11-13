# cancer-detection

Multimodal classification of renal cell carcinoma subtypes (clear cell, papillary,
chromophobe) from TITAN slide embeddings and tumor RNA expression. Design documents
are in [`docs/`](docs/).

## Setup

```bash
conda activate envBio
pip install -e ".[dev]"
hf auth login          # once; needs approved access to MahmoodLab/TITAN
```

## Data

```bash
rcc download           # GDC manifests + RNA files (~4 GB) + TITAN features
# save Ricketts et al. 2018 Table S1 into data/raw/labels/  (manual download)
rcc cohort             # writes data/processed/
```

| Path              | Contents                                                                                       | In git |
| ----------------- | ---------------------------------------------------------------------------------------------- | ------ |
| `data/manifests/` | GDC file lists, selected RNA files, GDC release                                                | yes    |
| `data/raw/`       | RNA files, TITAN pickle, Table S1                                                              | no     |
| `data/processed/` | `cohort.parquet`, `X_img.npy`, `X_rna.npy`, `genes.csv`, `availability.csv`, `provenance.json` | no     |

TITAN features are released under CC-BY-NC-ND 4.0 and must not be redistributed, so
`data/raw/` and `data/processed/` are git-ignored.
