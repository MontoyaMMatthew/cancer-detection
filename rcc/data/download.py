"""Fetch and load the three inputs: TITAN slide embeddings, GDC RNA, labels.

fetch_* functions touch the network and write under data/raw or data/manifests.
load_* / map_* functions only read local files and return arrays or tables.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from rcc import config as C

BARCODE = re.compile(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}")
# Slide barcode: TCGA-XX-XXXX-01Z-00-DX1 (DX = diagnostic, TS/BS/MS = frozen sections).
SLIDE_TYPE = r"-\d{2}[A-Z]?-\d{2}-(?:DX|TS|BS|MS)"
DIAGNOSTIC = r"-\d{2}[A-Z]?-\d{2}-DX"


def patient_of(identifier: str) -> str | None:
    """12-character patient barcode at the start of any TCGA identifier."""
    m = BARCODE.match(str(identifier).strip().upper())
    return m.group(0) if m else None


# =============================================================================
# GDC
# =============================================================================
def _in(field, values):
    return {"op": "in", "content": {"field": field, "value": list(values)}}


def _and(*clauses):
    return {"op": "and", "content": list(clauses)}


def _post(url, payload, tries=4):
    err = None
    for attempt in range(tries):
        try:
            r = requests.post(url, json=payload, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # network hiccup or 5xx: back off and retry
            err = e
            time.sleep(2**attempt)
    raise RuntimeError(f"GDC request failed after {tries} tries: {err}")


def gdc_query(
    endpoint: str, filters: dict, fields: list[str], page: int = 1000
) -> list[dict]:
    """All hits for a GDC `files` or `cases` query, following pagination."""
    hits, start = [], 0
    while True:
        data = _post(
            f"{C.GDC_API}/{endpoint}",
            {
                "filters": filters,
                "fields": ",".join(fields),
                "format": "JSON",
                "size": page,
                "from": start,
            },
        )["data"]
        hits += data["hits"]
        start += len(data["hits"])
        if not data["hits"] or start >= data["pagination"]["total"]:
            return hits


def fetch_gdc_release() -> dict:
    """Record which GDC data release the manifests came from."""
    r = requests.get(f"{C.GDC_API}/status", timeout=60)
    r.raise_for_status()
    info = {
        "data_release": r.json().get("data_release"),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.MANIFESTS.mkdir(parents=True, exist_ok=True)
    (C.MANIFESTS / "gdc_release.json").write_text(json.dumps(info, indent=2))
    return info


def fetch_cases() -> pd.DataFrame:
    """One row per patient in the three projects: project, sex, age at diagnosis."""
    hits = gdc_query(
        "cases",
        _and(_in("project.project_id", C.PROJECTS)),
        [
            "submitter_id",
            "project.project_id",
            "demographic.gender",
            "demographic.age_at_index",
            "diagnoses.age_at_diagnosis",
        ],
    )
    rows = []
    for h in hits:
        demo = h.get("demographic") or {}
        if isinstance(demo, list):
            demo = demo[0] if demo else {}
        days = [
            d["age_at_diagnosis"]
            for d in (h.get("diagnoses") or [])
            if d.get("age_at_diagnosis") is not None
        ]
        age = min(days) / 365.25 if days else demo.get("age_at_index")
        rows.append(
            {
                "patient_id": h["submitter_id"],
                "project_id": (h.get("project") or {}).get("project_id"),
                "sex": demo.get("gender"),
                "age_at_diagnosis": None if age is None else round(float(age), 1),
            }
        )
    df = pd.DataFrame(rows).sort_values("patient_id").reset_index(drop=True)
    C.MANIFESTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(C.MANIFESTS / "cases.csv", index=False)
    return df


_FILE_FIELDS = [
    "file_id",
    "file_name",
    "md5sum",
    "file_size",
    "access",
    "cases.submitter_id",
    "cases.project.project_id",
    "cases.samples.submitter_id",
    "cases.samples.sample_type",
]


def _flatten_files(hits: list[dict]) -> pd.DataFrame:
    rows = []
    for h in hits:
        for case in h.get("cases") or [{}]:
            for s in case.get("samples") or [{}]:
                rows.append(
                    {
                        "file_id": h["file_id"],
                        "file_name": h["file_name"],
                        "md5": h.get("md5sum"),
                        "size": h.get("file_size"),
                        "patient_id": case.get("submitter_id"),
                        "project_id": (case.get("project") or {}).get("project_id"),
                        "sample_id": s.get("submitter_id"),
                        "sample_type": s.get("sample_type"),
                    }
                )
    cols = [
        "file_id",
        "file_name",
        "md5",
        "size",
        "patient_id",
        "project_id",
        "sample_id",
        "sample_type",
    ]
    return (
        pd.DataFrame(rows, columns=cols)
        .sort_values(["patient_id", "sample_id", "file_id"])
        .reset_index(drop=True)
    )


def fetch_rna_manifest() -> pd.DataFrame:
    """Every open-access STAR-Counts file in the three projects (metadata only)."""
    df = _flatten_files(
        gdc_query(
            "files",
            _and(
                _in("cases.project.project_id", C.PROJECTS),
                _in("data_type", ["Gene Expression Quantification"]),
                _in("analysis.workflow_type", ["STAR - Counts"]),
                _in("access", ["open"]),
            ),
            _FILE_FIELDS,
        )
    )
    C.MANIFESTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(C.MANIFESTS / "rna_files.csv", index=False)
    return df


def fetch_slide_manifest() -> pd.DataFrame:
    """Diagnostic H&E slide files in GDC (metadata only; nothing is downloaded).

    Used for the availability audit: which patients have a diagnostic slide,
    independent of whether TITAN published an embedding for it.
    """
    df = _flatten_files(
        gdc_query(
            "files",
            _and(
                _in("cases.project.project_id", C.PROJECTS),
                _in("data_type", ["Slide Image"]),
                _in("experimental_strategy", ["Diagnostic Slide"]),
            ),
            _FILE_FIELDS,
        )
    )
    df = df.drop_duplicates("file_id").reset_index(drop=True)
    df.to_csv(C.MANIFESTS / "slide_files.csv", index=False)
    return df


def select_rna_files(rna_files: pd.DataFrame) -> pd.DataFrame:
    """One primary-tumor RNA file per patient, chosen deterministically.

    Rule: keep sample_type == "Primary Tumor"; if a patient has several,
    take the first by (sample barcode, file id). `n_candidates` records how
    many there were so the choice is auditable.
    """
    tumor = rna_files[rna_files["sample_type"] == "Primary Tumor"]
    tumor = tumor.sort_values(["patient_id", "sample_id", "file_id"])
    n = tumor.groupby("patient_id")["file_id"].nunique().rename("n_candidates")
    sel = tumor.drop_duplicates("patient_id").merge(n, on="patient_id")
    sel = sel.reset_index(drop=True)
    C.MANIFESTS.mkdir(parents=True, exist_ok=True)
    sel.to_csv(C.MANIFESTS / "rna_selected.csv", index=False)
    # Same selection in gdc-client manifest format, as an alternative downloader.
    (
        sel.rename(columns={"file_id": "id", "file_name": "filename"})
        .assign(state="released")[["id", "filename", "md5", "size", "state"]]
        .to_csv(C.MANIFESTS / "rna_gdc_manifest.txt", sep="\t", index=False)
    )
    return sel


def rna_path(file_id: str) -> Path:
    return C.RNA_DIR / f"{file_id}.tsv"


def _download_one(file_id: str, md5: str, size: int, tries: int = 4) -> str:
    dest = rna_path(file_id)
    if dest.exists() and dest.stat().st_size == int(size):
        return "cached"
    tmp = dest.with_suffix(".tsv.part")
    err = None
    for attempt in range(tries):
        try:
            digest = hashlib.md5()
            with requests.get(
                f"{C.GDC_API}/data/{file_id}", stream=True, timeout=180
            ) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                        digest.update(chunk)
            if md5 and digest.hexdigest() != md5:
                raise IOError("md5 mismatch")
            os.replace(tmp, dest)
            return "downloaded"
        except Exception as e:
            err = e
            time.sleep(2**attempt)
    raise RuntimeError(f"{file_id}: {err}")


def fetch_rna(selected: pd.DataFrame, workers: int = 8) -> dict:
    """Download the selected RNA files. Resumable: finished files are skipped."""
    C.RNA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from tqdm.auto import tqdm
    except ImportError:  # progress bar is optional
        tqdm = lambda it, **k: it
    counts, failed = {"cached": 0, "downloaded": 0}, []
    with ThreadPoolExecutor(workers) as pool:
        jobs = {
            pool.submit(_download_one, r.file_id, r.md5, r.size): r.file_id
            for r in selected.itertuples()
        }
        for job in tqdm(as_completed(jobs), total=len(jobs), desc="RNA files"):
            try:
                counts[job.result()] += 1
            except Exception as e:
                failed.append(str(e))
    if failed:
        raise RuntimeError(
            f"{len(failed)} RNA downloads failed (re-run to resume). "
            f"First: {failed[0]}"
        )
    return counts


def read_star_counts(path) -> pd.DataFrame:
    """Gene rows of one GDC STAR-Counts file (drops the N_* summary rows)."""
    df = pd.read_csv(
        path,
        sep="\t",
        comment="#",
        usecols=["gene_id", "gene_name", "gene_type", C.RNA_VALUE_COLUMN],
    )
    return df[~df["gene_id"].str.startswith("N_")].reset_index(drop=True)


def load_rna(selected: pd.DataFrame):
    """log2(TPM + 1) matrix for the selected files.

    Returns (X [n_patients, n_genes] float32, genes table, patient_ids), with
    rows in the order of `selected`.
    """
    genes, keep, X = None, None, None
    for i, r in enumerate(selected.itertuples()):
        df = read_star_counts(rna_path(r.file_id))
        if genes is None:
            genes = df[["gene_id", "gene_name", "gene_type"]]
            keep = (
                (genes["gene_type"] == "protein_coding").to_numpy()
                if C.PROTEIN_CODING_ONLY
                else np.ones(len(genes), bool)
            )
            X = np.empty((len(selected), int(keep.sum())), dtype=np.float32)
        elif not df["gene_id"].equals(genes["gene_id"]):
            df = df.set_index("gene_id").reindex(genes["gene_id"]).reset_index()
        tpm = df[C.RNA_VALUE_COLUMN].to_numpy(dtype=np.float64)[keep]
        if np.isnan(tpm).any():
            raise ValueError(f"{r.file_id}: missing TPM values after aligning genes")
        X[i] = np.log2(tpm + 1.0)
    return X, genes[keep].reset_index(drop=True), selected["patient_id"].tolist()


# =============================================================================
# TITAN slide embeddings (Hugging Face, gated)
# =============================================================================
def fetch_titan() -> Path:
    """Download TCGA_TITAN_features.pkl only (not the model weights)."""
    from huggingface_hub import hf_hub_download

    C.TITAN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        return Path(
            hf_hub_download(C.TITAN_REPO, filename=C.TITAN_FILE, local_dir=C.TITAN_DIR)
        )
    except Exception as e:
        if (
            type(e).__name__
            in {"GatedRepoError", "LocalTokenNotFoundError", "RepositoryNotFoundError"}
            or "401" in str(e)
            or "403" in str(e)
        ):
            raise RuntimeError(
                "Hugging Face refused the download. TITAN is a gated repo:\n"
                f"  1. Request access at https://huggingface.co/{C.TITAN_REPO} with an account "
                "whose primary email is your JHU address (Gmail is denied).\n"
                "  2. After approval run `hf auth login` (or `huggingface-cli login`) "
                "in this environment, or set HF_TOKEN.\n"
                f"Original error: {type(e).__name__}: {e}"
            ) from e
        raise


def _to_numpy(v):
    if hasattr(v, "detach"):  # torch tensor
        v = v.detach().cpu().float().numpy()
    return np.asarray(v)


def _is_numeric(v) -> bool:
    try:
        a = _to_numpy(v)
    except Exception:
        return False
    return a.dtype.kind in "fiu" and a.ndim >= 1 and a.size > 1


def _is_strseq(v) -> bool:
    if not isinstance(v, (list, tuple, np.ndarray, pd.Series, pd.Index)) or len(v) == 0:
        return False
    return all(isinstance(x, str) for x in list(v)[:50])


def describe(obj, depth: int = 0, max_depth: int = 3) -> str:
    """Human-readable outline of a pickled object, for inspecting the .pkl."""
    pad = "  " * depth
    if isinstance(obj, dict):
        lines = [f"{pad}dict with {len(obj)} keys"]
        if depth < max_depth:
            for k in list(obj)[:6]:
                lines.append(f"{pad}  [{k!r}] ->")
                lines.append(describe(obj[k], depth + 2, max_depth))
            if len(obj) > 6:
                lines.append(f"{pad}  ... {len(obj) - 6} more keys")
        return "\n".join(lines)
    if isinstance(obj, pd.DataFrame):
        return f"{pad}DataFrame {obj.shape}, columns={list(obj.columns)[:8]}"
    if _is_numeric(obj):
        a = _to_numpy(obj)
        return f"{pad}{type(obj).__name__} shape={a.shape} dtype={a.dtype}"
    if isinstance(obj, (list, tuple)):
        head = repr(obj[0])[:80] if len(obj) else ""
        return f"{pad}{type(obj).__name__} len={len(obj)} first={head}"
    return f"{pad}{type(obj).__name__}: {repr(obj)[:80]}"


def parse_titan(obj):
    """(slide_ids, embeddings [n, d]) from the pickle, whatever its layout.

    The layout is undocumented, so this accepts the plausible ones:
      - dict with a 2-D array under one key and a same-length list of ids under another
      - dict mapping id -> vector
      - dict of such dicts (e.g. grouped by project), merged
      - (ids, array) pair, list of (id, vector) pairs, or a DataFrame
    Anything else raises with an outline of the object so it can be handled explicitly.
    """
    if isinstance(obj, pd.DataFrame):
        ids = None
        if _is_strseq(obj.index):
            ids = list(obj.index)
        else:
            for c in obj.columns:
                if _is_strseq(obj[c]) and patient_of(obj[c].iloc[0]):
                    ids = list(obj[c])
                    break
        num = obj.select_dtypes("number")
        if ids is not None and num.shape[1] >= 8:
            return ids, num.to_numpy(np.float32)
        for c in obj.columns:
            if ids is not None and _is_numeric(obj[c].iloc[0]):
                return ids, np.stack([_to_numpy(v).reshape(-1) for v in obj[c]]).astype(
                    np.float32
                )

    if isinstance(obj, dict) and obj:
        mats = {
            k: _to_numpy(v)
            for k, v in obj.items()
            if _is_numeric(v) and _to_numpy(v).ndim == 2
        }
        seqs = {k: list(v) for k, v in obj.items() if _is_strseq(v)}
        for m in mats.values():
            for s in seqs.values():
                if len(s) == len(m):
                    return s, m.astype(np.float32)
        if all(isinstance(k, str) for k in obj) and all(
            _is_numeric(v) for v in obj.values()
        ):
            vecs = [_to_numpy(v).reshape(-1) for v in obj.values()]
            if len({len(v) for v in vecs}) == 1:
                return list(obj), np.stack(vecs).astype(np.float32)
        if all(isinstance(v, (dict, pd.DataFrame)) for v in obj.values()):
            parts = [parse_titan(v) for v in obj.values()]
            return sum((p[0] for p in parts), []), np.concatenate([p[1] for p in parts])

    if isinstance(obj, (list, tuple)) and len(obj):
        if len(obj) == 2 and _is_strseq(obj[0]) and _is_numeric(obj[1]):
            return list(obj[0]), _to_numpy(obj[1]).astype(np.float32)
        if all(
            isinstance(x, (list, tuple)) and len(x) == 2 and isinstance(x[0], str)
            for x in obj
        ):
            return [x[0] for x in obj], np.stack(
                [_to_numpy(x[1]).reshape(-1) for x in obj]
            ).astype(np.float32)

    raise ValueError(
        "Unrecognised TITAN pickle layout. Outline:\n"
        + describe(obj)
        + "\nAdd a branch for it in rcc.data.download.parse_titan."
    )


def read_titan_pickle(path=None):
    path = Path(path or C.TITAN_DIR / C.TITAN_FILE)
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except ModuleNotFoundError as e:
        raise RuntimeError(
            f"The pickle needs the '{e.name}' package to load; "
            f"install it in this environment and retry."
        ) from e


def load_titan(path=None, patient_ids=None):
    """Slide-level TITAN embeddings restricted to the given patients.

    Returns (slides table: slide_id, patient_id, is_diagnostic; embeddings [n, d]).
    Only diagnostic (DX) slides are kept when slide ids carry a slide-type code.
    """
    ids, emb = parse_titan(read_titan_pickle(path))
    if len(ids) != len(emb):
        raise ValueError(f"{len(ids)} ids but {len(emb)} embeddings")
    stems = [
        re.sub(r"\.(svs|h5|pt|tiff?|ndpi)$", "", Path(str(i)).name, flags=re.I)
        for i in ids
    ]
    slides = pd.DataFrame(
        {"slide_id": stems, "patient_id": [patient_of(s) for s in stems]}
    )
    typed = slides["slide_id"].str.upper().str.contains(SLIDE_TYPE)
    slides["is_diagnostic"] = slides["slide_id"].str.upper().str.contains(DIAGNOSTIC)
    keep = slides["patient_id"].notna() & (~typed | slides["is_diagnostic"])
    if patient_ids is not None:
        keep &= slides["patient_id"].isin(set(patient_ids))
    keep = keep.to_numpy()
    emb = emb[keep]
    if not np.isfinite(emb).all():
        raise ValueError("TITAN embeddings contain NaN or inf")
    return slides[keep].reset_index(drop=True), emb


def pool_titan(slides: pd.DataFrame, emb: np.ndarray):
    """Mean of a patient's slide embeddings -> one vector per patient."""
    if slides.empty:
        raise RuntimeError(
            "No TITAN slide embeddings matched the cohort's patients. "
            "Inspect the pickle with rcc.data.download.describe()."
        )
    order = sorted(slides["patient_id"].unique())
    groups = slides.groupby("patient_id").indices
    X = np.stack([emb[groups[p]].mean(axis=0) for p in order]).astype(np.float32)
    n = (
        slides.groupby("patient_id")["slide_id"]
        .agg(n_slides="count", slide_ids=lambda s: ";".join(sorted(s)))
        .loc[order]
        .reset_index()
    )
    return X, n


