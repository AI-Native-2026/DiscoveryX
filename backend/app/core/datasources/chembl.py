"""ChEMBL data source (optional).

Kept as an optional source for retrospective activity data. Uses the public
ChEMBL REST API with on-disk caching.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger("discoveryx.datasources.chembl")

BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"
DEFAULT_TYPES = ("IC50", "Ki", "Kd")


class ChEMBLClient:
    def __init__(self, cache_dir: str | Path | None = None, timeout: float = 60.0, retries: int = 3) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.retries = retries

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        cache_file = None
        if self.cache_dir:
            import hashlib

            key = hashlib.sha256(json.dumps({"p": path, "q": params}, sort_keys=True).encode()).hexdigest()[:24]
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                return json.loads(cache_file.read_text(encoding="utf-8"))

        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                    resp = client.get(f"{BASE_URL}/{path}", params={**params, "format": "json"})
                    resp.raise_for_status()
                    data = resp.json()
                if cache_file:
                    cache_file.write_text(json.dumps(data), encoding="utf-8")
                return data
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(attempt)
        raise ExternalServiceError(f"ChEMBL request failed: {last}")

    def activities(
        self, target_chembl_id: str, *, activity_types: tuple[str, ...] = DEFAULT_TYPES, max_records: int | None = None, page_size: int = 1000
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for std_type in activity_types:
            offset = 0
            while True:
                data = self._get(
                    "activity",
                    {"target_chembl_id": target_chembl_id, "standard_type": std_type, "limit": page_size, "offset": offset},
                )
                batch = data.get("activities", []) or []
                out.extend(batch)
                if max_records and len(out) >= max_records:
                    return out[:max_records]
                if not (data.get("page_meta", {}) or {}).get("next") or not batch:
                    break
                offset += page_size
        return out

    def target(self, target_chembl_id: str) -> dict[str, Any]:
        return self._get(f"target/{target_chembl_id}", {})

    def assay_confidence_map(self, target_chembl_id: str) -> dict[str, int]:
        conf: dict[str, int] = {}
        offset = 0
        while True:
            data = self._get("assay", {"target_chembl_id": target_chembl_id, "limit": 1000, "offset": offset})
            batch = data.get("assays", []) or []
            for a in batch:
                if a.get("assay_chembl_id") and a.get("confidence_score") is not None:
                    conf[a["assay_chembl_id"]] = int(a["confidence_score"])
            if not (data.get("page_meta", {}) or {}).get("next") or not batch:
                break
            offset += 1000
        return conf
