"""API tests — health, tasks, guardrails, datasets, RAG status, OpenAPI."""

from __future__ import annotations

from fastapi.testclient import TestClient

SCIENTIST = {"X-Role": "scientist", "X-User": "alice"}
GUEST = {"X-Role": "guest", "X-User": "anon"}
ENGINEER = {"X-Role": "engineer", "X-User": "bob"}
ADMIN = {"X-Role": "admin", "X-User": "root"}


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "DiscoveryX"


def test_trace_header_present(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.headers.get("X-Trace-Id")


def test_openapi_schema_complete(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for expected in ("/api/v1/tasks", "/api/v1/guardrails/events", "/api/v1/rag/query", "/api/v1/projects", "/api/v1/copilot/chat"):
        assert expected in paths


def test_task_submit_denied_for_guest(client: TestClient) -> None:
    resp = client.post("/api/v1/tasks", json={"hypothesis": "find a good BACE1 inhibitor"}, headers=GUEST)
    assert resp.status_code == 403
    assert resp.json()["error"] == "guardrail_violation"


def test_task_submit_blocked_by_dlp(client: TestClient, fake_queue) -> None:
    resp = client.post(
        "/api/v1/tasks",
        json={"hypothesis": "assess internal project PROJ-1234 compounds"},
        headers=SCIENTIST,
    )
    assert resp.status_code == 403
    assert resp.json()["details"]["guardrail"] == "dlp"


def test_task_submit_ok(client: TestClient, fake_queue) -> None:
    resp = client.post(
        "/api/v1/tasks",
        json={"hypothesis": "find a brain-penetrant BACE1 inhibitor", "rounds": 2},
        headers=SCIENTIST,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["task_id"].startswith("task-")
    assert body["status"] == "queued"


def test_task_get_roundtrip(client: TestClient, fake_queue) -> None:
    created = client.post(
        "/api/v1/tasks", json={"hypothesis": "find a brain-penetrant BACE1 inhibitor"}, headers=SCIENTIST
    ).json()
    resp = client.get(f"/api/v1/tasks/{created['task_id']}", headers=SCIENTIST)
    assert resp.status_code == 200
    assert resp.json()["task_id"] == created["task_id"]


def test_task_not_found(client: TestClient, fake_queue) -> None:
    resp = client.get("/api/v1/tasks/task-doesnotexist", headers=SCIENTIST)
    assert resp.status_code == 404


def test_task_scoped_to_project(client: TestClient, fake_queue) -> None:
    created = client.post(
        "/api/v1/tasks",
        json={"hypothesis": "find a brain-penetrant BACE1 inhibitor", "project": "proj-a"},
        headers=SCIENTIST,
    ).json()
    assert created["status"] == "queued"
    state = fake_queue[created["task_id"]]
    assert state.project == "proj-a"

    listed = client.get("/api/v1/tasks?project=proj-a", headers=SCIENTIST).json()
    assert any(t["task_id"] == created["task_id"] for t in listed)
    other = client.get("/api/v1/tasks?project=proj-b", headers=SCIENTIST).json()
    assert all(t["task_id"] != created["task_id"] for t in other)


def test_task_inherits_target_and_pdb_from_project(client: TestClient, fake_queue) -> None:
    """A task must not silently run against a different target than its project."""
    client.post(
        "/api/v1/projects",
        json={"id": "metap2-prog", "name": "MetAP2 programme", "target": "MetAP2", "pdb_id": "1B6A"},
        headers=SCIENTIST,
    )
    created = client.post(
        "/api/v1/tasks",
        json={"hypothesis": "find a selective MetAP2 inhibitor", "project": "metap2-prog"},
        headers=SCIENTIST,
    ).json()
    state = fake_queue[created["task_id"]]
    assert state.target == "MetAP2"
    _, payload, _ = fake_queue["_enqueued"][-1]
    assert payload["target"] == "MetAP2"
    assert payload["pdb_id"] == "1B6A"


def test_task_explicit_target_overrides_project(client: TestClient, fake_queue) -> None:
    client.post(
        "/api/v1/projects",
        json={"id": "metap2-prog2", "name": "MetAP2 programme", "target": "MetAP2", "pdb_id": "1B6A"},
        headers=SCIENTIST,
    )
    client.post(
        "/api/v1/tasks",
        json={
            "hypothesis": "explore an EGFR series instead",
            "project": "metap2-prog2",
            "target": "EGFR",
            "pdb_id": "4HJO",
        },
        headers=SCIENTIST,
    )
    _, payload, _ = fake_queue["_enqueued"][-1]
    assert payload["target"] == "EGFR"
    assert payload["pdb_id"] == "4HJO"


def test_audit_read_denied_for_guest(client: TestClient) -> None:
    assert client.get("/api/v1/guardrails/events", headers=GUEST).status_code == 403


def test_audit_read_allowed_for_engineer(client: TestClient) -> None:
    resp = client.get("/api/v1/guardrails/events", headers=ENGINEER)
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_policy_view_requires_guardrails_read(client: TestClient) -> None:
    assert client.get("/api/v1/guardrails/policy", headers=GUEST).status_code == 403
    assert client.get("/api/v1/guardrails/policy", headers=ADMIN).status_code == 200


def test_dlp_check_endpoint(client: TestClient) -> None:
    blocked = client.post("/api/v1/guardrails/dlp-check", json={"text": "project PROJ-9999"}, headers=SCIENTIST)
    assert blocked.status_code == 200
    assert blocked.json()["blocked"] is True

    clean = client.post("/api/v1/guardrails/dlp-check", json={"text": "a clean hypothesis"}, headers=SCIENTIST)
    assert clean.json()["action"] == "ALLOW"


def test_datasets_filtered_by_clearance(client: TestClient) -> None:
    from app.core.datasets import DatasetRegistry

    reg = DatasetRegistry()
    reg.ensure_dir(
        "internal_assay",
        meta={
            "name": "Internal assay results",
            "data_type": "document",
            "source": "upload",
            "sensitivity": "confidential",
            "purpose": "rag",
        },
    )
    (reg.root / "internal_assay" / "assay.txt").write_text("internal assay data", encoding="utf-8")

    # guest lacks dataset:read entirely
    assert client.get("/api/v1/datasets", headers=GUEST).status_code == 403

    # engineer clearance = internal -> confidential dataset filtered out
    eng_items = client.get("/api/v1/datasets", headers=ENGINEER).json()["items"]
    assert all(d["sensitivity"] in {"public", "internal"} for d in eng_items)

    # scientist clearance = confidential -> sees it
    sci_items = client.get("/api/v1/datasets", headers=SCIENTIST).json()["items"]
    assert any(d["id"] == "internal_assay" for d in sci_items)


def test_dataset_directory_listing(client: TestClient) -> None:
    from app.core.datasets import DatasetRegistry

    reg = DatasetRegistry()
    reg.ensure_dir("AAA", meta={"name": "Doc set", "data_type": "document", "sensitivity": "public", "purpose": "rag"})
    (reg.root / "AAA" / "a.pdf.txt").write_text("hello", encoding="utf-8")
    (reg.root / "AAA" / "b.csv").write_text("x,y\n1,2\n", encoding="utf-8")

    info = client.get("/api/v1/datasets/AAA", headers=SCIENTIST).json()
    assert info["is_directory"] is True
    assert info["n_files"] == 2
    assert info["data_type"] == "document"

    files = client.get("/api/v1/datasets/AAA/files", headers=SCIENTIST).json()
    assert files["total"] == 2
    assert len(files["items"]) == 2


def test_create_dataset_directory(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/datasets",
        headers=SCIENTIST,
        json={
            "id": "PROJ_DOCS",
            "name": "Project documents",
            "data_type": "document",
            "source": "upload",
            "sensitivity": "internal",
            "purpose": "rag",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == "PROJ_DOCS"


def test_admin_can_read_restricted_dataset(client: TestClient) -> None:
    from app.core.datasets import DatasetRegistry

    DatasetRegistry().ensure_dir(
        "restricted_x",
        meta={"name": "Restricted", "data_type": "tabular", "sensitivity": "restricted", "purpose": "tool"},
    )
    assert client.get("/api/v1/datasets/restricted_x", headers=SCIENTIST).status_code == 403
    assert client.get("/api/v1/datasets/restricted_x", headers=ADMIN).status_code == 200


# ---------------------------------------------------------------- copilot
def test_copilot_requires_permission(client: TestClient) -> None:
    resp = client.post("/api/v1/copilot/chat", json={"message": "hello"}, headers=GUEST)
    assert resp.status_code == 403


def test_copilot_blocks_dlp(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/copilot/chat",
        json={"message": "tell me about internal project PROJ-1234"},
        headers=SCIENTIST,
    )
    assert resp.status_code == 403
    assert resp.json()["details"]["guardrail"] == "dlp"


def test_copilot_returns_answer(client: TestClient) -> None:
    resp = client.post("/api/v1/copilot/chat", json={"message": "summarise the current run"}, headers=SCIENTIST)
    assert resp.status_code == 200
    body = resp.json()
    assert "answer" in body
    assert any(s["tool"] == "guardrails" for s in body["steps"])


def test_copilot_openapi_present(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/v1/copilot/chat" in schema["paths"]
    assert "/api/v1/datasets/{dataset_id}/files" in schema["paths"]
    assert "/api/v1/datasets/{dataset_id}/index" in schema["paths"]


# ---------------------------------------------------------------- approvals
def test_approvals_flow(client: TestClient) -> None:
    from app.core import approvals

    approvals.reset()
    req = approvals.create(task_id="t1", kind="advance_candidates", title="approve me", requested_by="alice")

    listed = client.get("/api/v1/approvals?status=pending", headers=SCIENTIST).json()
    assert listed["pending"] == 1

    decided = client.post(
        f"/api/v1/approvals/{req.id}/decision",
        headers=SCIENTIST,
        json={"decision": "approved", "comment": "looks good"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"
    assert decided.json()["decided_by"] == "alice"

    assert client.get("/api/v1/approvals?status=pending", headers=SCIENTIST).json()["pending"] == 0


def test_approvals_requires_permission(client: TestClient) -> None:
    assert client.get("/api/v1/approvals", headers=GUEST).status_code == 403


# ---------------------------------------------------------------- projects
def test_projects_start_empty_and_are_created(client: TestClient) -> None:
    # The platform starts with no projects (no seed/mock data).
    first = client.get("/api/v1/projects", headers=SCIENTIST)
    assert first.status_code == 200
    assert first.json()["total"] == 0

    created = client.post(
        "/api/v1/projects",
        headers=SCIENTIST,
        json={"id": "proj-x", "name": "Project X", "target": "BACE1"},
    )
    assert created.status_code == 201

    after = client.get("/api/v1/projects", headers=SCIENTIST).json()
    assert after["total"] == 1
    assert after["items"][0]["id"] == "proj-x"


def test_project_name_collision_gets_unique_id(client: TestClient) -> None:
    a = client.post("/api/v1/projects", headers=SCIENTIST, json={"name": "Collision Test"}).json()
    b = client.post("/api/v1/projects", headers=SCIENTIST, json={"name": "Collision Test"}).json()
    assert a["id"] != b["id"]
    assert b["id"].startswith(a["id"])


def test_project_create(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/projects",
        headers=SCIENTIST,
        json={
            "id": "my-proj",
            "name": "My Project",
            "description": "test project",
            "target": "BACE1",
            "objectives": ["BBB"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == "my-proj"

    duplicate = client.post("/api/v1/projects", headers=SCIENTIST, json={"id": "my-proj", "name": "dup"})
    assert duplicate.status_code == 422


def test_projects_requires_permission(client: TestClient) -> None:
    assert client.get("/api/v1/projects", headers=GUEST).status_code == 403


# ---------------------------------------------------------------- upload
def test_dataset_upload(client: TestClient) -> None:
    from app.core.datasets import DatasetRegistry

    DatasetRegistry().ensure_dir(
        "UPLOADED", meta={"name": "upload test", "data_type": "document", "sensitivity": "public", "purpose": "rag"}
    )
    resp = client.post(
        "/api/v1/datasets/UPLOADED/upload",
        headers=SCIENTIST,
        files=[("files", ("notes.txt", b"hello world", "text/plain"))],
    )
    assert resp.status_code == 200
    assert resp.json()["uploaded"] == 1

    files = client.get("/api/v1/datasets/UPLOADED/files", headers=SCIENTIST).json()
    assert files["total"] == 1
    assert files["items"][0]["name"] == "notes.txt"


def test_dataset_upload_rejects_traversal(client: TestClient) -> None:
    from app.core.datasets import DatasetRegistry

    DatasetRegistry().ensure_dir(
        "TRAV", meta={"name": "t", "data_type": "document", "sensitivity": "public", "purpose": "rag"}
    )
    resp = client.post(
        "/api/v1/datasets/TRAV/upload",
        headers=SCIENTIST,
        files=[("files", ("../evil.txt", b"x", "text/plain"))],
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------- report
def test_task_report_html(client: TestClient, fake_queue) -> None:
    created = client.post(
        "/api/v1/tasks", json={"hypothesis": "find a brain-penetrant BACE1 inhibitor"}, headers=SCIENTIST
    ).json()
    tid = created["task_id"]
    state = fake_queue[tid]
    state.result = {
        "task_id": tid,
        "target": "BACE1",
        "hypothesis": "find a brain-penetrant BACE1 inhibitor",
        "rounds": [{"round": 1, "passed": 1, "summary": "round 1: 1 passed", "decision": "met"}],
        "top_candidates": [
            {
                "id": 1,
                "smiles": "CC(=O)Oc1ccccc1C(=O)O",
                "pIC50": 7.5,
                "bbb": True,
                "hepatotoxic": False,
                "sa_score": 2.1,
                "qed": 0.6,
                "route_steps": 3,
                "mpo": 0.8,
            }
        ],
        "decision": "met",
        "evidence": [{"type": "pdb", "id": "4WY1", "title": "BACE1"}],
        "activity_model": {
            "kind": "qsar",
            "n_train": 10,
            "n_test": 3,
            "metrics": {"r2": 0.5, "mae": 0.4, "spearman": 0.6, "auroc_binarised": 0.8},
            "test_predictions": [[5.0, 5.2], [6.0, 5.6], [7.0, 7.1]],
        },
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "calls": 1, "cost_usd": 0.001},
        "generated_at": "2026-01-01T00:00:00+00:00",
    }
    resp = client.get(f"/api/v1/tasks/{tid}/report", headers=SCIENTIST)
    assert resp.status_code == 200
    assert "DMTA 研发报告" in resp.text
    assert "<svg" in resp.text  # molecule structure rendered
    # The report is a standalone light-scheme document. Without an explicit
    # color-scheme a dark-mode browser paints UA controls (buttons, table cells)
    # with light text, which is invisible on the white page.
    assert '<meta name="color-scheme" content="light"/>' in resp.text
    assert "color-scheme:light" in resp.text
    assert "html{background:#fff}" in resp.text
    # Every class used by the charts must actually be styled.
    for cls in (".tick{", ".sgrid{", ".axis-label{", ".bar-label{"):
        assert cls in resp.text, cls
    # The scatter's grid lines use their own class, separate from the layout grid.
    assert 'class="grid" x1=' not in resp.text
    assert 'class="sgrid" x1=' in resp.text


def test_chembl_cleaning_rules() -> None:
    """Raw ChEMBL rows are only trainable when exact, same-unit IC50."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("dx_download_data", root / "data" / "download_data.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    good = {
        "standard_type": "IC50",
        "standard_relation": "=",
        "standard_units": "nM",
        "pchembl_value": "7.39",
        "canonical_smiles": "CCO",
    }
    assert mod._trainable_ic50(good)

    for field, bad in [
        ("standard_relation", ">"),  # censored: no exact value
        ("standard_relation", "<"),
        ("standard_type", "Ki"),  # different assay type
        ("standard_units", "ug.mL-1"),
        ("pchembl_value", ""),
        ("canonical_smiles", ""),
    ]:
        row = {**good, field: bad}
        assert not mod._trainable_ic50(row), f"{field}={bad!r} should be rejected"
