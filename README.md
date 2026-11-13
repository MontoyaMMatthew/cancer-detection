# cancer-detection

Multimodal classification of renal cell carcinoma (RCC) subtypes — clear cell,
papillary, chromophobe — from TITAN slide embeddings and tumor RNA expression.
One prediction per patient; the question is whether fusing the two modalities beats
the best single modality. Design memos are in [`docs/`](docs/).

**Status:** data download, cohort assembly and a first train/evaluate pass run end to
end on real TCGA data. Evaluation is still a prototype (single 80/20 split, F1 only).

> The `submissions` branch holds the course-submission layout (`main.py`,
> `requirements.txt`, flowchart, professor's README template). `main` is the working branch.

## Setup

Developed on Python 3.14.

```bash
conda activate envBio
pip install -e ".[dev]"
```

## Data access

| Source | What | Access |
| --- | --- | --- |
| [GDC](https://portal.gdc.cancer.gov/) (TCGA-KIRC / KIRP / KICH) | RNA STAR-Counts files, case and slide metadata | Open access, no account needed |
| [MahmoodLab/TITAN](https://huggingface.co/MahmoodLab/TITAN) on Hugging Face | `TCGA_TITAN_features.pkl`, precomputed slide embeddings | **Gated**, see below |
| [Ricketts et al. 2018](https://doi.org/10.1016/j.celrep.2018.03.075), Table S1 | Reviewed subtype labels | Included: `data/raw/labels/mmc2.xlsx` |

TITAN access, once per machine:

1. Create a Hugging Face account whose primary email is institutional (Gmail is denied).
2. Request access on the [TITAN model page](https://huggingface.co/MahmoodLab/TITAN) and wait for approval.
3. Run `hf auth login` and paste a read token (or set `HF_TOKEN`).

## Run

```bash
rcc download   # GDC manifests + RNA files (~4 GB) + TITAN features
rcc cohort     # join by patient, write data/processed/
rcc run        # train image, RNA and fusion heads; write outputs/
```

`rcc download` is resumable. `rcc cohort --labels project` builds a provisional cohort
from GDC project codes for pipeline testing only; it is not used for reported results.

## Where things are saved

| Path | Contents | In git |
| --- | --- | --- |
| `data/manifests/` | GDC file lists, the selected RNA file per patient, GDC release | yes |
| `data/raw/labels/mmc2.xlsx` | Ricketts Table S1 | yes |
| `data/raw/rna/`, `data/raw/titan/` | RNA files, TITAN pickle | no |
| `data/processed/` | `cohort.parquet`, `X_img.npy`, `X_rna.npy`, `genes.csv`, `availability.csv`, `exclusions.csv`, `provenance.json` | no |
| `outputs/results.csv` | Test-set macro-F1 and per-class F1 for image, RNA and fusion | yes |
| `outputs/results.png` | Bar chart of the same table | yes |

TITAN features are released under CC-BY-NC-ND 4.0 and must not be redistributed, so
the raw downloads and `data/processed/` stay git-ignored.

## Current results

Cohort: 800 patients with a reviewed label, a TITAN embedding and RNA (464 clear cell,
255 papillary, 81 chromophobe) out of 941 candidates. Held-out test set: 160 patients.

| model | macro-F1 | clear cell | papillary | chromophobe |
| --- | --- | --- | --- | --- |
| image | 0.944 | 0.962 | 0.961 | 0.909 |
| rna | 0.919 | 0.931 | 0.891 | 0.933 |
| fusion | 0.945 | 0.957 | 0.941 | 0.938 |

One split, no confidence intervals yet: the image-vs-fusion gap (0.001) is not evidence
that fusion helps. The planned evaluation is in
[`docs/TARGET_AND_EVAL_MEMO.md`](docs/TARGET_AND_EVAL_MEMO.md).

## Layout

```
rcc/config.py          seed, paths, class map
rcc/data/download.py   fetch and load TITAN, GDC RNA, labels
rcc/data/cohort.py     join by patient, write data/processed/
rcc/train.py           heads, late fusion, evaluation, outputs
rcc/cli.py             rcc download | cohort | run
docs/                  dataset, target and evaluation memos; architecture diagrams
papers/                reference papers
```
