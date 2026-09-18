"""Pre-flight validation of the compound source for a DMTA task.

Enforces the platform rule: a task must have a usable **continuous activity**
source. If the caller supplies a dataset it must exist, pass the caller's
clearance and contain a SMILES column plus an activity column — otherwise the
task is rejected with a clear reason.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger

logger = get_logger("discoveryx.taskdata")

MIN_COMPOUNDS = 10
MIN_LABELLED_FOR_QSAR = 30


def validate_compound_source(payload: dict[str, Any], principal: Any, guard: Any) -> dict[str, Any]:
    """Validate the compound source and return a summary for the task record."""
    dataset_id = payload.get("dataset_id")
    if not dataset_id:
        return {
            "source": "builtin",
            "dataset_id": "molecule_net_bace",
            "name": "MoleculeNet BACE (built-in)",
            "usable_for_dmta": True,
            "reason": "ok",
        }

    from app.core.datasets import DatasetRegistry

    reg = DatasetRegistry()
    info = reg.get(dataset_id)
    if info is None:
        raise NotFoundError(f"dataset '{dataset_id}' not found", dataset_id=dataset_id)

    # data clearance: never read a dataset above the caller's clearance
    guard.authorize_level(principal, info.sensitivity.value, resource=f"dataset:{dataset_id}")

    from app.core.compounds import load_dataset_compounds

    table = load_dataset_compounds(
        dataset_id,
        smiles_column=payload.get("smiles_column"),
        activity_column=payload.get("activity_column"),
    )

    if table.n_valid < MIN_COMPOUNDS:
        raise ValidationError(
            f"dataset '{dataset_id}' has only {table.n_valid} valid molecules (< {MIN_COMPOUNDS}); "
            "provide a larger compound file",
            dataset_id=dataset_id,
            n_valid=table.n_valid,
        )

    if not table.usable_for_dmta:
        raise ValidationError(
            f"dataset '{dataset_id}' cannot drive a DMTA run: {table.reason()}",
            dataset_id=dataset_id,
            reason=table.reason(),
            detected={"smiles_column": table.smiles_column, "activity_column": table.activity_column},
        )

    summary = {"source": "dataset", "dataset_id": dataset_id, **table.summary()}
    if payload.get("activity_model", "qsar") == "qsar" and table.n_with_activity < MIN_LABELLED_FOR_QSAR:
        summary["warnings"] = list(summary.get("warnings", [])) + [
            f"only {table.n_with_activity} labelled compounds (< {MIN_LABELLED_FOR_QSAR}); "
            "the run will fall back to similarity k-NN"
        ]
    logger.info("compound source validated: %s", summary.get("reason"))
    return summary
