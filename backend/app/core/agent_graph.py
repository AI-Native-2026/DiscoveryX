"""LangGraph multi-agent DMTA orchestration.

Four specialist agents cooperate in an iterative Design-Make-Test-Analyze loop:

  * **biologist**       target analysis (real PDB metadata + PMC evidence) and
                        end-of-round analysis / go-no-go decision
  * **chemist**         candidate generation from real MoleculeNet BACE actives
                        plus RDKit reaction-based analog enumeration
  * **retrosynthesis**  synthesis route planning (AiZynthFinder or heuristic)
  * **pharmacologist**  ADME-Tox prediction (ADMET-AI or RDKit heuristics)

The loop repeats until the objectives are met or ``rounds`` is exhausted. Every
LLM call is DLP-checked and metered; a guardrail denial aborts the workflow.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from app.core import dmt_tools
from app.core.errors import ValidationError
from app.core.guardrails import Guardrails, get_guardrails
from app.core.llm_factory import ChatMessage, LLMFactory, TokenLedger
from app.core.logging import get_logger
from app.core.rbac import Principal
from app.models.schemas import Candidate, DMTAReport, DMTARound

logger = get_logger("discoveryx.agents")

ProgressFn = Callable[..., Awaitable[None]]


class DiscoveryState(TypedDict, total=False):
    task_id: str
    trace_id: str
    hypothesis: str
    target: str
    pdb_id: str
    rounds: int
    objectives: list[str]
    round: int
    candidates: list[dict[str, Any]]
    history: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    target_summary: str
    decision: str
    met: bool
    directives: list[str]
    directive_labels: list[str]
    prev_candidates: list[str]
    action: str
    principal: dict[str, str]


# --------------------------------------------------------------------- helpers
def _principal_from(state: DiscoveryState) -> Principal:
    p = state.get("principal") or {}
    from app.core.rbac import get_policy

    return get_policy().build_principal(p.get("role", "scientist"), p.get("id", "anonymous"))


def _load_builtin_seeds(limit: int | None = None) -> tuple[list[str], list[float]]:
    """Built-in fallback library: real MoleculeNet BACE actives (has pIC50)."""
    from app.core.datasources import molecule_net
    from config.settings import get_settings

    settings = get_settings()
    path = settings.raw_dir / "bace.csv"
    if not path.exists():
        path = molecule_net.fetch_bace(settings.raw_dir)
    df = molecule_net.load_bace(path)
    smiles_col = "smiles" if "smiles" in df.columns else df.columns[0]
    pic50_col = "pIC50" if "pIC50" in df.columns else None
    if pic50_col is None:
        return [], []
    df = df.dropna(subset=[smiles_col, pic50_col])
    if limit:
        df = df.head(limit)
    return df[smiles_col].astype(str).tolist(), df[pic50_col].astype(float).tolist()


def _resolve_compounds(payload: dict[str, Any]) -> tuple[list[str], list[float | None], dict[str, Any]]:
    """Resolve the compound source for a run.

    A dataset supplied on the task takes precedence; otherwise the built-in
    MoleculeNet BACE library is used. Returns ``(smiles, activity, info)``.
    """
    dataset_id = payload.get("dataset_id")
    if dataset_id:
        from app.core.compounds import load_dataset_compounds

        table = load_dataset_compounds(
            dataset_id,
            smiles_column=payload.get("smiles_column"),
            activity_column=payload.get("activity_column"),
        )
        info = {
            "source": "dataset",
            "dataset_id": dataset_id,
            **table.summary(),
        }
        return table.smiles, table.activity, info

    smiles, pic50 = _load_builtin_seeds()
    info = {
        "source": "builtin",
        "dataset_id": "molecule_net_bace",
        "name": "MoleculeNet BACE (built-in)",
        "n_valid": len(smiles),
        "n_with_activity": len(pic50),
        "activity_kind": "continuous",
        "usable_for_dmta": True,
        "reason": "ok",
    }
    return smiles, list(pic50), info


def _top_actives(pairs: list[tuple[str, float]], n: int = 40) -> list[str]:
    """Most active measured compounds - used as design starting points."""
    ordered = sorted(pairs, key=lambda t: t[1], reverse=True)
    return [s for s, _ in ordered[:n]]


# Minimum predicted potency for a molecule to count as a development candidate.
# ADMET quality complements target activity: a small, soluble, non-toxic molecule
# with no predicted activity is a fragment rather than a hit.
MIN_POTENT_PIC50 = 6.5

# Objective -> literature query term, so the evidence search reflects the
# objectives the project actually set.
OBJECTIVE_QUERY_TERMS: dict[str, str] = {
    "BBB": "blood-brain barrier penetration",
    "hepatotoxicity": "hepatotoxicity",
    "solubility": "aqueous solubility",
}


def _dataset_rag_collections(dataset_id: str | None) -> list[str] | None:
    """RAG collections owned by a dataset.

    Returns the dataset's collection when it has been indexed, otherwise
    ``None`` so callers can skip retrieval rather than cite sources that belong
    to a different dataset.
    """
    if not dataset_id:
        return None
    try:
        from app.core.datasets import DatasetRegistry

        state = DatasetRegistry().index_state(dataset_id)
        collection = state.get("collection")
        return [str(collection)] if state.get("indexed") and collection else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("dataset index state lookup failed: %s", exc)
        return None


# Objective -> human-readable improvement directive, and the targeted reactions
# the chemist applies when an objective is not met in a round.
OBJECTIVE_DIRECTIVES: dict[str, str] = {
    "BBB": "降低 TPSA / 减少氢键供体，提升血脑屏障渗透",
    "hepatotoxicity": "移除苯胺/硝基等肝毒性结构警示，苯环→吡啶",
    "solubility": "降低 logP / 引入极性基团，改善溶解度",
    "potency": "引入卤素等增强与靶点结合",
}

DIRECTIVE_REACTIONS: dict[str, list[tuple[str, str]]] = {
    "BBB": [
        ("[OX2H:1]>>[O:1]C", "甲基化羟基，减少氢键供体"),
        ("[NX3;H2:1]>>[N:1]C", "甲基化伯胺，减少氢键供体"),
    ],
    "hepatotoxicity": [
        ("[NX3;H2:1]c1ccccc1>>[NX3;H2:1]c1ccncc1", "苯胺→氨基吡啶，规避肝毒性警示"),
        ("c1ccccc1>>c1ccncc1", "苯环→吡啶，降低亲脂性与代谢风险"),
    ],
    "solubility": [
        ("[cH:1]>>[c:1]O", "引入羟基，提升溶解度"),
        ("[cH:1]>>[c:1]N", "引入氨基，提升溶解度"),
    ],
    "potency": [
        ("[cH:1]>>[c:1]F", "引入氟原子，增强结合"),
    ],
}


def _apply_directive(smiles: str, directive: str, *, limit: int = 3) -> tuple[list[str], str]:
    """Apply the targeted reactions for one objective to a molecule."""
    from rdkit import Chem

    mol = dmt_tools.mol_from_smiles(smiles)
    if mol is None:
        return [], ""
    out: list[str] = []
    applied: list[str] = []
    for smirks, label in DIRECTIVE_REACTIONS.get(directive, []):
        prod = dmt_tools._apply_reaction(mol, smirks)
        if prod is None:
            continue
        smi = Chem.MolToSmiles(prod)
        if smi != smiles and smi not in out:
            out.append(smi)
            applied.append(label)
        if len(out) >= limit:
            break
    return out, ("；".join(applied) if applied else "")


def _candidate_metrics(smiles: str, activity_model: Any, admet: Any) -> dict[str, Any]:
    admet_result = admet(smiles)
    pic50 = activity_model(smiles)
    route = dmt_tools.plan_route(smiles)
    metrics = {
        "smiles": smiles,
        "pIC50": pic50,
        "bbb": admet_result.get("bbb"),
        "hepatotoxic": admet_result.get("hepatotoxic"),
        "herg": admet_result.get("herg_prob") if "herg_prob" in admet_result else admet_result.get("herg"),
        "solubility": admet_result.get("solubility"),
        "sa_score": dmt_tools.sa_score(smiles),
        "qed": dmt_tools.qed(smiles),
        "admet_engine": admet_result.get("engine"),
        "route_steps": route.get("steps"),
        "route_available": route.get("available"),
        "route_engine": route.get("engine"),
    }
    metrics["mpo"] = dmt_tools.mpo_score(metrics)
    return metrics


# ------------------------------------------------------------------ graph build
async def run_dmta_workflow(
    task_id: str,
    payload: dict[str, Any],
    trace_id: str,
    progress: ProgressFn | None = None,
) -> DMTAReport:
    from langgraph.graph import END, START, StateGraph

    guard: Guardrails = get_guardrails()
    ledger = TokenLedger()

    async def emit(stage: str, round_no: int, pct: float, message: str, **extra: Any) -> None:
        if progress:
            await progress(stage, round_no, pct, message, **extra)

    # ------------------------------------------------- data-driven setup
    from app.core.admet import get_predictor
    from app.core.qsar import train_activity_model
    from config.settings import get_settings

    seed_smiles, seed_activity, dataset_info = _resolve_compounds(payload)
    pairs = [(s, float(a)) for s, a in zip(seed_smiles, seed_activity, strict=False) if a is not None]
    if not pairs:
        raise ValidationError(
            f"dataset '{dataset_info.get('dataset_id')}' provides no usable activity: {dataset_info.get('reason')}"
        )

    await emit(
        "setup",
        0,
        0.05,
        f"loaded {len(seed_smiles)} compounds ({len(pairs)} with activity) from {dataset_info.get('dataset_id')}",
    )

    # Candidates are required to be novel relative to the measured dataset: its
    # compounds serve as design *starting points*, and every reported candidate is
    # a new molecule derived from them.
    known_smiles: set[str] = {
        std for s in seed_smiles if (std := dmt_tools.standardize_smiles(s)) is not None
    }

    activity_model, model_info = train_activity_model(
        seed_smiles,
        seed_activity,
        seed=int(payload.get("seed", 42)),
        dataset_id=dataset_info.get("dataset_id"),
        model_dir=get_settings().data_dir / "models",
    )
    await emit("setup", 0, 0.08, f"activity model: {model_info.kind} ({model_info.note})")

    admet = get_predictor()
    admet_cache: dict[str, dict[str, Any]] = {}
    pred_cache: dict[str, float | None] = {}

    def admet_one(smi: str) -> dict[str, Any]:
        if smi not in admet_cache:
            admet_cache[smi] = admet.predict([smi])[0]
        return admet_cache[smi]

    def predict_one(smi: str) -> float | None:
        if smi not in pred_cache:
            pred_cache[smi] = activity_model.predict([smi])[0]
        return pred_cache[smi]

    # ------------------------------------------------------------- biologist
    async def biologist(state: DiscoveryState) -> DiscoveryState:
        rnd = state.get("round", 0)
        await emit("target", rnd, 0.1, "biologist: analysing target and evidence")
        evidence: list[dict[str, Any]] = []

        # real PDB metadata
        pdb_title = ""
        pdb_resolution: Any = None
        try:
            from app.core.datasources import pdb

            meta = pdb.fetch_metadata(state["pdb_id"])
            pdb_title = str(meta.get("title") or "")
            pdb_resolution = meta.get("resolution")
            evidence.append({"type": "pdb", "id": state["pdb_id"], "title": meta.get("title"), "resolution": meta.get("resolution")})
        except Exception as exc:  # noqa: BLE001
            logger.warning("pdb metadata failed: %s", exc)

        # Real PMC evidence via RAG, scoped to this run's dataset: a MetAP2 run
        # must not be justified with BACE1 literature.
        try:
            from app.core.rag_engine import RAGEngine

            rag = RAGEngine()
            collections = _dataset_rag_collections(dataset_info.get("dataset_id"))
            if rag.status()["total_chunks"] > 0 and collections:
                terms = [
                    OBJECTIVE_QUERY_TERMS[o]
                    for o in (state.get("objectives") or [])
                    if o in OBJECTIVE_QUERY_TERMS
                ]
                query = " ".join([state["target"], "inhibitor", *terms]).strip()
                result = await rag.query(
                    query,
                    _principal_from(state),
                    top_k=3,
                    collections=collections,
                    guard=guard,
                    ledger=ledger,
                )
                for c in result.citations:
                    evidence.append({"type": "pmc", "id": c.id, "title": c.title, "score": c.score})
        except Exception as exc:  # noqa: BLE001
            logger.warning("rag evidence failed: %s", exc)

        # Target intelligence summary: grounded in the PDB entry and the sources
        # retrieved above, so the prose cannot drift from the evidence.
        target_summary = ""
        try:
            papers = [e for e in evidence if e.get("type") == "pmc"]
            source_lines = [f"- PDB {state['pdb_id']}: {pdb_title or 'structure'}"
                            + (f" (resolution {pdb_resolution})" if pdb_resolution else "")]
            source_lines += [f"- {e.get('title') or e.get('id')}" for e in papers[:4]]
            prompt = (
                f"Target: {state['target']}. Reference structure: {state['pdb_id']}. "
                f"Project hypothesis: {state['hypothesis']}. "
                f"Objectives: {', '.join(state.get('objectives') or []) or 'none'}.\n"
                f"Evidence available:\n" + "\n".join(source_lines) + "\n\n"
                "Write three concise sentences for a discovery scientist: what this target is, "
                "why it matters for this project, and what the evidence implies for inhibitor design. "
                "Use only the evidence listed; if it is thin, say so."
            )
            res = LLMFactory(ledger).complete(
                [
                    ChatMessage.system(
                        "You are a structural biologist supporting a drug-discovery team. "
                        "Ground every claim in the evidence provided and never invent data."
                    ),
                    ChatMessage.user(prompt),
                ],
                principal=_principal_from(state),
                guard=guard,
                purpose="target_summary",
            )
            target_summary = res.content.strip()[:600]
        except Exception as exc:  # noqa: BLE001 - summary is optional
            logger.warning("target summary failed: %s", exc)

        return {"evidence": evidence, "target_summary": target_summary}

    # --------------------------------------------------------------- chemist
    async def chemist(state: DiscoveryState) -> DiscoveryState:
        rnd = state.get("round", 0) + 1
        await emit("design", rnd, 0.25, f"chemist: designing candidates (round {rnd})")
        principal = _principal_from(state)
        limit = 8

        # design starting points: round 1 uses the dataset's most active compounds;
        # later rounds refine the previous round's best candidates using the
        # improvement directives produced by the analyze stage (feedback loop).
        directives = list(state.get("directives") or [])
        prev = list(state.get("prev_candidates") or [])
        generated: list[str] = []
        action = ""

        if rnd > 1 and prev and directives:
            applied: list[str] = []
            for smi in prev[:3]:
                generated.append(smi)
                for directive in directives:
                    mods, label = _apply_directive(smi, directive, limit=3)
                    generated.extend(mods)
                    if label:
                        applied.append(label)
            action = "定向修饰：" + "；".join(dict.fromkeys(applied)) if applied else ""
            if not applied:
                for smi in prev[:2]:
                    generated.append(smi)
                    generated.extend(dmt_tools.generate_analogs(smi, limit=4))
                action = "定向修饰无可用产物，回退到类似物枚举"
            await emit("design", rnd, 0.25, f"chemist: refining previous round ({action})")
        else:
            actives = _top_actives(pairs, n=40)
            if actives:
                start = ((rnd - 1) * 3) % max(1, len(actives))
                base_seeds = actives[start : start + 2] or actives[:2]
                for smi in base_seeds:
                    generated.append(smi)
                    generated.extend(dmt_tools.generate_analogs(smi, limit=4))
            action = "从数据集高活性分子出发，枚举类似物"

        # de-duplicate, standardize, keep valid and **novel** molecules only
        seen: set[str] = set()
        unique: list[str] = []
        dropped_known = 0
        for smi in generated:
            std = dmt_tools.standardize_smiles(smi)
            if std is None:
                continue
            if std in known_smiles:
                dropped_known += 1
                continue
            if std in seen:
                continue
            seen.add(std)
            unique.append(std)

        metrics = [_candidate_metrics(s, predict_one, admet_one) for s in unique[:limit]]
        metrics.sort(key=lambda m: m["mpo"], reverse=True)

        candidates: list[dict[str, Any]] = []
        for i, m in enumerate(metrics, 1):
            candidates.append({"id": i, **m})
        if dropped_known:
            action = (action + "；" if action else "") + f"已剔除 {dropped_known} 个数据集已知化合物"

        # LLM rationale for the top candidate (DLP-checked, metered)
        rationale = None
        try:
            llm = LLMFactory(ledger)
            top = candidates[0]
            prompt = (
                f"Target: {state['target']}. Hypothesis: {state['hypothesis']}. "
                f"Top candidate SMILES: {top['smiles']} with predicted pIC50 {top['pIC50']}, "
                f"BBB={top['bbb']}, hepatotoxic={top['hepatotoxic']}, SA={top['sa_score']}. "
                "In one sentence, explain the design rationale for a medicinal chemist."
            )
            res = llm.complete(
                [ChatMessage.system("You are a medicinal chemist. Be concise."), ChatMessage.user(prompt)],
                principal=principal,
                guard=guard,
                purpose="design_rationale",
            )
            rationale = res.content.strip()[:400]
        except Exception as exc:  # noqa: BLE001
            logger.warning("rationale LLM failed: %s", exc)
        if rationale and candidates:
            candidates[0]["rationale"] = rationale

        await emit(
            "design",
            rnd,
            0.4,
            f"chemist: {len(candidates)} novel candidates designed ({dropped_known} dataset compounds excluded)",
            candidates=len(candidates),
            excluded_known=dropped_known,
        )
        return {"candidates": candidates, "round": rnd, "action": action}

    # -------------------------------------------------------- retrosynthesis
    async def retrosynthesis(state: DiscoveryState) -> DiscoveryState:
        rnd = state.get("round", 1)
        await emit("make", rnd, 0.55, "retrosynthesis: planning routes")
        updated: list[dict[str, Any]] = []
        for c in state.get("candidates", []):
            route = dmt_tools.plan_route(c["smiles"])
            updated.append(
                {
                    **c,
                    "route_steps": route.get("steps"),
                    "route_available": route.get("available"),
                    "route_engine": route.get("engine"),
                }
            )
        return {"candidates": updated}

    # -------------------------------------------------------- pharmacologist
    async def pharmacologist(state: DiscoveryState) -> DiscoveryState:
        rnd = state.get("round", 1)
        await emit("test", rnd, 0.7, "pharmacologist: predicting ADME-Tox")
        updated: list[dict[str, Any]] = []
        for c in state.get("candidates", []):
            result = admet_one(c["smiles"])
            merged = {
                **c,
                "bbb": result.get("bbb"),
                "hepatotoxic": result.get("hepatotoxic"),
                "herg": result.get("herg_prob") if "herg_prob" in result else result.get("herg"),
                "solubility": result.get("solubility"),
                "admet_engine": result.get("engine"),
            }
            merged["pIC50"] = predict_one(c["smiles"])
            merged["mpo"] = dmt_tools.mpo_score(merged)
            updated.append(merged)
        return {"candidates": updated}

    # ---------------------------------------------------------------- analyze
    async def analyze(state: DiscoveryState) -> DiscoveryState:
        rnd = state.get("round", 1)
        objectives = set(state.get("objectives", []))
        cands = state.get("candidates", [])

        passed = [
            c
            for c in cands
            if (c.get("pIC50") or 0) >= MIN_POTENT_PIC50
            and ("BBB" not in objectives or c.get("bbb"))
            and ("hepatotoxicity" not in objectives or c.get("hepatotoxic") is False)
            and (c.get("route_available") is not False)
        ]
        met = len(passed) >= 2

        summary = f"round {rnd}: {len(cands)} candidates, {len(passed)} passed all objectives"
        decision = (
            "Objectives met - candidates are ready for synthesis and assay."
            if met
            else "Objectives not yet met - refine the series in the next round."
        )

        # ---- feedback: which objectives failed, and what to change next round
        failures: list[str] = []
        if "BBB" not in objectives or sum(1 for c in cands if c.get("bbb")) < max(1, len(cands) // 2):
            if "BBB" in objectives:
                failures.append("BBB")
        if "hepatotoxicity" in objectives and sum(1 for c in cands if c.get("hepatotoxic")) > 0:
            failures.append("hepatotoxicity")
        if "solubility" in objectives and sum(1 for c in cands if (c.get("solubility") or 0) < -6) > len(cands) // 2:
            failures.append("solubility")
        if sum(1 for c in cands if (c.get("pIC50") or 0) >= MIN_POTENT_PIC50) < max(1, len(cands) // 2):
            failures.append("potency")

        directives = list(failures) if not met else []
        directive_labels = [OBJECTIVE_DIRECTIVES[f] for f in failures if f in OBJECTIVE_DIRECTIVES] if not met else []
        prev_candidates = [c["smiles"] for c in sorted(cands, key=lambda c: c.get("mpo", 0), reverse=True)[:4]]

        # Narrative summary for the discovery team. The pass/fail decision above
        # stays deterministic; the model only puts the numbers into words.
        narrative = ""
        try:
            pic50s = sorted((c.get("pIC50") or 0) for c in cands)
            median = pic50s[len(pic50s) // 2] if pic50s else 0.0
            prompt = (
                f"Target: {state['target']}. Objectives: {', '.join(sorted(objectives)) or 'none'}. "
                f"Round {rnd}: {len(cands)} candidates, {len(passed)} passed every objective, "
                f"median predicted pIC50 {median:.2f}. "
                f"Unmet: {', '.join(failures) or 'none'}. "
                f"Next actions: {'; '.join(directive_labels) or 'advance the series'}. "
                "Write at most two sentences for a discovery team: what this round means and what to do next. "
                "Do not invent numbers."
            )
            res = LLMFactory(ledger).complete(
                [
                    ChatMessage.system(
                        "You are the lead biologist on a DMTA team. Be concrete and concise; "
                        "use only the numbers given to you."
                    ),
                    ChatMessage.user(prompt),
                ],
                principal=_principal_from(state),
                guard=guard,
                purpose="decision_narrative",
            )
            narrative = res.content.strip()[:400]
        except Exception as exc:  # noqa: BLE001 - narrative is optional
            logger.warning("decision narrative failed: %s", exc)

        history = list(state.get("history", []))
        history.append(
            {
                "round": rnd,
                "n_candidates": len(cands),
                "n_passed": len(passed),
                "met": met,
                "summary": summary,
                "action": state.get("action", ""),
                "directives": directives,
                "directive_labels": directive_labels,
                "narrative": narrative,
            }
        )
        await emit(
            "analyze",
            rnd,
            0.85,
            f"biologist: {summary}",
            passed=len(passed),
            met=met,
            directives=len(directives),
        )
        return {
            "history": history,
            "met": met,
            "decision": decision,
            "directives": directives,
            "directive_labels": directive_labels,
            "prev_candidates": prev_candidates,
        }

    # ------------------------------------------------------------- routing
    def route_after_analyze(state: DiscoveryState) -> str:
        if state.get("met"):
            return "end"
        if state.get("round", 0) >= state.get("rounds", 3):
            return "end"
        return "chemist"

    graph = StateGraph(DiscoveryState)
    graph.add_node("biologist", biologist)
    graph.add_node("chemist", chemist)
    graph.add_node("retrosynthesis", retrosynthesis)
    graph.add_node("pharmacologist", pharmacologist)
    graph.add_node("analyze", analyze)

    graph.add_edge(START, "biologist")
    graph.add_edge("biologist", "chemist")
    graph.add_edge("chemist", "retrosynthesis")
    graph.add_edge("retrosynthesis", "pharmacologist")
    graph.add_edge("pharmacologist", "analyze")
    graph.add_conditional_edges("analyze", route_after_analyze, {"chemist": "chemist", "end": END})

    app = graph.compile()

    initial: DiscoveryState = {
        "task_id": task_id,
        "trace_id": trace_id,
        "hypothesis": payload.get("hypothesis", ""),
        "target": payload.get("target", "BACE1"),
        "pdb_id": payload.get("pdb_id") or "4WY1",
        "rounds": int(payload.get("rounds", 3)),
        "objectives": payload.get("objectives", ["BBB", "hepatotoxicity"]),
        "round": 0,
        "candidates": [],
        "history": [],
        "evidence": [],
        "principal": payload.get("_principal", {"role": "scientist", "id": "anonymous"}),
    }

    final = await app.ainvoke(initial, config={"recursion_limit": 50})

    # Report candidates: collapse duplicates (the same molecule can be proposed in
    # several rounds) and rank potent matter first, so the report headlines
    # development candidates.
    unique: dict[str, dict[str, Any]] = {}
    for c in final.get("candidates", []):
        key = str(c.get("smiles") or c.get("id") or "")
        if not key:
            continue
        prev = unique.get(key)
        if prev is None or c.get("mpo", 0) > prev.get("mpo", 0):
            unique[key] = c
    pool = list(unique.values())
    potent = [c for c in pool if (c.get("pIC50") or 0) >= MIN_POTENT_PIC50]
    top = sorted(potent or pool, key=lambda c: c.get("mpo", 0), reverse=True)[:5]
    rounds_out = [
        DMTARound(
            round=h["round"],
            passed=h["n_passed"],
            summary=h["summary"],
            decision="met" if h["met"] else "iterate",
            action=h.get("action", ""),
            directives=h.get("directives", []),
            directive_labels=h.get("directive_labels", []),
            narrative=h.get("narrative", ""),
        )
        for h in final.get("history", [])
    ]

    return DMTAReport(
        task_id=task_id,
        target=final.get("target", ""),
        hypothesis=final.get("hypothesis", ""),
        target_summary=final.get("target_summary", ""),
        objectives=list(final.get("objectives") or []),
        rounds=rounds_out,
        top_candidates=[Candidate.model_validate(c) for c in top],
        decision=final.get("decision", ""),
        evidence=final.get("evidence", []),
        token_usage=ledger.snapshot(),
        dataset=dataset_info,
        activity_model=model_info.model_dump(mode="json"),
        admet_engine=admet.engine,
    )
