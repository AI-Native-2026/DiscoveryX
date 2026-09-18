"""Compound dataset loading for the DMTA workflow.

A user dataset is a directory (see :mod:`app.core.datasets`) whose tabular files
contain molecules. This module turns it into a validated
:class:`CompoundTable` — SMILES plus a continuous activity (pIC50).

Column detection is automatic with explicit overrides:

* **SMILES column** — name match (`smiles`, `mol`, `structure`, …) or the first
  column whose values are ≥ 80 % RDKit-parseable.
* **Activity column** — name match (`pIC50`, `IC50`, `activity`, `potency`, …),
  then unit conversion to pIC50 (nM / µM / M).

A **binary** label column (0/1) is recognised but is *not* usable as a DMTA
activity source — the caller rejects such datasets with a clear message.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.errors import ValidationError
from app.core.logging import get_logger

logger = get_logger("discoveryx.compounds")

TABULAR_EXTS = {".csv", ".tsv", ".xlsx", ".xlsm", ".xls"}
MOL_EXTS = {".sdf", ".mol", ".smi"}
SUPPORTED_EXTS = TABULAR_EXTS | MOL_EXTS

SMILES_HINTS = ("smiles", "smile", "canonical_smiles", "can_smiles", "mol", "molecule", "structure", "smi")
# activity column hints, most specific first
ACTIVITY_TIERS: list[tuple[str, ...]] = [
    ("pic50", "p_ic50", "pchembl", "pec50", "pkd", "pki"),          # already on -log10 scale
    ("ic50", "ec50", "ki", "kd", "activity", "potency", "affinity"),  # needs unit conversion
    ("value", "measured"),                                            # generic numeric
]
BINARY_HINTS = ("label", "class", "y", "active", "hit", "outcome")

ActivityKind = Literal["continuous", "binary", "none"]


class CompoundTable(BaseModel):
    """Validated molecules plus a continuous activity where available."""

    source: str
    smiles_column: str | None = None
    activity_column: str | None = None
    activity_kind: ActivityKind = "none"
    activity_unit: str | None = None
    smiles: list[str] = Field(default_factory=list)
    activity: list[float | None] = Field(default_factory=list)
    n_rows: int = 0
    n_valid: int = 0
    n_with_activity: int = 0
    warnings: list[str] = Field(default_factory=list)

    @property
    def usable_for_dmta(self) -> bool:
        return self.activity_kind == "continuous" and self.n_with_activity > 0 and self.n_valid > 0

    def reason(self) -> str:
        if self.n_valid == 0:
            return "no valid molecules found (missing or unparsable SMILES column)"
        if self.activity_kind == "none":
            return "no activity column found (need pIC50 / IC50 / activity)"
        if self.activity_kind == "binary":
            return "only a binary label column found; DMTA needs a continuous activity (pIC50 / IC50)"
        if self.n_with_activity == 0:
            return "activity column present but no usable values"
        return "ok"

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "smiles_column": self.smiles_column,
            "activity_column": self.activity_column,
            "activity_kind": self.activity_kind,
            "activity_unit": self.activity_unit,
            "n_rows": self.n_rows,
            "n_valid": self.n_valid,
            "n_with_activity": self.n_with_activity,
            "usable_for_dmta": self.usable_for_dmta,
            "reason": self.reason(),
            "warnings": self.warnings,
        }


# ------------------------------------------------------------------ detection
def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def detect_smiles_column(df: Any) -> str | None:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    cols = list(df.columns)
    for c in cols:
        if _norm(c) in SMILES_HINTS:
            return c
    best: tuple[float, str] | None = None
    for c in cols:
        sample = df[c].dropna().astype(str).head(60)
        if sample.empty:
            continue
        ok = sum(1 for v in sample if Chem.MolFromSmiles(v) is not None)
        frac = ok / len(sample)
        if frac >= 0.8 and (best is None or frac > best[0]):
            best = (frac, c)
    return best[1] if best else None


def detect_activity_column(df: Any, smiles_col: str) -> tuple[str | None, ActivityKind]:
    """Pick the best activity column: specific continuous hints beat generic ones,
    and continuous columns beat binary labels."""
    # tier 1-3: continuous activity, most specific hint first
    for tier in ACTIVITY_TIERS:
        for c in df.columns:
            if c == smiles_col:
                continue
            n = _norm(c)
            if not any(h in n for h in tier):
                continue
            numeric = _to_numeric(df[c].dropna())
            if numeric is None or numeric.empty:
                continue
            return c, "continuous"
    # tier 4: binary labels
    for c in df.columns:
        if c == smiles_col:
            continue
        n = _norm(c)
        if not any(h in n for h in BINARY_HINTS):
            continue
        numeric = _to_numeric(df[c].dropna())
        if numeric is None or numeric.empty:
            continue
        uniq = set(numeric.round(6).tolist())
        if uniq.issubset({0.0, 1.0}):
            return c, "binary"
    return None, "none"


def _activity_score(columns: list[str]) -> int:
    """Higher = better compound table (used to pick a file inside a directory)."""
    norm = [_norm(c) for c in columns]
    for i, tier in enumerate(ACTIVITY_TIERS):
        if any(any(h in n for h in tier) for n in norm):
            return 100 - i * 10
    if any(any(h in n for h in BINARY_HINTS) for n in norm):
        return 10
    return 0


def _to_numeric(series: Any) -> Any:
    import pandas as pd

    try:
        return pd.to_numeric(series, errors="coerce").dropna()
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------- activity
def _unit_from_name(name: str) -> str | None:
    n = _norm(name)
    if "pic50" in n or "pchembl" in n or n.startswith("p"):
        return "p"
    if "nm" in n or "nanomolar" in n:
        return "nM"
    if "um" in n or "µm" in str(name).lower() or "micromolar" in n:
        return "uM"
    if "mm" in n or "millimolar" in n:
        return "mM"
    return None


def _guess_unit(values: list[float]) -> str:
    """Fallback when the column name carries no unit."""
    if not values:
        return "p"
    med = sorted(values)[len(values) // 2]
    if 2.0 <= med <= 12.0:
        return "p"  # already pIC50-like
    if med > 100:
        return "nM"
    if med > 0.1:
        return "uM"
    return "M"


def _to_pic50(value: float, unit: str) -> float | None:
    try:
        if unit == "p":
            return round(float(value), 3) if 0 < value < 20 else None
        molar = {
            "M": 1.0,
            "mM": 1e-3,
            "uM": 1e-6,
            "nM": 1e-9,
        }.get(unit)
        if molar is None or value <= 0:
            return None
        return round(-math.log10(value * molar), 3)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------- loading
def _read_table(path: Path) -> Any:
    import pandas as pd

    ext = path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
    if ext == ".tsv":
        return pd.read_csv(path, sep="\t", encoding="utf-8", on_bad_lines="skip")
    if ext in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path)
    raise ValidationError(f"unsupported tabular format: {ext}")


def _read_molecules(path: Path) -> tuple[list[str], list[float | None]]:
    """Read SMILES (+ optional activity) from SDF / SMI files."""
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    smiles: list[str] = []
    activity: list[float | None] = []
    if path.suffix.lower() == ".sdf":
        supplier = Chem.SDMolSupplier(str(path))
        for mol in supplier:
            if mol is None:
                continue
            smiles.append(Chem.MolToSmiles(mol))
            props = mol.GetPropsAsDict()
            act = None
            for key in ("pIC50", "pic50", "IC50", "activity", "Activity"):
                if key in props:
                    try:
                        act = float(props[key])
                    except (TypeError, ValueError):
                        act = None
                    break
            activity.append(act)
    else:  # .smi
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            smiles.append(parts[0])
            activity.append(None)
    return smiles, activity


def load_compounds(path: str | Path, *, smiles_column: str | None = None, activity_column: str | None = None) -> CompoundTable:
    """Load and validate a compound file into a :class:`CompoundTable`."""
    from app.core import dmt_tools

    p = Path(path)
    if not p.exists():
        raise ValidationError(f"compound file not found: {p}")
    ext = p.suffix.lower()

    if ext in MOL_EXTS:
        raw_smiles, raw_activity = _read_molecules(p)
        table = CompoundTable(
            source=str(p),
            smiles_column="smi",
            activity_column="pIC50" if any(a is not None for a in raw_activity) else None,
            activity_kind="continuous" if any(a is not None for a in raw_activity) else "none",
            activity_unit="p",
        )
        _finalize(table, raw_smiles, raw_activity, dmt_tools)
        return table

    df = _read_table(p)
    table = CompoundTable(source=str(p), n_rows=int(len(df)))

    smi_col = smiles_column or detect_smiles_column(df)
    if smi_col is None:
        table.warnings.append("could not detect a SMILES column")
        table.n_valid = 0
        return table
    table.smiles_column = str(smi_col)

    act_col, kind = (activity_column, "continuous") if activity_column else detect_activity_column(df, smi_col)
    if act_col is not None and act_col not in df.columns:
        raise ValidationError(f"activity column '{act_col}' not found; columns: {list(df.columns)}")
    table.activity_column = str(act_col) if act_col else None
    table.activity_kind = kind

    raw_smiles = df[smi_col].astype(str).tolist()
    raw_activity: list[float | None] = [None] * len(raw_smiles)

    if act_col and kind == "continuous":
        values = _to_numeric(df[act_col])
        if values is None or values.empty:
            table.warnings.append(f"activity column '{act_col}' is not numeric")
            table.activity_kind = "none"
        else:
            unit = _unit_from_name(str(act_col)) or _guess_unit(values.tolist())
            table.activity_unit = unit
            if unit == "p":
                table.warnings.append("activity treated as pIC50 (values look like -log10 scale)")
            else:
                table.warnings.append(f"activity converted from {unit} to pIC50")
            for i, v in enumerate(df[act_col].tolist()):
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                raw_activity[i] = _to_pic50(fv, unit)
    elif act_col and kind == "binary":
        table.warnings.append(f"column '{act_col}' is binary; not usable as a DMTA activity source")

    _finalize(table, raw_smiles, raw_activity, dmt_tools)
    return table


def _finalize(table: CompoundTable, raw_smiles: list[str], raw_activity: list[float | None], tools: Any) -> None:
    seen: set[str] = set()
    out_smiles: list[str] = []
    out_activity: list[float | None] = []
    invalid = 0
    for smi, act in zip(raw_smiles, raw_activity, strict=False):
        std = tools.standardize_smiles(smi)
        if std is None:
            invalid += 1
            continue
        if std in seen:
            continue
        seen.add(std)
        out_smiles.append(std)
        out_activity.append(act)
    if invalid:
        table.warnings.append(f"dropped {invalid} unparsable SMILES")
    table.smiles = out_smiles
    table.activity = out_activity
    table.n_valid = len(out_smiles)
    table.n_with_activity = sum(1 for a in out_activity if a is not None)
    if table.n_rows == 0:
        table.n_rows = len(raw_smiles)


def find_compound_file(dataset_dir: str | Path) -> Path | None:
    """Pick the best compound file inside a dataset directory.

    Prefers files that expose a *continuous* activity column (pIC50 / IC50),
    then larger files.
    """
    root = Path(dataset_dir)
    if not root.is_dir():
        return None
    candidates = [p for p in sorted(root.rglob("*")) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    if not candidates:
        return None

    def rank(p: Path) -> tuple[int, int, int]:
        score = 0
        if p.suffix.lower() in TABULAR_EXTS:
            try:
                df = _read_table(p)
                score = _activity_score([str(c) for c in df.columns])
            except Exception:  # noqa: BLE001
                score = 0
        return (score, 1 if p.suffix.lower() in TABULAR_EXTS else 0, p.stat().st_size)

    candidates.sort(key=rank, reverse=True)
    return candidates[0]


def load_dataset_compounds(dataset_id: str, *, smiles_column: str | None = None, activity_column: str | None = None) -> CompoundTable:
    """Load the compound table of a platform dataset directory."""
    from app.core.datasets import DatasetRegistry

    reg = DatasetRegistry()
    info = reg.get(dataset_id)
    if info is None:
        raise ValidationError(f"dataset '{dataset_id}' not found")
    path = find_compound_file(reg.root / dataset_id)
    if path is None:
        raise ValidationError(f"dataset '{dataset_id}' contains no supported compound file")
    table = load_compounds(path, smiles_column=smiles_column, activity_column=activity_column)
    table.source = f"{dataset_id}/{path.name}"
    return table


def probe_compounds(path: str | Path, *, sample: int = 300) -> dict[str, Any]:
    """Cheap column probe (no full validation) for catalog display."""
    p = Path(path)
    try:
        if p.suffix.lower() in TABULAR_EXTS:
            import pandas as pd

            df = (
                pd.read_csv(p, nrows=sample, encoding="utf-8", on_bad_lines="skip")
                if p.suffix.lower() in {".csv", ".tsv"}
                else pd.read_excel(p, nrows=sample)
            )
            smi_col = detect_smiles_column(df)
            if smi_col is None:
                return {"usable_for_dmta": False, "reason": "no SMILES column detected"}
            act_col, kind = detect_activity_column(df, smi_col)
            return {
                "smiles_column": str(smi_col),
                "activity_column": str(act_col) if act_col else None,
                "activity_kind": kind,
                "usable_for_dmta": kind == "continuous",
                "reason": "ok" if kind == "continuous" else f"activity column is {kind}",
                "sampled_rows": int(len(df)),
            }
    except Exception as exc:  # noqa: BLE001
        return {"usable_for_dmta": False, "reason": f"probe failed: {exc}"}
    return {"usable_for_dmta": False, "reason": "not a tabular file"}
