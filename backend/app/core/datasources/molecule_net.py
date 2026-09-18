"""MoleculeNet data source — BACE dataset (real DeepChem public CSV)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger("discoveryx.datasources.molnet")

BACE_URL = "https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/bace.csv"
DATASETS: dict[str, str] = {
    "bace": BACE_URL,
    "bbbp": "https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/BBBP.csv",
    "hiv": "https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/HIV.csv",
}


def fetch_dataset(name: str, out_dir: str | Path) -> Path:
    """Download a MoleculeNet CSV by short name (real download)."""
    key = name.lower()
    if key not in DATASETS:
        raise ExternalServiceError(f"unknown MoleculeNet dataset '{name}' (have: {', '.join(DATASETS)})")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{key}.csv"
    if dest.exists() and dest.stat().st_size > 0:
        logger.info("dataset cached: %s", dest)
        return dest

    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            resp = client.get(DATASETS[key])
            resp.raise_for_status()
            dest.write_bytes(resp.content)
    except Exception as exc:  # noqa: BLE001
        raise ExternalServiceError(f"failed to download MoleculeNet {key}: {exc}") from exc
    logger.info("downloaded %s (%d bytes)", dest, dest.stat().st_size)
    return dest


def fetch_bace(out_dir: str | Path) -> Path:
    return fetch_dataset("bace", out_dir)


def load_bace(path: str | Path) -> Any:
    """Load the BACE CSV into a pandas DataFrame."""
    import pandas as pd

    return pd.read_csv(path)


def summarize(path: str | Path) -> dict[str, Any]:
    df = load_bace(path)
    cols = list(df.columns)
    return {
        "rows": int(len(df)),
        "columns": cols,
        "smiles_col": next((c for c in cols if c.lower() in ("smiles", "mol")), None),
        "label_col": next((c for c in cols if c.lower() in ("class", "label", "p_np")), None),
    }
