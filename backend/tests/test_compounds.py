"""Compound loader and DMTA data-source validation tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import compounds

CSV_PIC50 = "smiles,pIC50\nCCO,7.5\nc1ccccc1,6.2\nCC(=O)Oc1ccccc1C(=O)O,8.1\n"
CSV_IC50_NM = "smiles,IC50_nM\nCCO,100\nc1ccccc1,10\n"
CSV_BINARY = "smiles,label\nCCO,1\nc1ccccc1,0\n"
CSV_NO_ACTIVITY = "smiles,name\nCCO,ethanol\nc1ccccc1,benzene\n"

SCIENTIST = {"X-Role": "scientist", "X-User": "alice"}
GUEST = {"X-Role": "guest", "X-User": "anon"}


def _write(tmp_path, name: str, text: str):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_load_compounds_pic50(tmp_path) -> None:
    p = _write(tmp_path, "a.csv", CSV_PIC50)
    table = compounds.load_compounds(p)
    assert table.smiles_column == "smiles"
    assert table.activity_column == "pIC50"
    assert table.activity_kind == "continuous"
    assert table.n_valid == 3
    assert table.n_with_activity == 3
    assert table.usable_for_dmta


def test_load_compounds_converts_ic50_nm(tmp_path) -> None:
    p = _write(tmp_path, "b.csv", CSV_IC50_NM)
    table = compounds.load_compounds(p)
    assert table.activity_kind == "continuous"
    assert table.activity_unit == "nM"
    # 100 nM -> pIC50 = 7.0 ; 10 nM -> 8.0
    values = sorted(v for v in table.activity if v is not None)
    assert values[0] == pytest.approx(7.0, abs=0.01)
    assert values[1] == pytest.approx(8.0, abs=0.01)


def test_load_compounds_binary_not_usable(tmp_path) -> None:
    p = _write(tmp_path, "c.csv", CSV_BINARY)
    table = compounds.load_compounds(p)
    assert table.activity_kind == "binary"
    assert not table.usable_for_dmta
    assert "binary" in table.reason()


def test_load_compounds_without_activity(tmp_path) -> None:
    p = _write(tmp_path, "d.csv", CSV_NO_ACTIVITY)
    table = compounds.load_compounds(p)
    assert table.activity_kind == "none"
    assert not table.usable_for_dmta
    assert "activity column" in table.reason()


def test_load_compounds_xlsx(tmp_path) -> None:
    pd = pytest.importorskip("pandas")
    p = tmp_path / "e.xlsx"
    pd.DataFrame({"SMILES": ["CCO", "c1ccccc1"], "Activity": [6.5, 7.5]}).to_excel(p, index=False)
    table = compounds.load_compounds(p)
    assert table.smiles_column == "SMILES"
    assert table.n_with_activity == 2


# --------------------------------------------------------------- task validation
def _register_dataset(client: TestClient, tmp_path, dataset_id: str, filename: str, content: str, **meta) -> None:
    from app.core.datasets import DatasetRegistry

    reg = DatasetRegistry()
    reg.ensure_dir(
        dataset_id,
        meta={"name": dataset_id, "data_type": "tabular", "sensitivity": "public", "purpose": "tool", **meta},
    )
    (reg.root / dataset_id / filename).write_text(content, encoding="utf-8")


def test_task_rejected_without_activity(client: TestClient, fake_queue, tmp_path) -> None:
    # large enough to pass the size check, but only a binary label (no continuous activity)
    rows = "smiles,label\n" + "".join(f"C{'C' * i}O,{i % 2}\n" for i in range(1, 40))
    _register_dataset(client, tmp_path, "noact", "mols.csv", rows)
    resp = client.post(
        "/api/v1/tasks",
        headers=SCIENTIST,
        json={"hypothesis": "find a BACE1 inhibitor", "dataset_id": "noact"},
    )
    assert resp.status_code == 422
    assert "binary" in resp.json()["message"]


def test_task_accepts_dataset_with_activity(client: TestClient, fake_queue, tmp_path) -> None:
    rows = "smiles,pIC50\n" + "".join(f"C{'C' * i}O,{6.0 + i * 0.1:.1f}\n" for i in range(1, 40))
    _register_dataset(client, tmp_path, "good", "mols.csv", rows)
    resp = client.post(
        "/api/v1/tasks",
        headers=SCIENTIST,
        json={"hypothesis": "find a BACE1 inhibitor", "dataset_id": "good", "rounds": 1},
    )
    assert resp.status_code == 202
    enqueued = fake_queue["_enqueued"]
    assert enqueued[-1][1]["dataset_id"] == "good"
    assert enqueued[-1][1]["_data_source"]["usable_for_dmta"] is True


def test_task_rejects_unknown_dataset(client: TestClient, fake_queue) -> None:
    resp = client.post(
        "/api/v1/tasks",
        headers=SCIENTIST,
        json={"hypothesis": "find a BACE1 inhibitor", "dataset_id": "nope"},
    )
    assert resp.status_code == 404
