"""Draw the annotated architecture flowchart. Run: python3 docs/make_flowchart.py

Edit NODES / NOTES below when a planned branch gets implemented, then re-run.
Writes flowchart.png in the repository root.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

IMG, RNA, NEUTRAL, PLAN = "#d9d0f7", "#c8efc8", "#ffffff", "#f1f1f1"
EDGE, CHANGED, PLAN_EDGE = "#222222", "#c2410c", "#8a8a8a"
W = 100  # canvas width in data units

# key: (x, y, width, height, fill, status, title, body)
# status: "done" | "changed" (implemented, differs from the proposal) | "planned"
NODES = {
    "img_in": (2, 118, 30, 13, IMG, "changed", "TITAN slide embeddings",
               "Hugging Face MahmoodLab/TITAN\nTCGA_TITAN_features.pkl (gated)\ndownload.py · fetch_titan()"),
    "rna_in": (35, 118, 30, 13, RNA, "done", "Tumor RNA expression",
               "GDC STAR-Counts, open access\none primary-tumor file per patient\ndownload.py · fetch_rna()"),
    "lab_in": (68, 118, 30, 13, NEUTRAL, "done", "Reviewed subtype labels",
               "Ricketts et al. 2018, Table S1\ndata/raw/labels/mmc2.xlsx\ndownload.py · fetch_labels()"),
    "img_pre": (2, 99, 30, 13, IMG, "changed", "Patient-level image vector",
                "diagnostic (DX) slides only\nmean of slide embeddings → 768-d\nload_titan() · pool_titan()"),
    "rna_pre": (35, 99, 30, 13, RNA, "changed", "Expression preprocessing",
                "log2(TPM + 1)\nprotein-coding genes (19,962)\ndownload.py · load_rna()"),
    "lab_pre": (68, 99, 30, 13, NEUTRAL, "done", "Label mapping",
                "map to 3 classes\nunmapped rows → exclusions.csv\ndownload.py · map_labels()"),
    "cohort": (2, 82, 96, 11, NEUTRAL, "done", "Cohort assembly",
               "inner join on patient ID; every exclusion logged in availability.csv\n"
               "800 of 941 candidates kept (464 clear cell · 255 papillary · 81 chromophobe)   —   cohort.py · build_cohort()"),
    "split": (2, 66, 96, 10, NEUTRAL, "done", "Patient-level split",
              "stratified 80 / 20 by subtype, seed 42  →  640 development · 160 locked test   —   train.py · run()"),
    "img_head": (2, 47, 45, 13, IMG, "done", "Image-only classifier",
                 "StandardScaler → logistic regression\nfit on development patients only\ntrain.py · make_heads()"),
    "rna_head": (53, 47, 45, 13, RNA, "done", "Expression-only classifier",
                 "StandardScaler → PCA(50) → logistic regression\nscaling and PCA fit inside training folds\ntrain.py · make_heads()"),
    "fusion": (2, 30, 96, 11, NEUTRAL, "done", "Late fusion on out-of-fold probabilities",
               "logistic regression on stacked 5-fold OOF class probabilities (Lipkova et al. late fusion)\n"
               "train.py · train_and_predict()"),
    "pred": (2, 15, 45, 9, NEUTRAL, "done", "3-class subtype prediction",
             "argmax: clear cell · papillary · chromophobe"),
    "disagree": (53, 15, 45, 9, PLAN, "planned", "Cross-modal disagreement score",
                 "flag cases for pathologist review"),
    "eval": (2, -2, 45, 11, NEUTRAL, "done", "Evaluation on locked test set",
             "macro-F1 and per-class F1, image vs RNA vs fusion\n"
             "→ outputs/results.csv + outputs/results.png\ntrain.py · evaluate() · save_outputs()"),
    "eval_plan": (53, -2, 45, 11, PLAN, "planned", "Evaluation still to add",
                  "majority baseline · per-class precision, recall, AP, ROC-AUC\n"
                  "confusion matrix · paired bootstrap 95% CI\nsite-held-out check · risk–coverage curve"),
}

ARROWS = [
    ("img_in", "img_pre"), ("rna_in", "rna_pre"), ("lab_in", "lab_pre"),
    ("img_pre", "cohort"), ("rna_pre", "cohort"), ("lab_pre", "cohort"),
    ("cohort", "split"), ("split", "img_head"), ("split", "rna_head"),
    ("img_head", "fusion"), ("rna_head", "fusion"),
    ("fusion", "pred"), ("fusion", "disagree"), ("pred", "eval"), ("disagree", "eval_plan"),
]

# Revision notes, numbered on the chart and listed underneath it.
NOTES = {
    "img_in": "1",
    "img_pre": "2",
    "rna_pre": "3",
    "split": "4",
}
NOTE_TEXT = [
    "1  Changed: the proposal tiled GDC slides and ran CONCH v1.5 → TITAN locally. The implementation downloads the "
    "slide embeddings the TITAN authors published for TCGA, so no whole-slide images are processed.",
    "2  Changed: tissue detection, tiling and patch encoding are gone from this pipeline; the only image step is "
    "averaging a patient's diagnostic-slide embeddings.",
    "3  Changed: 'drop low-count genes' became an annotation filter (protein-coding only), which does not depend on "
    "the data and is safe before splitting.",
    "4  Remaining: the split is recomputed from the seed on every run. Persisting it (splits.json) and adding "
    "site groups is planned.",
]


def draw_box(ax, key):
    x, y, w, h, fill, status, title, body = NODES[key]
    planned, changed = status == "planned", status == "changed"
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=1.6", facecolor=fill,
        edgecolor=PLAN_EDGE if planned else CHANGED if changed else EDGE,
        linewidth=1.4 if planned else 2.6 if changed else 1.6,
        linestyle=(0, (5, 3)) if planned else "-"))
    color = "#666666" if planned else "#111111"
    ax.text(x + w / 2, y + h - 1.6, title, ha="center", va="top", fontsize=11.5,
            fontweight="bold", color=color)
    ax.text(x + w / 2, y + h - 4.6, body, ha="center", va="top", fontsize=8.6,
            color=color, linespacing=1.45, family="DejaVu Sans Mono")
    if key in NOTES:
        ax.text(x + w - 1.3, y + h - 1.4, NOTES[key], ha="center", va="top", fontsize=9,
                fontweight="bold", color="white",
                bbox=dict(boxstyle="circle,pad=0.25", facecolor=CHANGED, edgecolor="none"))


def draw_arrow(ax, a, b):
    ax_, ay, aw, _, *_ = NODES[a]
    bx, by, bw, bh, _, status, *_ = NODES[b]
    # vertical arrow at the horizontal centre of the narrower box
    cx = ax_ + aw / 2 if aw <= bw else bx + bw / 2
    planned = status == "planned"
    ax.annotate("", xy=(cx, by + bh + 0.3), xytext=(cx, ay - 0.3),
                arrowprops=dict(arrowstyle="-|>", lw=1.5, mutation_scale=14,
                                color=PLAN_EDGE if planned else EDGE,
                                linestyle=(0, (5, 3)) if planned else "-"))


def main():
    fig, ax = plt.subplots(figsize=(13, 20))
    ax.set_xlim(0, W)
    ax.set_ylim(-40, 150)
    ax.axis("off")

    ax.text(2, 148, "RCC subtype classifier: implemented architecture", fontsize=19,
            fontweight="bold", va="top")
    ax.text(2, 143.4, "Multimodal H&E + RNA classification of renal cell carcinoma subtypes · Cancer Detection track\n"
            "Matthew M. Montoya (mmonto16) · annotated flowchart, revised November 12, 2026 · run with: python3 main.py",
            fontsize=10, va="top", color="#333333", linespacing=1.5)

    # legend
    for i, (label, fill, edge, lw, ls) in enumerate([
        ("Implemented as proposed", NEUTRAL, EDGE, 1.6, "-"),
        ("Implemented, changed from proposal", NEUTRAL, CHANGED, 2.6, "-"),
        ("Planned, not implemented yet", PLAN, PLAN_EDGE, 1.4, (0, (5, 3))),
    ]):
        lx = 2 + i * 33
        ax.add_patch(FancyBboxPatch((lx, 134.2), 4, 2.2, boxstyle="round,pad=0,rounding_size=0.6",
                                    facecolor=fill, edgecolor=edge, linewidth=lw, linestyle=ls))
        ax.text(lx + 5.2, 135.3, label, fontsize=9.5, va="center")
    ax.text(2, 132.6, "Purple = image modality · green = RNA modality", fontsize=8.8, va="center",
            color="#555555")

    for a, b in ARROWS:
        draw_arrow(ax, a, b)
    for key in NODES:
        draw_box(ax, key)

    ax.text(2, -7.5, "Revision notes", fontsize=12, fontweight="bold", va="top")
    y = -11.5
    for note in NOTE_TEXT:
        import textwrap
        wrapped = textwrap.fill(note, 132, subsequent_indent="   ")
        ax.text(2, y, wrapped, fontsize=9.3, va="top", linespacing=1.45)
        y -= 3.1 * (wrapped.count("\n") + 1) + 1.2

    out = Path(__file__).resolve().parents[1] / "flowchart.png"
    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
