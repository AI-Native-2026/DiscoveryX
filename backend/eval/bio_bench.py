"""Automated bio-activity / drug-likeness scoring (real tools).

Scores molecules with RDKit (descriptors, QED, SA score, structural alerts) and
optionally ADMET-AI, then aggregates a benchmark table. Can run standalone::

    python -m eval.bio_bench --dataset data/raw/bace.csv --limit 200
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.core import dmt_tools


def score_molecule(smiles: str) -> dict[str, Any]:
    desc = dmt_tools.descriptors(smiles) or {}
    admet = dmt_tools.predict_admet(smiles)
    return {
        "smiles": smiles,
        "valid": bool(desc),
        **{k: desc.get(k) for k in ("mw", "logp", "tpsa", "hbd", "hba", "rotatable")},
        "qed": dmt_tools.qed(smiles),
        "sa_score": dmt_tools.sa_score(smiles),
        "lipinski_violations": dmt_tools.lipinski_violations(smiles),
        "bbb": admet.get("bbb"),
        "hepatotoxic": admet.get("hepatotoxic"),
        "solubility": admet.get("solubility"),
        "admet_engine": admet.get("engine"),
    }


def score_batch(smiles_list: list[str]) -> list[dict[str, Any]]:
    return [score_molecule(s) for s in smiles_list]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in rows if r.get("valid")]
    n = len(valid) or 1

    def mean(key: str) -> float | None:
        vals = [r[key] for r in valid if isinstance(r.get(key), int | float)]
        return round(sum(vals) / len(vals), 3) if vals else None

    return {
        "n_total": len(rows),
        "n_valid": len(valid),
        "valid_fraction": round(len(valid) / (len(rows) or 1), 3),
        "mean_mw": mean("mw"),
        "mean_logp": mean("logp"),
        "mean_tpsa": mean("tpsa"),
        "mean_qed": mean("qed"),
        "mean_sa": mean("sa_score"),
        "lipinski_pass_fraction": round(
            sum(1 for r in valid if (r.get("lipinski_violations") or 0) <= 1) / n, 3
        ),
        "bbb_pass_fraction": round(sum(1 for r in valid if r.get("bbb")) / n, 3),
        "hepatotox_rate": round(sum(1 for r in valid if r.get("hepatotoxic")) / n, 3),
    }


def benchmark_dataset(dataset: str | Path, *, limit: int = 200) -> dict[str, Any]:
    """Run the benchmark over a MoleculeNet-style CSV (real data)."""
    import pandas as pd

    df = pd.read_csv(dataset)
    smiles_col = "smiles" if "smiles" in df.columns else df.columns[0]
    smiles = df[smiles_col].dropna().astype(str).head(limit).tolist()
    rows = score_batch(smiles)
    return {"dataset": str(dataset), "summary": summarize(rows), "rows": rows[:50]}


def main() -> int:
    parser = argparse.ArgumentParser(description="DiscoveryX bio-activity benchmark")
    parser.add_argument("--dataset", required=True, help="CSV with a smiles column (e.g. MoleculeNet BACE)")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--out", default=None, help="Optional JSON output path")
    args = parser.parse_args()

    result = benchmark_dataset(args.dataset, limit=args.limit)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
