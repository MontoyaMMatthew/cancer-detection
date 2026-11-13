"""Join the three sources by patient ID and write the model-ready cohort."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from rcc import config as C
from rcc.data import download as D


def _read_manifest(name: str) -> pd.DataFrame:
    path = C.MANIFESTS / name
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run `rcc download` first.")
    return pd.read_csv(path)


def build_cohort(labels: str = "ricketts") -> pd.DataFrame:
    """Build data/processed/: one row per patient with image and RNA features.

    labels="ricketts" uses reviewed Table S1 labels (the project design);
    labels="project" uses GDC project codes and marks the cohort provisional.

    Writes
      cohort.parquet     patient_id, label, y, site_code, age, sex, provenance columns
      X_img.npy          [n, 768] mean TITAN slide embedding per patient
      X_rna.npy          [n, genes] log2(TPM+1)
      genes.csv          column annotation for X_rna
      availability.csv   every candidate patient, what they have, why excluded
      exclusions.csv     label rows that could not be mapped to a class
      provenance.json    sources, counts, hashes
    Rows of cohort.parquet, X_img and X_rna are aligned and sorted by patient_id.
    """
    if labels not in {"ricketts", "project"}:
        raise ValueError("labels must be 'ricketts' or 'project'")
    cases = _read_manifest("cases.csv")
    rna_sel = _read_manifest("rna_selected.csv")
    slide_files = _read_manifest("slide_files.csv")

    # --- labels --------------------------------------------------------------
    if labels == "ricketts":
        label_path = D.fetch_labels()
        lab, label_excl = D.map_labels(D.read_label_table(label_path))
        label_file = label_path.name
        print(f"Labels: column {lab.attrs['column']!r} of {label_file}")
        counts = lab["label"].value_counts().to_dict()
        if counts != C.RICKETTS_EXPECTED:
            print(
                f"  WARNING: label counts {counts} differ from the published "
                f"{C.RICKETTS_EXPECTED}. Check the column choice and exclusions."
            )
    else:
        lab, label_excl, label_file = (
            D.project_labels(cases),
            pd.DataFrame(columns=["patient_id", "label_raw", "reason"]),
            None,
        )
        print("Labels: GDC project codes (PROVISIONAL, not reviewed histology)")

    # --- image ---------------------------------------------------------------
    slides, emb = D.load_titan(patient_ids=cases["patient_id"])
    X_img_all, img_meta = D.pool_titan(slides, emb)
    img_row = {p: i for i, p in enumerate(img_meta["patient_id"])}

    # --- availability audit (before any filtering) ---------------------------
    avail = cases.merge(lab, on="patient_id", how="outer")
    avail["n_gdc_diagnostic_slides"] = (
        avail["patient_id"]
        .map(slide_files.groupby("patient_id")["file_id"].nunique())
        .fillna(0)
        .astype(int)
    )
    avail = avail.merge(
        img_meta.rename(columns={"n_slides": "n_titan_slides"}),
        on="patient_id",
        how="left",
    )
    avail["n_titan_slides"] = avail["n_titan_slides"].fillna(0).astype(int)
    avail = avail.merge(
        rna_sel[["patient_id", "file_id", "sample_id", "n_candidates"]].rename(
            columns={
                "file_id": "rna_file_id",
                "sample_id": "rna_sample_id",
                "n_candidates": "n_rna_candidates",
            }
        ),
        on="patient_id",
        how="left",
    )
    avail["has_label"] = avail["label"].notna()
    avail["has_image"] = avail["n_titan_slides"] > 0
    avail["has_rna"] = avail["rna_file_id"].notna()
    avail["has_clinical"] = avail["age_at_diagnosis"].notna() & avail["sex"].notna()
    reasons = []
    for r in avail.itertuples():
        missing = [
            name
            for name, ok in (
                ("label", r.has_label),
                ("image", r.has_image),
                ("rna", r.has_rna),
            )
            if not ok
        ]
        reasons.append("" if not missing else "missing " + "+".join(missing))
    avail["exclusion_reason"] = reasons
    avail["eligible"] = avail["exclusion_reason"] == ""
    avail = avail.sort_values("patient_id").reset_index(drop=True)

    cohort = avail[avail["eligible"]].reset_index(drop=True)
    if cohort.empty:
        raise RuntimeError(
            "No patient has a label, an image embedding and RNA. "
            "Check availability.csv inputs and the TITAN slide ids."
        )

    # --- features, aligned to cohort order -----------------------------------
    X_img = X_img_all[[img_row[p] for p in cohort["patient_id"]]]
    sel = rna_sel.set_index("patient_id").loc[cohort["patient_id"]].reset_index()
    missing = [f for f in sel["file_id"] if not D.rna_path(f).exists()]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} RNA files not downloaded yet. "
            "Run `rcc download` to finish."
        )
    X_rna, genes, rna_patients = D.load_rna(sel)
    assert rna_patients == cohort["patient_id"].tolist()
    assert len(X_img) == len(X_rna) == len(cohort)

    cohort["y"] = (
        cohort["label"].map({c: i for i, c in enumerate(C.CLASSES)}).astype(int)
    )
    cohort["site_code"] = cohort["patient_id"].str[
        5:7
    ]  # tissue source site, for grouping
    cohort = cohort[
        [
            "patient_id",
            "label",
            "y",
            "site_code",
            "age_at_diagnosis",
            "sex",
            "n_titan_slides",
            "slide_ids",
            "rna_file_id",
            "rna_sample_id",
            "n_rna_candidates",
            "project_id",
            "label_raw",
            "label_source",
        ]
    ]

    # --- write ---------------------------------------------------------------
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    cohort.to_parquet(C.PROCESSED / "cohort.parquet", index=False)
    np.save(C.PROCESSED / "X_img.npy", X_img)
    np.save(C.PROCESSED / "X_rna.npy", X_rna)
    genes.to_csv(C.PROCESSED / "genes.csv", index=False)
    avail.to_csv(C.PROCESSED / "availability.csv", index=False)
    label_excl.to_csv(C.PROCESSED / "exclusions.csv", index=False)

    release_file = C.MANIFESTS / "gdc_release.json"
    titan_file = C.TITAN_DIR / C.TITAN_FILE
    provenance = {
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "labels_mode": labels,
        "provisional": labels != "ricketts",
        "label_file": label_file,
        "label_column": lab.attrs.get("column"),
        "gdc": json.loads(release_file.read_text()) if release_file.exists() else None,
        "titan": {
            "repo": C.TITAN_REPO,
            "file": C.TITAN_FILE,
            "sha256": D.sha256(titan_file),
        },
        "rna": {
            "value": f"log2({C.RNA_VALUE_COLUMN}+1)",
            "protein_coding_only": C.PROTEIN_CODING_ONLY,
            "n_genes": int(X_rna.shape[1]),
        },
        "n_candidates": int(len(avail)),
        "n_patients": int(len(cohort)),
        "class_counts": cohort["label"]
        .value_counts()
        .reindex(C.CLASSES, fill_value=0)
        .to_dict(),
        "excluded": avail.loc[~avail["eligible"], "exclusion_reason"]
        .value_counts()
        .to_dict(),
        "cohort_hash": hashlib.sha256(
            "\n".join(cohort["patient_id"]).encode()
        ).hexdigest(),
        "seed": C.SEED,
    }
    (C.PROCESSED / "provenance.json").write_text(json.dumps(provenance, indent=2))

    print(f"Cohort: {len(cohort)} patients of {len(avail)} candidates")
    print("  classes:", provenance["class_counts"])
    print("  excluded:", provenance["excluded"])
    print(f"  X_img {X_img.shape}, X_rna {X_rna.shape} -> {C.PROCESSED}")
    return cohort


def load_cohort():
    """(cohort table, X_img, X_rna, genes) as written by build_cohort."""
    cohort = pd.read_parquet(C.PROCESSED / "cohort.parquet")
    X_img = np.load(C.PROCESSED / "X_img.npy")
    X_rna = np.load(C.PROCESSED / "X_rna.npy")
    genes = pd.read_csv(C.PROCESSED / "genes.csv")
    assert len(cohort) == len(X_img) == len(X_rna) and X_rna.shape[1] == len(genes)
    return cohort, X_img, X_rna, genes
