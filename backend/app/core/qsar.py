"""Dataset-specific activity model (QSAR).

When a task is bound to a compound dataset, the platform trains a small QSAR
model **on that dataset** (Morgan fingerprint + RDKit descriptors → LightGBM)
and uses it to predict activity for the newly designed analogs. This is classic
cheminformatics on CPU (seconds), not LLM fine-tuning.

Fallback: if there are too few labelled compounds, or the caller asks for it,
similarity k-NN over the measured compounds is used instead (zero training).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.features import featurize
from app.core.logging import get_logger

logger = get_logger("discoveryx.qsar")

MIN_TRAIN = 30  # minimum labelled compounds to fit a QSAR model
MIN_TEST = 10


class ActivityModelInfo(BaseModel):
    kind: Literal["qsar", "knn", "none"] = "none"
    n_train: int = 0
    n_test: int = 0
    metrics: dict[str, float] = Field(default_factory=dict)
    test_predictions: list[list[float]] = Field(default_factory=list)
    model_path: str | None = None
    note: str = ""


class ActivityModel:
    """Predicts pIC50 for new SMILES."""

    def __init__(self, kind: str, *, booster: Any = None, seeds: tuple[list[str], list[float]] = ((), ())) -> None:
        self.kind = kind
        self._booster = booster
        self._seeds = seeds

    def predict(self, smiles: list[str]) -> list[float | None]:
        if not smiles:
            return []
        if self.kind == "qsar" and self._booster is not None:
            X = featurize(smiles)
            return [round(float(v), 2) for v in self._booster.predict(X)]
        if self.kind == "knn":
            from app.core import dmt_tools

            seed_smiles, seed_pic50 = self._seeds
            return [dmt_tools.nearest_activity(s, seed_smiles, seed_pic50) for s in smiles]
        return [None] * len(smiles)


def _scaffold_split(smiles: list[str], activity: list[float], *, test_frac: float = 0.2) -> tuple[list[int], list[int]]:
    from rdkit.Chem.Scaffolds import MurckoScaffold

    groups: dict[str, list[int]] = {}
    for i, smi in enumerate(smiles):
        try:
            scaf = MurckoScaffold.MurckoScaffoldSmiles(smiles=smi, includeChirality=False)
        except Exception:  # noqa: BLE001
            scaf = ""
        groups.setdefault(scaf, []).append(i)
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    n_test = max(1, int(round(len(smiles) * test_frac)))
    test_idx: list[int] = []
    train_idx: list[int] = []
    for _, idxs in ordered:
        if len(test_idx) < n_test:
            test_idx.extend(idxs)
        else:
            train_idx.extend(idxs)
    return train_idx, test_idx


def _regression_metrics(y_true: Any, y_pred: Any) -> dict[str, float]:
    import numpy as np
    from sklearn.metrics import mean_absolute_error, r2_score

    out: dict[str, float] = {}
    try:
        out["r2"] = round(float(r2_score(y_true, y_pred)), 4)
    except Exception:  # noqa: BLE001
        out["r2"] = 0.0
    try:
        out["mae"] = round(float(mean_absolute_error(y_true, y_pred)), 4)
    except Exception:  # noqa: BLE001
        out["mae"] = 0.0
    try:
        from scipy.stats import spearmanr

        out["spearman"] = round(float(spearmanr(y_true, y_pred).statistic), 4)
    except Exception:  # noqa: BLE001
        pass
    # binarised AUROC (active = above median) for comparability with literature
    try:
        from sklearn.metrics import roc_auc_score

        thr = float(np.median(y_true))
        yb = (np.asarray(y_true) >= thr).astype(int)
        if 0 < yb.sum() < len(yb):
            out["auroc_binarised"] = round(float(roc_auc_score(yb, y_pred)), 4)
    except Exception:  # noqa: BLE001
        pass
    return out


def train_activity_model(
    smiles: list[str],
    activity: list[float | None],
    *,
    seed: int = 42,
    dataset_id: str | None = None,
    model_dir: Path | None = None,
    min_train: int = MIN_TRAIN,
) -> tuple[ActivityModel, ActivityModelInfo]:
    """Train a QSAR model on labelled compounds; fall back to k-NN when too few."""
    pairs = [(s, a) for s, a in zip(smiles, activity, strict=False) if a is not None]
    seed_smiles = [s for s, _ in pairs]
    seed_pic50 = [float(a) for _, a in pairs]

    if len(pairs) < min_train:
        note = f"only {len(pairs)} labelled compounds (< {min_train}); using similarity k-NN"
        logger.info("activity model: %s", note)
        return (
            ActivityModel("knn", seeds=(seed_smiles, seed_pic50)),
            ActivityModelInfo(kind="knn", n_train=len(pairs), note=note),
        )

    import lightgbm as lgb
    import numpy as np

    train_idx, test_idx = _scaffold_split(seed_smiles, seed_pic50)
    if len(test_idx) < MIN_TEST:
        train_idx, test_idx = list(range(len(seed_smiles))), []

    X = featurize(seed_smiles)
    y = np.asarray(seed_pic50, dtype=float)

    model = lgb.LGBMRegressor(
        n_estimators=800,
        learning_rate=0.03,
        num_leaves=31,
        min_child_samples=5,
        subsample=0.85,
        colsample_bytree=0.6,
        reg_lambda=1.0,
        random_state=seed,
        verbose=-1,
    )
    if test_idx:
        model.fit(
            X[train_idx],
            y[train_idx],
            eval_set=[(X[test_idx], y[test_idx])],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
        preds = model.predict(X[test_idx])
        metrics = _regression_metrics(y[test_idx], preds)
        pairs = [[round(float(a), 2), round(float(p), 2)] for a, p in zip(y[test_idx], preds, strict=False)]
    else:
        model.fit(X, y)
        preds = model.predict(X)
        metrics = _regression_metrics(y, preds)
        pairs = [[round(float(a), 2), round(float(p), 2)] for a, p in zip(y, preds, strict=False)]

    info = ActivityModelInfo(
        kind="qsar",
        n_train=len(train_idx),
        n_test=len(test_idx),
        metrics=metrics,
        test_predictions=pairs[:200],
        note=f"trained on {len(train_idx)} compounds, scaffold split, tested on {len(test_idx)}",
    )

    if model_dir is not None and dataset_id:
        try:
            model_dir.mkdir(parents=True, exist_ok=True)
            path = model_dir / f"{dataset_id}.txt"
            model.booster_.save_model(str(path))
            info.model_path = str(path)
            (model_dir / f"{dataset_id}.metrics.json").write_text(
                json.dumps(info.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not persist QSAR model: %s", exc)

    logger.info("activity model trained: %s", info.metrics)
    return ActivityModel("qsar", booster=model), info


def load_activity_model(dataset_id: str, model_dir: Path) -> ActivityModel | None:
    """Load a previously trained QSAR model (for reuse)."""
    path = model_dir / f"{dataset_id}.txt"
    if not path.exists():
        return None
    try:
        import lightgbm as lgb

        booster = lgb.Booster(model_file=str(path))
        return ActivityModel("qsar", booster=booster)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not load QSAR model %s: %s", path, exc)
        return None
