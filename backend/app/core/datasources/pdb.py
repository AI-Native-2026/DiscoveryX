"""RCSB PDB data source — structure files and entry metadata (real API)."""

from __future__ import annotations

from pathlib import Path

import httpx

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger("discoveryx.datasources.pdb")

FILES_URL = "https://files.rcsb.org/download"
ENTRY_URL = "https://data.rcsb.org/rest/v1/core/entry"


def fetch_structure(pdb_id: str, out_dir: str | Path, *, fmt: str = "cif") -> Path:
    """Download a structure file (mmCIF by default). Real RCSB download."""
    pdb_id = pdb_id.upper()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{pdb_id}.{fmt}"
    if dest.exists() and dest.stat().st_size > 0:
        logger.info("structure cached: %s", dest)
        return dest

    url = f"{FILES_URL}/{pdb_id}.{fmt}"
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
    except Exception as exc:  # noqa: BLE001
        raise ExternalServiceError(f"failed to download PDB {pdb_id}: {exc}") from exc
    logger.info("downloaded %s (%d bytes)", dest, dest.stat().st_size)
    return dest


def fetch_metadata(pdb_id: str) -> dict:
    """Fetch entry metadata from the RCSB REST API (real)."""
    pdb_id = pdb_id.upper()
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(f"{ENTRY_URL}/{pdb_id}")
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise ExternalServiceError(f"failed to fetch PDB metadata for {pdb_id}: {exc}") from exc

    return {
        "pdb_id": pdb_id,
        "title": data.get("struct", {}).get("title"),
        "resolution": (data.get("rcsb_entry_info", {}) or {}).get("resolution_combined"),
        "method": (data.get("exptl", [{}]) or [{}])[0].get("method"),
        "organism": data.get("rcsb_entity_source_organism", [{}]),
        "deposited": data.get("rcsb_accession_info", {}).get("deposit_date"),
    }
