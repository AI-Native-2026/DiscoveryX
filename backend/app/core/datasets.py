"""Directory-based dataset catalog.

Each sub-directory of ``data/datasets`` is **one dataset** (e.g. ``AAA/`` may
contain many PDFs, Excel sheets, CSVs …). A directory may declare metadata in
``dataset.json``; otherwise sensible defaults are derived from its contents.

The catalog is scanned from disk, so it is always in sync with reality — no
mock entries.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core import documents
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.schemas import DatasetInfo, DataType, Purpose, Sensitivity

logger = get_logger("discoveryx.datasets")

META_NAME = "dataset.json"
INDEX_STATE = ".index_state.json"

# A dataset id is a plain directory name: no separators, no traversal.
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _infer_data_type(file_types: dict[str, int]) -> DataType:
    exts = set(file_types)
    if not exts:
        return DataType.MIXED
    doc_exts = {".pdf", ".docx", ".txt", ".md", ".xml", ".html", ".htm"}
    sheet_exts = {".xlsx", ".xlsm", ".xls", ".csv", ".tsv"}
    struct_exts = {".cif", ".pdb", ".mol", ".sdf", ".smi"}
    seq_exts = {".fasta", ".fa", ".faa", ".fastq"}
    if exts <= doc_exts:
        return DataType.DOCUMENT
    if exts <= sheet_exts:
        return DataType.TABULAR
    if exts <= struct_exts:
        return DataType.STRUCTURE
    if exts <= seq_exts:
        return DataType.SEQUENCE
    return DataType.MIXED


class DatasetRegistry:
    """Scans ``data/datasets/<name>/`` directories into :class:`DatasetInfo`."""

    def __init__(self, root: str | Path | None = None) -> None:
        from config.settings import get_settings

        self.settings = get_settings()
        self.root = Path(root) if root else self.settings.datasets_dir
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- index state
    def _state_path(self) -> Path:
        return self.root / INDEX_STATE

    def _load_state(self) -> dict[str, Any]:
        p = self._state_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # pragma: no cover
                return {}
        return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self._state_path().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def mark_indexed(self, dataset_id: str, *, chunks: int, collection: str) -> None:
        state = self._load_state()
        state[dataset_id] = {
            "indexed": True,
            "chunks": chunks,
            "collection": collection,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self._save_state(state)

    def index_state(self, dataset_id: str) -> dict[str, Any]:
        return self._load_state().get(dataset_id, {})

    # ------------------------------------------------------------------ build
    def _dataset_dirs(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(
            [d for d in self.root.iterdir() if d.is_dir() and not d.name.startswith(".")],
            key=lambda p: p.name,
        )

    def _to_info(self, d: Path) -> DatasetInfo:
        scan = documents.scan_directory(d)
        meta: dict[str, Any] = {}
        meta_file = d / META_NAME
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                meta = {}

        st = d.stat()
        file_types = scan["file_types"]
        state = self.index_state(d.name)

        sensitivity = str(meta.get("sensitivity", "public"))
        data_type = str(meta.get("data_type") or _infer_data_type(file_types).value)
        purpose = str(meta.get("purpose", "rag" if data_type == "document" else "tool"))

        # compound probe (cheap) so the UI can show whether a dataset can drive DMTA
        compound: dict[str, Any] = {}
        if data_type in {"tabular", "mixed"}:
            from app.core import compounds as _compounds

            path = _compounds.find_compound_file(d)
            if path is not None:
                compound = _compounds.probe_compounds(path)
                compound["file"] = path.name

        return DatasetInfo(
            id=d.name,
            name=meta.get("name") or d.name,
            data_type=DataType(data_type),
            source=meta.get("source", "local"),
            sensitivity=Sensitivity(sensitivity),
            purpose=Purpose(purpose),
            scale=f"{scan['n_files']} files",
            status=meta.get("status", "ready"),
            rag_indexed=bool(state.get("indexed")),
            path=str(d),
            owner=meta.get("owner", "system"),
            updated_at=datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds"),
            meta={
                **{k: v for k, v in meta.items() if k not in {"name", "sensitivity", "data_type", "purpose"}},
                "index_state": state,
                "compound": compound,
            },
            is_directory=True,
            n_files=scan["n_files"],
            size_bytes=scan["size_bytes"],
            file_types=file_types,
        )

    # ------------------------------------------------------------------- api
    def list(self) -> list[DatasetInfo]:
        return [self._to_info(d) for d in self._dataset_dirs()]

    def get(self, dataset_id: str) -> DatasetInfo | None:
        d = self.root / dataset_id
        if not d.is_dir():
            return None
        return self._to_info(d)

    def files(self, dataset_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        d = self.root / dataset_id
        if not d.is_dir():
            return []
        return documents.list_files(d, limit=limit)

    def documents(self, dataset_id: str, *, max_files: int = 2000):
        d = self.root / dataset_id
        if not d.is_dir():
            return iter(())
        return documents.iter_documents(d, max_files=max_files)

    def ensure_dir(self, dataset_id: str, meta: dict[str, Any] | None = None) -> Path:
        d = self.root / dataset_id
        d.mkdir(parents=True, exist_ok=True)
        if meta:
            (d / META_NAME).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return d

    def delete(self, dataset_id: str) -> dict[str, Any]:
        """Remove a dataset directory, its RAG collection and its index state.

        Returns a small summary of what was removed. Raises if the id is not a
        plain directory name inside the datasets root.
        """
        if not _SAFE_ID.match(dataset_id) or dataset_id.startswith("."):
            raise ValidationError(f"invalid dataset id '{dataset_id}'", dataset_id=dataset_id)

        d = self.root / dataset_id
        if not d.is_dir():
            raise NotFoundError(f"dataset '{dataset_id}' not found", dataset_id=dataset_id)

        state = self.index_state(dataset_id)
        collection = state.get("collection")

        shutil.rmtree(d)
        logger.info("dataset directory removed: %s", d)

        removed_collection = None
        if collection:
            try:
                from app.core.rag_engine import RAGEngine

                RAGEngine().delete_collection(str(collection))
                removed_collection = str(collection)
            except Exception as exc:  # noqa: BLE001 - index cleanup is best effort
                logger.warning("could not drop collection %s: %s", collection, exc)

        if state:
            full = self._load_state()
            full.pop(dataset_id, None)
            self._save_state(full)

        return {
            "dataset_id": dataset_id,
            "files_removed": True,
            "collection_removed": removed_collection,
        }


def make_dataset_info(**kwargs: Any) -> DatasetInfo:
    return DatasetInfo(**kwargs)