# =============================================================================
# Labels (Ricketts et al. 2018, Table S1)
# =============================================================================
def fetch_labels() -> Path:
    """Locate the Table S1 file. It must be downloaded by hand.

    The publisher and PMC pages sit behind a browser check, so an automated
    download is not reliable. Save the spreadsheet into data/raw/labels/.
    """
    C.LABELS_DIR.mkdir(parents=True, exist_ok=True)
    found = sorted(
        p
        for p in C.LABELS_DIR.iterdir()
        if p.suffix.lower() in {".xlsx", ".csv", ".tsv"} and not p.name.startswith("~")
    )
    if not found:
        raise FileNotFoundError(
            "No label file found.\n"
            f"  1. Open {C.RICKETTS_URL} (Supplemental Information).\n"
            "  2. Download Table S1 (the patient annotation spreadsheet).\n"
            f"  3. Save it in {C.LABELS_DIR}\n"
            "Then re-run. To proceed provisionally with GDC project codes as labels, "
            "use `rcc cohort --labels project` (not for reported results)."
        )
    if len(found) > 1:
        print(f"Several files in {C.LABELS_DIR}; using {found[0].name}")
    return found[0]


def read_label_table(path) -> pd.DataFrame:
    """Read Table S1 as strings, finding the sheet and header row automatically.

    The patient column is located by content (cells that look like TCGA
    barcodes), so title rows above the header do not matter.
    """
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
    else:
        sep = "\t" if path.suffix.lower() == ".tsv" else ","
        sheets = {"table": pd.read_csv(path, sep=sep, header=None, dtype=str)}
    best = None
    for name, raw in sheets.items():
        hits = raw.apply(lambda col: col.map(lambda v: patient_of(v) is not None))
        if not hits.to_numpy().any():
            continue
        col = hits.sum().idxmax()
        first = int(np.argmax(hits[col].to_numpy()))
        n = int(hits[col].sum())
        if best is None or n > best[0]:
            best = (n, name, raw, col, first)
    if best is None:
        raise ValueError(f"No TCGA barcodes found in {path.name}")
    _, name, raw, col, first = best
    if first > 0:
        header = [
            str(h).strip() if pd.notna(h) else f"col{i}"
            for i, h in enumerate(raw.iloc[first - 1])
        ]
    else:
        header = [f"col{i}" for i in range(raw.shape[1])]
    seen = {}
    for i, h in enumerate(header):  # make duplicate column names unique
        seen[h] = seen.get(h, 0) + 1
        if seen[h] > 1:
            header[i] = f"{h}.{seen[h]}"
    table = raw.iloc[first:].copy()
    table.columns = header
    table.insert(
        0, "patient_id", table.iloc[:, list(raw.columns).index(col)].map(patient_of)
    )
    table = table[table["patient_id"].notna()].reset_index(drop=True)
    table.attrs.update(sheet=name, source=path.name)
    return table


