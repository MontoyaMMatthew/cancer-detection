"""Command line: `rcc download`, `rcc cohort`."""

from __future__ import annotations

import argparse

from rcc import config as C


def cmd_download(args):
    from rcc.data import download as D

    release = D.fetch_gdc_release()
    print(f"GDC {release['data_release']}")
    cases = D.fetch_cases()
    print(f"Cases: {len(cases)}  {cases['project_id'].value_counts().to_dict()}")
    rna = D.fetch_rna_manifest()
    slides = D.fetch_slide_manifest()
    sel = D.select_rna_files(rna)
    print(
        f"RNA files: {len(rna)} listed, {len(sel)} primary-tumor patients selected "
        f"({sel['size'].sum() / 1e9:.2f} GB)"
    )
    print(
        f"Diagnostic slides in GDC: {len(slides)} files, "
        f"{slides['patient_id'].nunique()} patients (metadata only)"
    )
    if not args.skip_rna:
        print("RNA download:", D.fetch_rna(sel, workers=args.workers))
    if not args.skip_titan:
        print("TITAN features:", D.fetch_titan())
    try:
        print("Labels file:", D.fetch_labels())
    except FileNotFoundError as e:
        print(f"\nLabels still needed:\n{e}")


def cmd_cohort(args):
    from rcc.data.cohort import build_cohort

    build_cohort(labels=args.labels)


def cmd_run(args):
    from rcc.train import run

    run()


def main(argv=None):
    ### top-level subparser
    p = argparse.ArgumentParser(prog="rcc", description=f"Data root: {C.DATA}")
    sub = p.add_subparsers(dest="command", required=True)

    ### download subparsers
    d = sub.add_parser(
        "download", help="fetch GDC manifests, RNA files and TITAN features"
    )
    d.add_argument(
        "--skip-rna", action="store_true", help="manifests only, no RNA files"
    )
    d.add_argument(
        "--skip-titan", action="store_true", help="skip the Hugging Face download"
    )
    d.add_argument("--workers", type=int, default=8, help="parallel RNA downloads")
    d.set_defaults(func=cmd_download)

    ### Cohort subparsers
    c = sub.add_parser("cohort", help="join by patient and write data/processed/")
    c.add_argument(
        "--labels",
        choices=["ricketts", "project"],
        default="ricketts",
        help="'project' uses GDC project codes: provisional, for testing only",
    )
    c.set_defaults(func=cmd_cohort)

    r = sub.add_parser(
        "run", help="train heads, save outputs/results.csv and results.png"
    )
    r.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
