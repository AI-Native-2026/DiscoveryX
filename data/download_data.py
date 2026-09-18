#!/usr/bin/env python3
"""Download real public data and lay it out as **directory-based datasets**.

Every sub-directory of ``data/datasets`` is one dataset (e.g. ``AAA/`` may hold
many PDFs, Excel sheets, CSVs …). A ``dataset.json`` in the directory declares
its metadata (name, type, sensitivity, purpose).

Datasets produced (all real sources):
  * ``pmc_bace1_literature/``    PMC open-access articles (one file per article)
  * ``molecule_net_bace/``       MoleculeNet BACE (CSV + XLSX) — default DMTA source
  * ``pdb_bace1_structures/``    BACE1 crystal structures (mmCIF)
  * ``chembl_ache_activities/``  ChEMBL acetylcholinesterase activity data (CSV)
  * ``chembl_casp3_activities/`` ChEMBL caspase-3 activity data (CSV)
  * ``chembl_metap2_activities/`` ChEMBL MetAP2 activity data (CSV)
  * ``chembl_egfr_activities/``  ChEMBL EGFR activity data (CSV)
  * ``bace1_dmta_results/``      platform-generated DMTA run results (confidential)

Usage:
    python data/download_data.py                 # build all datasets
    python data/download_data.py --index         # also index documents into RAG
    python data/download_data.py --only pmc_bace1_literature
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

RAW_DIR = REPO_ROOT / "data" / "raw"
DATASETS_DIR = REPO_ROOT / "data" / "datasets"
MANIFEST = REPO_ROOT / "data" / "manifest.json"

PMC_QUERIES = [
    "BACE1 inhibitor blood-brain barrier",
    "BACE1 inhibitor hepatotoxicity",
    "BACE1 amyloid precursor protein cleavage inhibitor",
    "Alzheimer BACE1 drug discovery CNS penetration",
]
BACE1_PDBS = ["4WY1", "1FKN", "2ZHR", "3TPJ", "4IVT", "3CIB", "2OHL", "1M4H"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_meta(directory: Path, meta: dict) -> None:
    (directory / "dataset.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def build_pmc() -> list[dict]:
    """One text + one JSON file per PMC article (real open-access literature)."""
    from app.core.datasources import pmc

    d = DATASETS_DIR / "pmc_bace1_literature"
    d.mkdir(parents=True, exist_ok=True)
    seen: dict[str, dict] = {}
    for q in PMC_QUERIES:
        for art in pmc.search_europepmc(q, retmax=15):
            key = art.get("pmcid") or art.get("pmid") or art.get("doi")
            if key and key not in seen:
                seen[key] = art

    for key, art in seen.items():
        safe = key.replace("/", "_")
        (d / f"{safe}.txt").write_text(
            f"{art.get('title','')}\n\n{art.get('abstract','')}\n\n"
            f"Journal: {art.get('journal','')} ({art.get('year','')})\nAuthors: {', '.join(art.get('authors', []))}\n",
            encoding="utf-8",
        )
        (d / f"{safe}.json").write_text(json.dumps(art, ensure_ascii=False, indent=2), encoding="utf-8")

    write_meta(
        d,
        {
            "name": "PMC BACE1 literature",
            "data_type": "document",
            "source": "Europe PMC",
            "sensitivity": "public",
            "purpose": "rag",
            "description": "Open-access articles on BACE1 inhibitors, BBB penetration and hepatotoxicity.",
        },
    )
    return [{"dataset": d.name, "files": len(seen) * 2, "source": "Europe PMC"}]


def build_molecule_net() -> list[dict]:
    """MoleculeNet BACE: the default DMTA compound source (SMILES + pIC50)."""
    from app.core.datasources import molecule_net

    d = DATASETS_DIR / "molecule_net_bace"
    d.mkdir(parents=True, exist_ok=True)
    csv_path = molecule_net.fetch_bace(RAW_DIR)
    (d / "bace.csv").write_bytes(csv_path.read_bytes())

    try:
        import pandas as pd

        df = pd.read_csv(csv_path)
        # a clean compound table for the DMTA workflow (unambiguous columns)
        if {"mol", "pIC50"}.issubset(df.columns):
            df[["mol", "pIC50"]].rename(columns={"mol": "smiles"}).dropna().to_csv(
                d / "bace_compounds.csv", index=False
            )
        cols = [c for c in ["mol", "CID", "Class", "pIC50", "MW", "AlogP", "HBA", "HBD", "RB", "PSA"] if c in df.columns]
        with pd.ExcelWriter(d / "bace_activity.xlsx", engine="openpyxl") as writer:
            df[cols].head(2000).to_excel(writer, index=False, sheet_name="BACE_activity")
            summary = (
                df.groupby("Class")["pIC50"].agg(["count", "mean", "min", "max"]).reset_index()
                if "Class" in df.columns
                else df.describe()
            )
            summary.to_excel(writer, index=False, sheet_name="summary")
    except Exception as exc:  # noqa: BLE001
        print(f"      WARN: xlsx export skipped ({exc})")

    write_meta(
        d,
        {
            "name": "MoleculeNet BACE",
            "data_type": "tabular",
            "source": "DeepChem / MoleculeNet",
            "sensitivity": "public",
            "purpose": "tool",
            "description": "BACE-1 binding data (pIC50) — usable as a DMTA compound source (SMILES + activity).",
        },
    )
    return [{"dataset": d.name, "files": len(list(d.glob("*"))), "source": "MoleculeNet"}]


def build_pdb() -> list[dict]:
    """BACE1 crystal structures (real mmCIF files)."""
    from app.core.datasources import pdb

    d = DATASETS_DIR / "pdb_bace1_structures"
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    for pid in BACE1_PDBS:
        try:
            pdb.fetch_structure(pid, d)
            n += 1
        except Exception as exc:  # noqa: BLE001
            print(f"      WARN: {pid} failed ({exc})")
    write_meta(
        d,
        {
            "name": "BACE1 crystal structures",
            "data_type": "structure",
            "source": "RCSB PDB",
            "sensitivity": "public",
            "purpose": "file",
            "description": "BACE1 (beta-secretase) structures used for target and pocket analysis.",
        },
    )
    return [{"dataset": d.name, "files": n, "source": "RCSB PDB"}]


CHEMBL_TARGETS: dict[str, dict[str, str]] = {
    "chembl_metap2_activities": {
        "target_id": "CHEMBL3922",
        "target_name": "Methionine aminopeptidase 2",
        "name": "ChEMBL MetAP2 activities",
        "description": (
            "Methionine aminopeptidase 2 (CHEMBL3922) IC50 records, cleaned: uncensored "
            "nM measurements only, one median pIC50 per molecule across assays."
        ),
    },
    "chembl_casp3_activities": {
        "target_id": "CHEMBL2334",
        "target_name": "Caspase-3",
        "name": "ChEMBL Caspase-3 activities",
        "description": (
            "Caspase-3 (CHEMBL2334) IC50 records, cleaned: uncensored nM measurements "
            "only, one median pIC50 per molecule across assays."
        ),
    },
    "chembl_ache_activities": {
        "target_id": "CHEMBL220",
        "target_name": "Acetylcholinesterase",
        "name": "ChEMBL AChE activities",
        "description": (
            "Acetylcholinesterase (CHEMBL220) IC50 records, cleaned: uncensored nM "
            "measurements only, one median pIC50 per molecule across assays."
        ),
    },
    "chembl_egfr_activities": {
        "target_id": "CHEMBL203",
        "target_name": "EGFR",
        "name": "ChEMBL EGFR activities",
        "description": (
            "EGFR (CHEMBL203) IC50 records, cleaned: uncensored nM measurements only, "
            "one median pIC50 per molecule across assays."
        ),
    },
}


def _trainable_ic50(record: dict) -> bool:
    """Keep only exact, same-unit IC50 measurements usable as a regression label."""
    if str(record.get("standard_type")) != "IC50":
        return False
    if str(record.get("standard_relation")) != "=":
        return False
    if str(record.get("standard_units")) != "nM":
        return False
    try:
        float(record["pchembl_value"])
    except (KeyError, TypeError, ValueError):
        return False
    return bool(record.get("canonical_smiles"))


def build_chembl_target(dataset_id: str) -> list[dict]:
    """ChEMBL activity data for one target, as a trainable CSV.

    Raw ChEMBL exports are not directly trainable:

    * the same molecule is assayed many times with spreads of up to several log
      units between cell lines/conditions, so the label is ambiguous;
    * censored measurements (``>``, ``<``, ``~``) carry no exact value;
    * a few rows report other units.

    We therefore keep uncensored IC50 in nM and collapse each molecule to the
    **median** pIC50 across its assays — one unambiguous label per molecule.
    """
    import csv
    import statistics
    from collections import defaultdict

    from app.core.datasources.chembl import ChEMBLClient

    spec = CHEMBL_TARGETS[dataset_id]
    d = DATASETS_DIR / dataset_id
    d.mkdir(parents=True, exist_ok=True)
    client = ChEMBLClient(cache_dir=RAW_DIR / "chembl_cache")
    records = client.activities(spec["target_id"], max_records=4000)

    fields = [
        "molecule_chembl_id", "canonical_smiles", "standard_type", "standard_value",
        "standard_units", "standard_relation", "pchembl_value", "document_year",
        "target_chembl_id", "assay_chembl_id",
    ]

    by_mol: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if _trainable_ic50(r):
            by_mol[str(r["canonical_smiles"])].append(r)

    rows: list[dict] = []
    for smiles, group in by_mol.items():
        values = [float(r["pchembl_value"]) for r in group]
        median = statistics.median(values)
        rep = max(group, key=lambda r: float(r["pchembl_value"]))
        row = {k: rep.get(k, "") for k in fields}
        row["canonical_smiles"] = smiles
        row["pchembl_value"] = f"{median:.2f}"
        row["n_measurements"] = len(values)
        rows.append(row)
    rows.sort(key=lambda r: float(r["pchembl_value"]), reverse=True)

    out = d / "activities.csv"
    with open(out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[*fields, "n_measurements"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    write_meta(
        d,
        {
            "name": spec["name"],
            "data_type": "tabular",
            "source": "ChEMBL (EBI)",
            "sensitivity": "public",
            "purpose": "tool",
            "description": spec["description"],
            "target": spec["target_name"],
            "n_molecules": len(rows),
        },
    )
    return [{"dataset": d.name, "files": 1, "source": "ChEMBL"}]


def _make_chembl_builder(dataset_id: str):  # type: ignore[no-untyped-def]
    """Bind a builder for one entry of CHEMBL_TARGETS."""

    def _builder() -> list[dict]:
        return build_chembl_target(dataset_id)

    _builder.__name__ = f"build_{dataset_id}"
    return _builder


def build_dmta_results() -> list[dict]:
    """Export platform-generated DMTA run results as an internal dataset."""
    import redis as redis_lib

    from config.settings import get_settings

    d = DATASETS_DIR / "bace1_dmta_results"
    d.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    n = 0
    try:
        client = redis_lib.from_url(settings.redis_url, decode_responses=True)
        for key in client.scan_iter("dx:task:*", count=200):
            raw = client.get(key)
            if not raw:
                continue
            try:
                state = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            if state.get("status") != "succeeded" or not state.get("result"):
                continue
            tid = state["task_id"]
            report = state["result"]
            (d / f"{tid}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            lines = [
                f"DMTA run {tid}",
                f"target: {report.get('target')}",
                f"hypothesis: {report.get('hypothesis')}",
                f"decision: {report.get('decision')}",
                "",
                "rounds:",
            ]
            lines += [f"  R{r.get('round')}: {r.get('summary')}" for r in report.get("rounds", [])]
            lines.append("")
            lines.append("top candidates:")
            for c in report.get("top_candidates", []):
                lines.append(
                    f"  #{c.get('id')} {c.get('smiles')} pIC50={c.get('pIC50')} BBB={c.get('bbb')} "
                    f"hepatotoxic={c.get('hepatotoxic')} SA={c.get('sa_score')} MPO={c.get('mpo')}"
                )
            (d / f"{tid}.txt").write_text("\n".join(lines), encoding="utf-8")
            n += 1
    except Exception as exc:  # noqa: BLE001
        print(f"      WARN: could not export DMTA results ({exc})")

    write_meta(
        d,
        {
            "name": "BACE1 DMTA run results (confidential)",
            "data_type": "document",
            "source": "DiscoveryX platform",
            "sensitivity": "confidential",
            "purpose": "rag",
            "description": "Candidate triage results produced by DiscoveryX DMTA runs — confidential R&D output.",
            "owner": "discoveryx",
        },
    )
    return [{"dataset": d.name, "files": n * 2, "source": "DiscoveryX"}]


BUILDERS = {
    "pmc_bace1_literature": build_pmc,
    "molecule_net_bace": build_molecule_net,
    "pdb_bace1_structures": build_pdb,
    "bace1_dmta_results": build_dmta_results,
    **{ds: _make_chembl_builder(ds) for ds in CHEMBL_TARGETS},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build DiscoveryX dataset directories from real sources")
    parser.add_argument("--only", default=None, help="Build only this dataset directory")
    parser.add_argument("--index", action="store_true", help="Index document datasets into the RAG knowledge base")
    args = parser.parse_args()

    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    results: list[dict] = []

    names = [args.only] if args.only else list(BUILDERS)
    for i, name in enumerate(names, 1):
        if name not in BUILDERS:
            print(f"unknown dataset '{name}' (have: {', '.join(BUILDERS)})", file=sys.stderr)
            return 1
        print(f"[{i}/{len(names)}] building {name} …")
        try:
            results.extend(BUILDERS[name]())
        except Exception as exc:  # noqa: BLE001
            print(f"      ERROR: {name} failed: {exc}", file=sys.stderr)

    for info in results:
        d = DATASETS_DIR / info["dataset"]
        for f in d.rglob("*"):
            if f.is_file() and f.name != "dataset.json":
                manifest.append(
                    {
                        "dataset": info["dataset"],
                        "file": f.relative_to(REPO_ROOT).as_posix(),
                        "bytes": f.stat().st_size,
                        "sha256": sha256(f),
                    }
                )
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nmanifest written to {MANIFEST} ({len(manifest)} files)")

    if args.index:
        print("\n[index] indexing document datasets into the knowledge base …")
        from app.core.datasets import DatasetRegistry
        from app.core.rag_engine import RAGEngine

        engine = RAGEngine()
        reg = DatasetRegistry()
        for info in reg.list():
            if info.purpose.value != "rag":
                continue
            docs = [
                {
                    "id": doc["id"],
                    "text": doc["text"],
                    "title": doc["metadata"].get("file", info.id),
                    "journal": info.source,
                    "year": "",
                }
                for doc in reg.documents(info.id)
            ]
            if not docs:
                continue
            collection = f"kb_{info.sensitivity.value}_{info.id}"
            chunks = engine.index_documents(
                docs, collection=collection, sensitivity=info.sensitivity.value, source=f"dataset:{info.id}"
            )
            reg.mark_indexed(info.id, chunks=chunks, collection=collection)
            print(f"  {info.id}: {len(docs)} docs -> {chunks} chunks ({collection})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
