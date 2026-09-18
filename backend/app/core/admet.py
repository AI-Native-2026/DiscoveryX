"""ADMET prediction.

Primary engine: **ADMET-AI** — pretrained Chemprop models trained on the TDC
ADMET datasets (41 endpoints). It is a ready-made model: **no training and no
fine-tuning required**, and it runs on CPU.

Fallback: transparent RDKit descriptor heuristics (see
:func:`app.core.dmt_tools.predict_admet`) so the platform always works.
"""

from __future__ import annotations

import threading
from typing import Any

from app.core.logging import get_logger

logger = get_logger("discoveryx.admet")

_lock = threading.Lock()
_model: Any | None = None
_load_failed = False

# ADMET-AI column -> our endpoint
COLUMN_MAP = {
    "bbb": ["BBB_Martins"],
    "hepatotoxic": ["Hepatotoxicity", "DILI"],
    "herg_prob": ["hERG"],
    "solubility": ["Solubility_AqSolDB"],
    "cyp3a4": ["CYP3A4_Veith", "CYP3A4_Substrate_CarbonMangels"],
    "clearance": ["Clearance_Hepatocyte_AZ", "Clearance_Microsome_AZ"],
    "ppbr": ["PPBR_AZ"],
    "half_life": ["Half_Life_Obach"],
    "ames": ["AMES"],
    "bioavailability": ["Bioavailability_Ma"],
    "lipophilicity": ["Lipophilicity_AstraZeneca"],
}


def _load_model() -> Any | None:
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    with _lock:
        if _model is not None or _load_failed:
            return _model
        try:
            from admet_ai import ADMETModel  # type: ignore

            logger.info("loading ADMET-AI (pretrained Chemprop models)")
            _model = ADMETModel()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ADMET-AI unavailable, falling back to RDKit heuristics: %s", exc)
            _load_failed = True
            _model = None
    return _model


class AdmetPredictor:
    """Predict ADME-Tox endpoints for a batch of molecules."""

    def __init__(self) -> None:
        self.model = _load_model()

    @property
    def engine(self) -> str:
        return "admet_ai" if self.model is not None else "rdkit-heuristic"

    def predict(self, smiles: list[str]) -> list[dict[str, Any]]:
        if not smiles:
            return []
        if self.model is not None:
            try:
                df = self.model.predict(smiles=smiles)
                return [self._row_to_endpoints(row) for _, row in df.iterrows()]
            except Exception as exc:  # noqa: BLE001
                logger.warning("ADMET-AI prediction failed (%s); using heuristics", exc)
        from app.core import dmt_tools

        return [dmt_tools.predict_admet(s) for s in smiles]

    def _row_to_endpoints(self, row: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"valid": True, "engine": "admet_ai"}
        for key, columns in COLUMN_MAP.items():
            for col in columns:
                if col in row.index:
                    try:
                        out[key] = round(float(row[col]), 4)
                    except (TypeError, ValueError):
                        continue
                    break
        if "bbb" in out:
            out["bbb"] = bool(out["bbb"] >= 0.5)
        if "hepatotoxic" in out:
            out["hepatotoxic"] = bool(out["hepatotoxic"] >= 0.5)
        if "ames" in out:
            out["ames"] = bool(out["ames"] >= 0.5)
        return out

    def status(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "available": self.model is not None,
            "endpoints": list(COLUMN_MAP) if self.model is not None else ["bbb", "hepatotoxic", "herg_prob", "solubility"],
        }


def get_predictor() -> AdmetPredictor:
    return AdmetPredictor()


def reset() -> None:
    global _model, _load_failed
    with _lock:
        _model = None
        _load_failed = False
