"""rcc: command-line interface for the RCC subtype classifier.

Pipeline (each command reads the previous command's outputs):

    rcc download   -> download.py      fetch TITAN embeddings, GDC RNA + clinical
    rcc package    -> download.py      raw downloads -> npz / parquet
    rcc cohort     -> cohort.py        one row per patient
    rcc split      -> splits.py        80/20 test split, 5-fold CV, site groups
    rcc train      -> heads.py         per-modality heads, OOF probabilities
    rcc fuse       -> fusion.py        late fusion, score locked test set once
    rcc disagree   -> disagreement.py  image-vs-RNA disagreement score
    rcc analyze    -> metrics.py, bootstrap.py, confounding.py, sensitivity.py

Image features are precomputed TITAN slide embeddings from Hugging Face
(MahmoodLab/TITAN); no tiling or patch encoding is done here.

Each module is expected to expose ``run(args: argparse.Namespace) -> None``.

Usage:
    python src/main.py <command> [options]
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

import config as cfg



def _dispatch(module_name: str, args: argparse.Namespace) -> int:
    """Import a pipeline module and call its ``run(args)``."""
    module = importlib.import_module(module_name)
    run = getattr(module, "run", None)
    if run is None:
        print(
            f"rcc {args.command}: {module_name}.py does not implement run(args) yet.",
            file=sys.stderr,
        )
        return 2
    run(args)
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    return _dispatch("download", args)


def cmd_package(args: argparse.Namespace) -> int:
    import download

    download.package(args)
    return 0


def cmd_cohort(args: argparse.Namespace) -> int:
    return _dispatch("cohort", args)


def cmd_split(args: argparse.Namespace) -> int:
    return _dispatch("splits", args)


def cmd_train(args: argparse.Namespace) -> int:
    return _dispatch("heads", args)


def cmd_fuse(args: argparse.Namespace) -> int:
    return _dispatch("fusion", args)


def cmd_disagree(args: argparse.Namespace) -> int:
    return _dispatch("disagreement", args)


def cmd_analyze(args: argparse.Namespace) -> int:
    status = 0
    for name in args.only or cfg.ANALYSES:
        status = max(status, _dispatch(name, args))
    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rcc",
        description="Multimodal (TITAN H&E embeddings + RNA) RCC subtype classifier.",
    )
    parser.add_argument("--seed", type=int, default=cfg.SEED, help="global random seed")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    # rcc download
    p = sub.add_parser(
        "download",
        help="fetch TITAN embeddings, GDC RNA, and GDC clinical data",
        description=(
            "Fetch TCGA_TITAN_features.pkl from the gated Hugging Face repo "
            "MahmoodLab/TITAN, open-access STAR counts (TPM) from GDC, and "
            "Ricketts et al. 2018 Table S1 subtype labels."
        ),
    )
    p.add_argument(
        "--source",
        nargs="+",
        choices=("titan", "rna", "clinical", "labels"),
        default=["titan", "clinical", "rna"],
        help="which sources to fetch (default: all)",
    )
    p.add_argument("--projects", nargs="+", default=list(cfg.PROJECTS), help="TCGA projects")
    p.add_argument("--out-dir", type=Path, default=cfg.RAW_DIR, help="raw data directory")
    p.add_argument(
        "--hf-token",
        default=os.environ.get(cfg.HF_TOKEN_ENV),
        help="Hugging Face token for the gated TITAN repo (default: $HF_TOKEN)",
    )
    p.add_argument("--hf-repo", default=cfg.HF_REPO, help="Hugging Face repo id")
    p.add_argument(
        "--titan-file", default=cfg.TITAN_FILE, help="embedding file in the HF repo"
    )
    p.add_argument("--gdc-manifest", type=Path, help="optional pre-built GDC manifest")
    p.add_argument("--force", action="store_true", help="re-download existing files")
    p.add_argument("--manifest-only", action="store_true", help="write the GDC manifest, download nothing")
    p.add_argument("--status", action="store_true", help="show what is on disk, download nothing")
    p.add_argument("--workers", type=int, default=8, help="parallel GDC downloads")
    p.set_defaults(func=cmd_download)

    # rcc package
    p = sub.add_parser(
        "package",
        help="turn raw downloads into npz / parquet",
        description=(
            "Write titan_rcc.npz, slides.parquet, rnaseq.parquet, rnaseq_samples.parquet, "
            "and clinical.parquet from the raw downloads."
        ),
    )
    p.add_argument("--source", nargs="+", choices=("titan", "rna"), default=["titan", "rna"])
    p.add_argument("--raw-dir", type=Path, default=cfg.RAW_DIR, help="output of `rcc download`")
    p.add_argument("--out-dir", type=Path, default=cfg.PROCESSED_DIR, help="packaged output directory")
    p.set_defaults(func=cmd_package)

    # rcc cohort
    p = sub.add_parser(
        "cohort",
        help="join modalities by patient, map labels, apply exclusions",
        description=(
            "Average TITAN slide embeddings per patient, load primary-tumor RNA as "
            "log2(TPM+1), map reviewed labels to 3 classes, and inner-join on patient ID."
        ),
    )
    p.add_argument("--raw-dir", type=Path, default=cfg.RAW_DIR, help="output of `rcc download`")
    p.add_argument("--out-dir", type=Path, default=cfg.PROCESSED_DIR, help="cohort output directory")
    p.add_argument(
        "--slide-agg",
        choices=("mean",),
        default="mean",
        help="how to aggregate multiple slides per patient",
    )
    p.add_argument(
        "--min-tpm", type=float, default=1.0, help="low-expression gene filter threshold"
    )
    p.add_argument(
        "--require-clinical",
        action="store_true",
        help="drop patients missing age at diagnosis or sex",
    )
    p.set_defaults(func=cmd_cohort)

    # rcc split
    p = sub.add_parser(
        "split",
        help="stratified 80/20 test split, 5-fold CV, site groups",
        description="Write splits.json; every later command reads it and nothing re-splits.",
    )
    p.add_argument(
        "--cohort", type=Path, default=cfg.COHORT_PATH, help="cohort table"
    )
    p.add_argument("--test-size", type=float, default=0.2, help="locked test fraction")
    p.add_argument("--folds", type=int, default=5, help="CV folds on the dev set")
    p.add_argument("--out", type=Path, default=cfg.SPLITS_PATH, help="output file")
    p.set_defaults(func=cmd_split)

    # rcc train
    p = sub.add_parser(
        "train",
        help="fit per-modality classifier heads, save OOF probabilities",
        description=(
            "image: standardize + logistic regression on 768-d TITAN embeddings. "
            "rna: standardize + PCA + L2 logistic regression. Fit inside each CV fold."
        ),
    )
    p.add_argument(
        "--modality",
        nargs="+",
        choices=cfg.MODALITIES,
        default=list(cfg.MODALITIES),
        help="which heads to train (default: both)",
    )
    p.add_argument("--data-dir", type=Path, default=cfg.PROCESSED_DIR, help="output of `rcc cohort`")
    p.add_argument("--splits", type=Path, default=cfg.SPLITS_PATH)
    p.add_argument("--out-dir", type=Path, default=cfg.OUTPUT_DIR, help="OOF probs + model dir")
    p.add_argument("--pca-components", type=int, default=50, help="RNA PCA components")
    p.add_argument(
        "--C", type=float, nargs="+", default=[0.01, 0.1, 1.0, 10.0], help="LR inverse-regularization grid"
    )
    p.add_argument(
        "--class-weight",
        choices=("none", "balanced"),
        default="balanced",
        help="class weighting for the heads",
    )
    p.add_argument(
        "--group-by",
        choices=("none", "site"),
        default="none",
        help="'site' runs site-held-out folds instead of stratified folds",
    )
    p.set_defaults(func=cmd_train)

    # rcc fuse
    p = sub.add_parser(
        "fuse",
        help="late fusion on OOF probabilities, score locked test set once",
        description=(
            "Fit a linear fusion layer on stacked OOF image/RNA probabilities, refit "
            "heads on all dev patients, and score the locked 20%% test set once."
        ),
    )
    p.add_argument("--data-dir", type=Path, default=cfg.PROCESSED_DIR)
    p.add_argument("--splits", type=Path, default=cfg.SPLITS_PATH)
    p.add_argument("--oof-dir", type=Path, default=cfg.OUTPUT_DIR, help="output of `rcc train`")
    p.add_argument("--out", type=Path, default=cfg.PREDS_PATH)
    p.add_argument(
        "--score-test",
        action="store_true",
        help="score the locked test set (do this once, after model selection)",
    )
    p.set_defaults(func=cmd_fuse)

    # rcc disagree
    p = sub.add_parser(
        "disagree",
        help="score image-vs-RNA disagreement and flag cases for review",
        description=(
            "Jensen-Shannon divergence between image and RNA class probabilities; "
            "the review threshold is chosen on dev folds only."
        ),
    )
    p.add_argument("--preds", type=Path, default=cfg.PREDS_PATH)
    p.add_argument("--splits", type=Path, default=cfg.SPLITS_PATH)
    p.add_argument("--out", type=Path, default=cfg.DISAGREEMENT_PATH)
    p.add_argument(
        "--flag-rate",
        type=float,
        default=0.1,
        help="target fraction of dev patients flagged when picking the threshold",
    )
    p.set_defaults(func=cmd_disagree)

    # rcc analyze
    p = sub.add_parser(
        "analyze",
        help="metrics, bootstrap CI, confounding, sensitivity reports",
        description="Write tables and figures to the reports directory.",
    )
    p.add_argument(
        "--only", nargs="+", choices=cfg.ANALYSES, help="run a subset of analyses (default: all)"
    )
    p.add_argument("--preds", type=Path, default=cfg.PREDS_PATH)
    p.add_argument("--disagreement", type=Path, default=cfg.DISAGREEMENT_PATH)
    p.add_argument("--cohort", type=Path, default=cfg.COHORT_PATH)
    p.add_argument("--splits", type=Path, default=cfg.SPLITS_PATH)
    p.add_argument("--out-dir", type=Path, default=cfg.REPORTS_DIR)
    p.add_argument("--n-bootstrap", type=int, default=1000, help="paired bootstrap resamples")
    p.set_defaults(func=cmd_analyze)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
