"""Shared molecular featurisation: Morgan fingerprint + RDKit descriptors.

Used by the dataset-specific QSAR model in the DMTA workflow.
"""

from __future__ import annotations

from typing import Any

DESCRIPTOR_NAMES = [
    "MolWt", "MolLogP", "TPSA", "HBD", "HBA", "RotB", "AromaticRings", "HeavyAtoms",
    "NumRings", "FractionCSP3", "NumHeteroatoms", "NumValenceElectrons", "MaxPartialCharge",
    "MinPartialCharge", "LabuteASA", "BalabanJ", "BertzCT", "Chi0", "Chi1", "Chi2n", "Chi3n",
    "Kappa1", "Kappa2", "Kappa3", "HallKierAlpha", "MolMR", "NumAmideBonds",
    "NumSaturatedRings", "NumAliphaticRings", "NumSpiroAtoms", "NumBridgeheadAtoms",
]

FP_BITS = 2048


def descriptor_vector(mol: Any) -> list[float]:
    from rdkit.Chem import Crippen, Descriptors, rdMolDescriptors

    def safe(fn: Any) -> float:
        try:
            v = fn(mol)
            return float(v) if v is not None else 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    return [
        safe(Descriptors.MolWt),
        safe(Crippen.MolLogP),
        safe(Descriptors.TPSA),
        safe(rdMolDescriptors.CalcNumHBD),
        safe(rdMolDescriptors.CalcNumHBA),
        safe(rdMolDescriptors.CalcNumRotatableBonds),
        safe(rdMolDescriptors.CalcNumAromaticRings),
        float(mol.GetNumHeavyAtoms()),
        safe(rdMolDescriptors.CalcNumRings),
        safe(rdMolDescriptors.CalcFractionCSP3),
        safe(rdMolDescriptors.CalcNumHeteroatoms),
        safe(Descriptors.NumValenceElectrons),
        safe(Descriptors.MaxPartialCharge),
        safe(Descriptors.MinPartialCharge),
        safe(Descriptors.LabuteASA),
        safe(Descriptors.BalabanJ),
        safe(Descriptors.BertzCT),
        safe(Descriptors.Chi0),
        safe(Descriptors.Chi1),
        safe(Descriptors.Chi2n),
        safe(Descriptors.Chi3n),
        safe(Descriptors.Kappa1),
        safe(Descriptors.Kappa2),
        safe(Descriptors.Kappa3),
        safe(Descriptors.HallKierAlpha),
        safe(Crippen.MolMR),
        safe(rdMolDescriptors.CalcNumAmideBonds),
        safe(rdMolDescriptors.CalcNumSaturatedRings),
        safe(rdMolDescriptors.CalcNumAliphaticRings),
        safe(rdMolDescriptors.CalcNumSpiroAtoms),
        safe(rdMolDescriptors.CalcNumBridgeheadAtoms),
    ]


def featurize(smiles: list[str]) -> Any:
    """Return an ``(n, FP_BITS + len(DESCRIPTOR_NAMES))`` float32 matrix."""
    import numpy as np
    from rdkit import Chem, DataStructs, RDLogger
    from rdkit.Chem import AllChem

    RDLogger.DisableLog("rdApp.*")
    n_desc = len(DESCRIPTOR_NAMES)
    rows = []
    for smi in smiles:
        mol = Chem.MolFromSmiles(smi) if isinstance(smi, str) else None
        if mol is None:
            rows.append(np.zeros(FP_BITS + n_desc, dtype=np.float32))
            continue
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=FP_BITS)
        bits = np.zeros(FP_BITS, dtype=np.float32)
        DataStructs.ConvertToNumpyArray(fp, bits)
        rows.append(np.concatenate([bits, np.array(descriptor_vector(mol), dtype=np.float32)]))
    return np.vstack(rows)
