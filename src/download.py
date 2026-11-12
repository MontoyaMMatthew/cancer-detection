"""rcc download: fetch TITAN slide embeddings (Hugging Face MahmoodLab/TITAN), GDC RNA STAR counts, and GDC clinical data, then package them.

Layout (under artifacts/data, see config.py):

    manifests/   rnaseq_manifest.txt (gdc-client format), rnaseq_files.tsv (file -> case map)
    raw/         titan/<pkl>, rnaseq/<file_id>/<file_name>, clinical.json
    processed/   titan_rcc.npz, slides.parquet, rnaseq.parquet, clinical.parquet

Every download is resumable: rerun the same command and finished files are skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from tqdm.auto import tqdm  # notebook widget in Jupyter, text bar in a terminal

import config as cfg

GDC_API = "https://api.gdc.cancer.gov"
MANIFEST_NAME = "rnaseq_manifest.txt"
FILE_MAP_NAME = "rnaseq_files.tsv"
CLINICAL_FIELDS = (
    "submitter_id,project.project_id,"
    "demographic.sex_at_birth,demographic.vital_status,demographic.days_to_death,"
    "diagnoses.age_at_diagnosis,diagnoses.primary_diagnosis,"
    "diagnoses.ajcc_pathologic_stage,diagnoses.days_to_last_follow_up"
)


# TITAN embeddings (Hugging Face)

def download_titan(out_dir: Path, repo: str = cfg.HF_REPO, filename: str = cfg.TITAN_FILE,
                   token: str | None = None, force: bool = False) -> Path:
    """Download only the embedding pickle from the gated repo (progress bar + resume built in).

    token=None falls back to $HF_TOKEN or the token saved by `hf auth login`.
    """
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(repo, filename=filename, local_dir=out_dir / "titan",
                           token=token, force_download=force)
    print(f"titan: {path}")
    return Path(path)


# GDC RNA-seq

def _gdc_hits(endpoint: str, filters: dict, fields: str) -> list[dict]:
    r = requests.post(f"{GDC_API}/{endpoint}", timeout=120,
                      json={"filters": filters, "fields": fields, "format": "JSON", "size": 20000})
    r.raise_for_status()
    return r.json()["data"]["hits"]


def build_rna_manifest(projects, manifest_dir: Path) -> pd.DataFrame:
    """Query GDC for open STAR-count files; write the gdc-client manifest and the file -> case map."""
    filters = {"op": "and", "content": [
        {"op": "in", "content": {"field": "cases.project.project_id", "value": list(projects)}},
        {"op": "=", "content": {"field": "data_type", "value": "Gene Expression Quantification"}},
        {"op": "=", "content": {"field": "analysis.workflow_type", "value": "STAR - Counts"}},
        {"op": "=", "content": {"field": "access", "value": "open"}},
    ]}
    hits = _gdc_hits("files", filters,
                     "file_id,file_name,md5sum,file_size,cases.submitter_id,"
                     "cases.project.project_id,cases.samples.submitter_id,cases.samples.sample_type")
    rows = []
    for h in hits:
        case = h["cases"][0]
        sample = case["samples"][0]
        rows.append({"id": h["file_id"], "filename": h["file_name"], "md5": h["md5sum"],
                     "size": h["file_size"], "case_id": case["submitter_id"],
                     "project_id": case["project"]["project_id"],
                     "sample_id": sample["submitter_id"], "sample_type": sample["sample_type"]})
    files = pd.DataFrame(rows).sort_values("id").reset_index(drop=True)

    manifest_dir.mkdir(parents=True, exist_ok=True)
    files[["id", "filename", "md5", "size"]].to_csv(manifest_dir / MANIFEST_NAME, sep="\t", index=False)
    files.to_csv(manifest_dir / FILE_MAP_NAME, sep="\t", index=False)
    print(f"manifest: {len(files)} files, {files['size'].sum() / 1e9:.2f} GB -> {manifest_dir / MANIFEST_NAME}")
    return files


def _rna_path(row, raw_dir: Path) -> Path:
    return raw_dir / "rnaseq" / row.id / row.filename  # same layout gdc-client uses


def _is_done(row, raw_dir: Path) -> bool:
    path = _rna_path(row, raw_dir)
    return path.exists() and path.stat().st_size == row.size


def _fetch_one(row, raw_dir: Path, bar: tqdm, retries: int = 4) -> None:
    path = _rna_path(row, raw_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    for attempt in range(retries):
        written = 0
        try:
            md5 = hashlib.md5()
            with requests.get(f"{GDC_API}/data/{row.id}", stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(part, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
                        md5.update(chunk)
                        written += len(chunk)
                        bar.update(len(chunk))
            if md5.hexdigest() != row.md5:
                raise IOError(f"md5 mismatch for {row.id}")
            part.rename(path)  # only complete, verified files get the final name
            return
        except (requests.RequestException, IOError):
            bar.update(-written)
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def download_rna(manifest: Path, raw_dir: Path, workers: int = 8, force: bool = False) -> None:
    """Download every file in the manifest. Rerun to resume: complete files are skipped."""
    files = pd.read_csv(manifest, sep="\t")
    todo = [r for r in files.itertuples() if force or not _is_done(r, raw_dir)]
    done_bytes = files["size"].sum() - sum(r.size for r in todo)
    print(f"rna: {len(files) - len(todo)}/{len(files)} files already present, {len(todo)} to download")
    failed = []
    with tqdm(total=int(files["size"].sum()), initial=int(done_bytes),
              unit="B", unit_scale=True, desc="rna") as bar:
        with ThreadPoolExecutor(workers) as pool:
            futures = {pool.submit(_fetch_one, r, raw_dir, bar): r for r in todo}
            for n, fut in enumerate(as_completed(futures), 1):
                if fut.exception():
                    failed.append(futures[fut].id)
                bar.set_postfix(files=f"{len(files) - len(todo) + n - len(failed)}/{len(files)}",
                                failed=len(failed))
    if failed:
        print(f"rna: {len(failed)} files failed; rerun the same command to retry them")


def rna_status(manifest: Path, raw_dir: Path) -> None:
    """Print how much of the manifest is on disk."""
    if not manifest.exists():
        print(f"rna: no manifest at {manifest} yet")
        return
    files = pd.read_csv(manifest, sep="\t")
    done = [_is_done(r, raw_dir) for r in files.itertuples()]
    got = files["size"][done].sum()
    print(f"rna: {sum(done)}/{len(files)} files, {got / 1e9:.2f}/{files['size'].sum() / 1e9:.2f} GB "
          f"({100 * got / files['size'].sum():.1f}%), {len(files) - sum(done)} missing")


# GDC clinical

def download_clinical(projects, raw_dir: Path) -> Path:
    """One API call: case-level clinical fields for the projects -> raw/clinical.json."""
    filters = {"op": "in", "content": {"field": "project.project_id", "value": list(projects)}}
    hits = _gdc_hits("cases", filters, CLINICAL_FIELDS)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / "clinical.json"
    path.write_text(json.dumps(hits))
    print(f"clinical: {len(hits)} cases -> {path}")
    return path


# Packaging

def package_clinical(raw_dir: Path, out_dir: Path) -> pd.DataFrame:
    rows = []
    for h in json.loads((raw_dir / "clinical.json").read_text()):
        dx = (h.get("diagnoses") or [{}])[0]
        demo = h.get("demographic") or {}
        rows.append({
            "case_id": h["submitter_id"],
            "project_id": h["project"]["project_id"],
            "site": h["submitter_id"][5:7],  # tissue source site code from the barcode
            "sex": demo.get("sex_at_birth"),
            "vital_status": demo.get("vital_status"),
            "days_to_death": demo.get("days_to_death"),
            "age_at_diagnosis_days": dx.get("age_at_diagnosis"),
            "primary_diagnosis": dx.get("primary_diagnosis"),
            "stage": dx.get("ajcc_pathologic_stage"),
            "days_to_last_follow_up": dx.get("days_to_last_follow_up"),
        })
    clinical = pd.DataFrame(rows).sort_values("case_id").reset_index(drop=True)
    clinical.to_parquet(out_dir / "clinical.parquet")
    print(f"clinical: {len(clinical)} cases -> {out_dir / 'clinical.parquet'}")
    return clinical


def package_titan(raw_dir: Path, out_dir: Path, clinical: pd.DataFrame,
                  filename: str = cfg.TITAN_FILE) -> None:
    """Keep the RCC slides from the pan-TCGA pickle -> titan_rcc.npz + slides.parquet."""
    with open(raw_dir / "titan" / filename, "rb") as f:
        data = pickle.load(f)
    if not (isinstance(data, dict) and {"filenames", "embeddings"} <= set(data)):
        keys = list(data)[:10] if isinstance(data, dict) else type(data)
        raise ValueError(f"unexpected TITAN pickle layout ({keys}); adapt package_titan")
    emb = pd.DataFrame({"slide_id": [str(s) for s in data["filenames"]]})
    emb["case_id"] = emb["slide_id"].str[:12]
    emb["row"] = np.arange(len(emb))
    emb = emb.merge(clinical[["case_id", "project_id"]], on="case_id")  # filters to RCC

    X = np.asarray(data["embeddings"])[emb["row"].to_numpy()].astype(np.float32)
    np.savez_compressed(out_dir / "titan_rcc.npz", X=X,
                        slide_id=emb["slide_id"].to_numpy(str), case_id=emb["case_id"].to_numpy(str))
    emb.drop(columns="row").to_parquet(out_dir / "slides.parquet")
    print(f"titan: {X.shape[0]} slides x {X.shape[1]} dims, {emb['case_id'].nunique()} cases "
          f"-> {out_dir / 'titan_rcc.npz'}")


def package_rna(raw_dir: Path, manifest_dir: Path, out_dir: Path) -> None:
    """Stack TPM from every downloaded file -> rnaseq.parquet (genes x files) + rnaseq_samples.parquet."""
    files = pd.read_csv(manifest_dir / FILE_MAP_NAME, sep="\t")
    have = [_is_done(r, raw_dir) for r in files.itertuples()]
    if not all(have):
        print(f"rna: packaging {sum(have)}/{len(files)} files; {len(files) - sum(have)} not downloaded yet")
    files = files[have].reset_index(drop=True)

    columns = {}
    for row in tqdm(list(files.itertuples()), desc="rna package"):
        df = pd.read_csv(_rna_path(row, raw_dir), sep="\t", comment="#",
                         usecols=["gene_id", "tpm_unstranded"], index_col="gene_id")
        columns[row.id] = df.loc[~df.index.str.startswith("N_"), "tpm_unstranded"].astype(np.float32)
    # rows = genes, columns = GDC file ids (unique; rnaseq_samples.parquet maps them to cases)
    pd.DataFrame(columns).to_parquet(out_dir / "rnaseq.parquet")
    files.rename(columns={"id": "file_id"}).drop(columns=["md5", "size"]).to_parquet(
        out_dir / "rnaseq_samples.parquet")
    print(f"rna: {len(columns)} files x {len(next(iter(columns.values())))} genes -> {out_dir / 'rnaseq.parquet'}")


# CLI entry points (called from main.py)

def run(args: argparse.Namespace) -> None:
    """rcc download"""
    manifest = args.gdc_manifest or cfg.MANIFEST_DIR / MANIFEST_NAME
    if args.status:
        titan = args.out_dir / "titan" / args.titan_file
        print(f"titan: {'present, %.2f GB' % (titan.stat().st_size / 1e9) if titan.exists() else 'missing'}")
        rna_status(manifest, args.out_dir)
        print(f"clinical: {'present' if (args.out_dir / 'clinical.json').exists() else 'missing'}")
        return
    if "titan" in args.source:
        download_titan(args.out_dir, args.hf_repo, args.titan_file, args.hf_token, args.force)
    if "clinical" in args.source:
        download_clinical(args.projects, args.out_dir)
    if "rna" in args.source:
        if args.gdc_manifest is None and (args.force or not manifest.exists()):
            build_rna_manifest(args.projects, cfg.MANIFEST_DIR)
        if not args.manifest_only:
            download_rna(manifest, args.out_dir, args.workers, args.force)
    if "labels" in args.source:
        print("labels: Ricketts 2018 Table S1 download is not implemented yet")


def package(args: argparse.Namespace) -> None:
    """rcc package"""
    args.out_dir.mkdir(parents=True, exist_ok=True)
    clinical = package_clinical(args.raw_dir, args.out_dir)
    if "titan" in args.source:
        package_titan(args.raw_dir, args.out_dir, clinical)
    if "rna" in args.source:
        package_rna(args.raw_dir, cfg.MANIFEST_DIR, args.out_dir)
