"""Train the image, RNA and fusion heads"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from rcc import config as C

OUT = C.ROOT / "outputs"


def load_data():
    cohort = pd.read_parquet(C.PROCESSED / "cohort.parquet")
    X = {
        "image": np.load(C.PROCESSED / "X_img.npy"),
        "rna": np.load(C.PROCESSED / "X_rna.npy"),
    }
    return X, cohort["y"].to_numpy()


def make_heads():
    def lr():
        return LogisticRegression(max_iter=2000, class_weight="balanced")

    return {
        "image": make_pipeline(StandardScaler(), lr()),
        "rna": make_pipeline(StandardScaler(), PCA(50, random_state=C.SEED), lr()),
    }


def train_and_predict(X, y, tr, te):
    cv = StratifiedKFold(5, shuffle=True, random_state=C.SEED)
    oof, test_prob, preds = [], [], {}
    for name, head in make_heads().items():
        oof.append(
            cross_val_predict(head, X[name][tr], y[tr], cv=cv, method="predict_proba")
        )
        head.fit(X[name][tr], y[tr])
        test_prob.append(head.predict_proba(X[name][te]))
        preds[name] = test_prob[-1].argmax(axis=1)
    fusion = LogisticRegression(max_iter=2000, class_weight="balanced")
    fusion.fit(np.hstack(oof), y[tr])
    preds["fusion"] = fusion.predict(np.hstack(test_prob))
    return preds


#### FIXME protoype eval function
def evaluate(preds, y_true):
    rows = []
    for name, pred in preds.items():
        f1 = f1_score(y_true, pred, average=None, labels=[0, 1, 2])
        rows.append({"model": name, "macro_f1": f1.mean(), **dict(zip(C.CLASSES, f1))})
    return pd.DataFrame(rows).round(3)


#### FIXME prototype outputs
def save_outputs(table, n_test):
    OUT.mkdir(exist_ok=True)
    table.to_csv(OUT / "results.csv", index=False)
    melted = table.melt(id_vars="model", var_name="metric", value_name="F1")
    ax = sns.barplot(data=melted, x="metric", y="F1", hue="model")
    ax.set(
        ylim=(0, 1),
        xlabel="",
        title=f"Held-out test F1 by model (n = {n_test} patients)",
    )
    plt.tight_layout()
    plt.savefig(OUT / "results.png", dpi=150)
    plt.close()


def run():
    X, y = load_data()
    tr, te = train_test_split(
        np.arange(len(y)), test_size=0.2, stratify=y, random_state=C.SEED
    )
    table = evaluate(train_and_predict(X, y, tr, te), y[te])
    save_outputs(table, len(te))
    print(table.to_string(index=False))


if __name__ == "__main__":
    run()