def classify_subtype(value) -> str | None:
    """Map a reviewed-histology string to one of the three classes.

    Project codes (KIRC/KIRP/KICH) are deliberately NOT recognised here, so a
    project-membership column can never be mistaken for the reviewed label.
    Values matching zero or several classes return None and are excluded.
    """
    s = str(value).lower()
    found = set()
    if "chromophobe" in s or "chrcc" in s:
        found.add("chromophobe")
    if "clear" in s or "ccrcc" in s:
        found.add("clear_cell")
    if "papillary" in s or "prcc" in s or "cimp" in s:
        found.add("papillary")
    return found.pop() if len(found) == 1 else None


def map_labels(table: pd.DataFrame, column: str | None = None):
    """Reviewed subtype per patient, plus the patients that could not be mapped.

    Returns (labels: patient_id, label, label_raw, label_source; exclusions).
    Papillary subdivisions (type 1, type 2, unclassified, CIMP) collapse into
    one broad papillary class.
    """
    column = column or C.LABEL_COLUMN
    if column is None:
        scores = {}
        for c in table.columns[1:]:
            vals = table[c].dropna()
            if len(vals) < 0.5 * len(table):
                continue
            frac = vals.map(classify_subtype).notna().mean()
            named = any(
                k in str(c).lower() for k in ("histolog", "subtype", "patholog")
            )
            scores[c] = (round(float(frac), 3), named)
        good = {c: s for c, s in scores.items() if s[0] >= 0.8}
        if not good:
            raise ValueError(
                "Could not find the reviewed-subtype column automatically.\n"
                f"Columns: {list(table.columns[1:])}\n"
                "Set RCC_LABEL_COLUMN (or config.LABEL_COLUMN) to the right one."
            )
        column = max(good, key=lambda c: good[c])
    if column not in table.columns:
        raise KeyError(f"Label column {column!r} not in {list(table.columns)}")

    out = pd.DataFrame({"patient_id": table["patient_id"], "label_raw": table[column]})
    out["label"] = out["label_raw"].map(classify_subtype)
    out["label_source"] = f"ricketts2018:{column}"
    dup = out.groupby("patient_id")["label"].nunique(dropna=False) > 1
    conflicted = out["patient_id"].isin(dup[dup].index)
    excl = pd.concat(
        [
            out[conflicted].assign(reason="conflicting labels for patient"),
            out[~conflicted & out["label"].isna()].assign(
                reason="label not one of the three classes"
            ),
        ]
    )[["patient_id", "label_raw", "reason"]].drop_duplicates()
    labels = (
        out[~conflicted & out["label"].notna()]
        .drop_duplicates("patient_id")[
            ["patient_id", "label", "label_raw", "label_source"]
        ]
        .sort_values("patient_id")
        .reset_index(drop=True)
    )
    labels.attrs["column"] = column
    return labels, excl.reset_index(drop=True)


def project_labels(cases: pd.DataFrame) -> pd.DataFrame:
    """PROVISIONAL labels from GDC project membership (pipeline testing only)."""
    out = cases[["patient_id"]].copy()
    out["label"] = cases["project_id"].map(C.PROJECT_TO_CLASS)
    out["label_raw"] = cases["project_id"]
    out["label_source"] = "gdc_project_code(PROVISIONAL)"
    return out.dropna(subset=["label"]).reset_index(drop=True)


def sha256(path, block: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()
