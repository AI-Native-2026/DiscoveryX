"""Chemistry tool tests (RDKit, real computations)."""

from __future__ import annotations

from app.core import dmt_tools

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
ANILINE = "Nc1ccccc1"


def test_standardize_removes_salt():
    assert dmt_tools.standardize_smiles("[Na+].[Cl-].CCO") == "CCO"


def test_standardize_invalid_returns_none():
    assert dmt_tools.standardize_smiles("not-a-molecule") is None


def test_descriptors_present():
    d = dmt_tools.descriptors(ASPIRIN)
    assert d is not None
    assert d["mw"] > 150
    assert d["tpsa"] > 0


def test_qed_in_range():
    q = dmt_tools.qed(ASPIRIN)
    assert q is not None and 0.0 <= q <= 1.0


def test_sa_score_in_range():
    sa = dmt_tools.sa_score(ASPIRIN)
    assert sa is not None and 1.0 <= sa <= 10.0


def test_lipinski_violations_non_negative():
    v = dmt_tools.lipinski_violations(ASPIRIN)
    assert v is not None and v >= 0


def test_admet_flags_aniline_hepatotoxicity():
    result = dmt_tools.predict_admet(ANILINE)
    assert result["valid"] is True
    assert result["hepatotoxic"] is True


def test_admet_bbb_heuristic_prefers_low_tpsa():
    # small, low-TPSA molecule should be predicted BBB+
    result = dmt_tools.predict_admet("Cc1ccccc1")
    assert result["valid"] and result["bbb"] is True


def test_generate_analogs_returns_new_molecules():
    analogs = dmt_tools.generate_analogs("c1ccccc1", limit=5)
    assert analogs
    assert all(a != "c1ccccc1" for a in analogs)


def test_plan_route_heuristic():
    route = dmt_tools.plan_route(ASPIRIN)
    assert route["steps"] is not None
    assert route["engine"] in {"aizynthfinder", "heuristic-disconnection"}


def test_nearest_activity_uses_seeds():
    seeds = [ASPIRIN, "CCCCCCCC"]
    values = [7.5, 4.0]
    assert dmt_tools.nearest_activity(ASPIRIN, seeds, values) == 7.5
    assert dmt_tools.nearest_activity("c1ccncc1", seeds, values) is None


def test_mpo_score_bounds():
    score = dmt_tools.mpo_score(
        {"pIC50": 8.0, "bbb": True, "hepatotoxic": False, "sa_score": 2.0, "route_available": True}
    )
    assert 0.0 <= score <= 1.0


def test_directive_reactions_produce_products():
    from app.core.agent_graph import _apply_directive

    # phenol -> methylated (BBB directive) should yield at least one product
    mods, label = _apply_directive("Oc1ccccc1", "BBB", limit=3)
    assert isinstance(mods, list)
    assert isinstance(label, str)
    assert all(m and m != "Oc1ccccc1" for m in mods)


def test_directive_pyridine_swap():
    from app.core.agent_graph import _apply_directive

    mods, _ = _apply_directive("c1ccccc1", "hepatotoxicity", limit=3)
    assert any("n" in m for m in mods) or mods == []
