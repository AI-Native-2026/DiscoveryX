"""Professional HTML report generation for a DMTA run.

Produces a self-contained, print-ready HTML document (use the browser's
"Print → Save as PDF") with:

  * executive summary and decision
  * iteration table
  * candidate table with **real RDKit-rendered 2D structures**
  * ADME-Tox radar and multi-parameter-optimization bars (inline SVG)
  * evidence / citations
  * token bill and run manifest
"""

from __future__ import annotations

import html
import math
import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger("discoveryx.report")

# ------------------------------------------------------------- display labels
# Raw enum values from the API are mapped to readable labels so the report never
# shows internal tokens such as "continuous", "qsar" or "succeeded".
ACTIVITY_KIND_LABELS = {"continuous": "连续值 (pIC50)", "binary": "二分类", "none": "无"}
MODEL_KIND_LABELS = {"qsar": "QSAR (LightGBM)", "knn": "k-NN 相似度", "none": "无"}
ENGINE_LABELS = {"admet_ai": "ADMET-AI", "rdkit-heuristic": "RDKit 启发式"}
STATUS_LABELS = {
    "queued": "排队中",
    "running": "运行中",
    "succeeded": "已完成",
    "failed": "失败",
    "blocked": "已拦截",
}
EVIDENCE_LABELS = {"pdb": "PDB 结构", "pmc": "文献", "dataset": "数据集"}
ROUND_DECISION_LABELS = {"met": "已达成", "iterate": "继续迭代"}

DECISION_ZH = {
    "Objectives met - candidates are ready for synthesis and assay.": "目标已达成，候选化合物可进入合成与活性验证。",
    "Objectives not yet met - refine the series in the next round.": "目标尚未全部达成，下一轮继续优化该系列。",
}


def _label(mapping: dict[str, str], value: Any) -> str:
    if value in (None, ""):
        return ""
    return mapping.get(str(value), str(value))


def _localize_decision(text: Any) -> str:
    if not text:
        return ""
    return DECISION_ZH.get(str(text), str(text))


def _localize_summary(text: Any) -> str:
    """Render the workflow's round summary in Chinese."""
    s = str(text or "")
    m = re.match(r"round (\d+): (\d+) candidates, (\d+) passed all objectives", s)
    if m:
        return "第 {} 轮：{} 个候选，{} 个通过全部目标".format(*m.groups())
    return s


def _rel_path(path: Any) -> str:
    """Show a repo-relative model path instead of an absolute server path."""
    if not path:
        return ""
    s = str(path).replace("\\", "/")
    marker = "/data/models/"
    i = s.find(marker)
    return "data/models/" + s[i + len(marker) :] if i >= 0 else s.rsplit("/", 1)[-1]


def _short_id(value: Any) -> str:
    """Strip a collection prefix from a document id for display."""
    s = str(value or "")
    return s.rsplit(":", 1)[-1] if ":" in s else s


def _fmt_resolution(value: Any) -> str:
    if isinstance(value, list | tuple) and value:
        return f"{value[0]} Å"
    if value:
        return f"{value} Å"
    return "—"


# ------------------------------------------------------------------ helpers
def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _mol_svg(smiles: str, w: int = 220, h: int = 150) -> str:
    """Render a molecule to inline SVG with RDKit (real 2D depiction)."""
    try:
        from rdkit import Chem, RDLogger
        from rdkit.Chem.Draw import rdMolDraw2D

        RDLogger.DisableLog("rdApp.*")
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return '<div class="mol-missing">invalid SMILES</div>'
        drawer = rdMolDraw2D.MolDraw2DSVG(w, h)
        opts = drawer.drawOptions()
        opts.bondLineWidth = 1.6
        opts.padding = 0.08
        rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
        drawer.FinishDrawing()
        svg = drawer.GetDrawingText()
        start = svg.find("<svg")
        return svg[start:] if start >= 0 else svg
    except Exception as exc:  # noqa: BLE001
        logger.warning("mol svg failed: %s", exc)
        return '<div class="mol-missing">n/a</div>'


def _radar_svg(axes: list[tuple[str, float]], size: int = 260) -> str:
    c = size / 2
    R = size * 0.34
    n = max(1, len(axes))

    def pt(i: int, v: float) -> tuple[float, float]:
        a = -math.pi / 2 + (i * 2 * math.pi) / n
        return c + R * v * math.cos(a), c + R * v * math.sin(a)

    parts = []
    for r in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, r) for i in range(n)))
        parts.append(f'<polygon points="{pts}" class="ring"/>')
    for i, (label, _) in enumerate(axes):
        x, y = pt(i, 1)
        parts.append(f'<line x1="{c}" y1="{c}" x2="{x:.1f}" y2="{y:.1f}" class="spoke"/>')
        lx, ly = pt(i, 1.24)
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" class="axis">{_esc(label)}</text>')
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, max(0.0, min(1.0, v))) for i, (_, v) in enumerate(axes)))
    parts.append(f'<polygon points="{poly}" class="shape"/>')
    return f'<svg viewBox="0 0 {size} {size}" class="radar">{"".join(parts)}</svg>'


def _bars_svg(items: list[tuple[str, float]], max_v: float = 1.0, width: int = 320, row: int = 26) -> str:
    h = max(row, row * len(items))
    parts = []
    for i, (label, v) in enumerate(items):
        y = i * row + 6
        w = max(0.0, min(1.0, v / max_v)) * (width - 120)
        parts.append(f'<text x="0" y="{y + 11}" class="bar-label">{_esc(label)}</text>')
        parts.append(f'<rect x="60" y="{y}" width="{width - 120}" height="12" rx="6" class="bar-track"/>')
        parts.append(f'<rect x="60" y="{y}" width="{w:.1f}" height="12" rx="6" class="bar-fill"/>')
        parts.append(f'<text x="{width - 52}" y="{y + 11}" class="bar-value">{v:.3f}</text>')
    return f'<svg viewBox="0 0 {width} {h}" class="bars">{"".join(parts)}</svg>'


def _scatter_svg(pairs: list[list[float]], size: int = 320) -> str:
    """Predicted vs measured scatter with the y=x reference line."""
    if not pairs:
        return ""
    pad = 40
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    lo = math.floor(min(xs + ys)) - 0.5
    hi = math.ceil(max(xs + ys)) + 0.5
    span = max(1e-6, hi - lo)

    def X(v: float) -> float:
        return pad + (v - lo) / span * (size - pad - 12)

    def Y(v: float) -> float:
        return size - pad - (v - lo) / span * (size - pad - 12)

    parts = [f'<rect x="{pad}" y="12" width="{size - pad - 12}" height="{size - pad - 12}" class="plot-area"/>']
    for t in range(int(lo) + 1, int(hi)):
        parts.append(f'<line class="sgrid" x1="{pad}" y1="{Y(t):.1f}" x2="{size - 12}" y2="{Y(t):.1f}"/>')
        parts.append(f'<text class="tick" x="{pad - 6}" y="{Y(t) + 3:.1f}" text-anchor="end">{t}</text>')
        parts.append(f'<text class="tick" x="{X(t):.1f}" y="{size - pad + 14}" text-anchor="middle">{t}</text>')
    parts.append(f'<line class="ref" x1="{X(lo):.1f}" y1="{Y(lo):.1f}" x2="{X(hi):.1f}" y2="{Y(hi):.1f}"/>')
    for a, p in pairs:
        parts.append(f'<circle class="pt" cx="{X(a):.1f}" cy="{Y(p):.1f}" r="3"/>')
    parts.append(f'<text class="axis-label" x="{size / 2:.0f}" y="{size - 8}" text-anchor="middle">measured pIC50</text>')
    parts.append(
        f'<text class="axis-label" x="12" y="{size / 2:.0f}" text-anchor="middle" transform="rotate(-90 12 {size / 2:.0f})">predicted pIC50</text>'
    )
    return f'<svg viewBox="0 0 {size} {size}" class="scatter">{"".join(parts)}</svg>'


CSS = """
:root{color-scheme:light;--ink:#0f1b2e;--muted:#46566e;--line:#d3ddec;--accent:#0b8f81;--accent2:#2f5cd4;--soft:#f1f6fd;--row:#f7fafe;--track:#e4ecf8}
*{box-sizing:border-box}
html{background:#fff}
body{font-family:'Inter','Segoe UI','Microsoft YaHei',sans-serif;color:var(--ink);margin:0;background:#fff;font-size:13px;line-height:1.55;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{max-width:960px;margin:0 auto;padding:40px 44px 64px}
h1{font-size:24px;margin:0 0 4px;letter-spacing:-.02em;color:var(--ink)}
h2{font-size:15px;margin:32px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--line);letter-spacing:-.01em;color:var(--ink)}
h3{font-size:13px;margin:18px 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.sub{color:var(--muted);font-size:12px}
.badges{margin:10px 0 0}
.badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:11px;margin-right:6px;background:var(--soft);color:var(--accent2);border:1px solid var(--line)}
.badge.ok{color:#0a6b50;background:#e6f7ef;border-color:#b6e3d1}
.badge.warn{color:#7d5700;background:#fdf3e0;border-color:#efd7a6}
table{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
th{text-align:left;color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em;background:var(--soft);border-bottom:1.5px solid var(--line);padding:8px 8px}
td{padding:8px;border-bottom:1px solid var(--line);vertical-align:middle;background:#fff;color:var(--ink)}
tr:nth-child(even) td{background:var(--row)}
tr:last-child td{border-bottom:none}
.mono{font-family:'SFMono-Regular',Consolas,monospace;font-size:11px;color:var(--ink)}
.num{text-align:right;font-variant-numeric:tabular-nums}
.mol-cell svg{width:150px;height:100px;display:block}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}
.card{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:#fff}
.summary{border-left:4px solid var(--accent);background:var(--soft);border-radius:0 10px 10px 0;padding:14px 18px}
.radar{width:100%;max-width:280px}
.ring{fill:none;stroke:var(--line);stroke-width:1}
.spoke{stroke:var(--line);stroke-width:1}
.shape{fill:rgba(11,143,129,.20);stroke:var(--accent);stroke-width:2}
.axis{fill:var(--muted);font-size:10px}
.bars{width:100%;max-width:360px}
.bar-label{fill:var(--muted);font-size:10px}
.bar-value{fill:var(--ink);font-size:10px;text-anchor:end}
.bar-track{fill:var(--track)}
.bar-fill{fill:var(--accent)}
.kv{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed var(--line);font-size:12px}
.kv:last-child{border-bottom:none}
.kv span:first-child{color:var(--muted)}
.kv span:last-child{font-family:'SFMono-Regular',Consolas,monospace;color:var(--ink)}
footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:11px;display:flex;justify-content:space-between}
.toolbar{position:fixed;top:16px;right:16px;display:flex;gap:8px}
.toolbar button{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:8px;padding:8px 14px;cursor:pointer;font-size:12px}
.toolbar button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.mol-missing{color:var(--muted);font-size:11px}
.plot-area{fill:#fbfdff;stroke:var(--line)}
.sgrid{stroke:var(--track);stroke-width:1}
.ref{stroke:var(--accent2);stroke-width:1.5;stroke-dasharray:5 4}
.scatter .pt{fill:rgba(11,143,129,.55);stroke:var(--accent);stroke-width:.8}
.axis-label{fill:var(--muted);font-size:10px}
.tick{fill:var(--muted);font-size:9px}
.mini{color:var(--muted);font-size:11px;margin-top:2px}
@media print{.toolbar{display:none}.page{padding:0 8mm}tr:nth-child(even) td{background:transparent}}
"""


def render_report_html(report: dict[str, Any], task: dict[str, Any] | None = None) -> str:
    task = task or {}
    cands = report.get("top_candidates") or []
    rounds = report.get("rounds") or []
    evidence = report.get("evidence") or []
    usage = report.get("token_usage") or {}

    # ---- candidate rows with real structures
    # Pass/fail is shown for the endpoints this run was optimising, so the table
    # reflects the project's objectives.
    objectives = [str(o) for o in (report.get("objectives") or [])]
    want_bbb = "BBB" in objectives
    want_hep = "hepatotoxicity" in objectives
    want_sol = "solubility" in objectives

    rows = []
    for c in cands:
        cells = [
            f'<td class="num"><b>#{_esc(c.get("id"))}</b></td>',
            f'<td class="mol-cell">{_mol_svg(c.get("smiles", ""))}</td>',
            f'<td class="mono">{_esc(c.get("smiles"))}</td>',
            f'<td class="num">{_fmt(c.get("pIC50"), 2)}</td>',
        ]
        if want_bbb:
            cells.append(f'<td>{_yn(c.get("bbb"))}</td>')
        if want_hep:
            cells.append(f'<td>{_yn(c.get("hepatotoxic"), invert=True)}</td>')
        if want_sol:
            cells.append(f'<td class="num">{_fmt(c.get("solubility"), 2)}</td>')
        cells += [
            f'<td class="num">{_fmt(c.get("sa_score"), 2)}</td>',
            f'<td class="num">{_fmt(c.get("qed"), 3)}</td>',
            f'<td class="num">{_fmt(c.get("route_steps"), 0)}</td>',
            f'<td class="num"><b>{_fmt(c.get("mpo"), 3)}</b></td>',
        ]
        rows.append("<tr>" + "".join(cells) + "</tr>")

    cand_head = ["#", "结构", "SMILES", "pIC50"]
    if want_bbb:
        cand_head.append("BBB 渗透")
    if want_hep:
        cand_head.append("无肝毒")
    if want_sol:
        cand_head.append("溶解度 logS")
    cand_head += ["SA", "QED", "路线步数", "MPO"]
    cand_head_html = "".join(
        f'<th class="num">{h}</th>' if h in {"pIC50", "SA", "QED", "路线步数", "MPO", "溶解度 logS"} else f"<th>{h}</th>"
        for h in cand_head
    )

    OBJ_LABELS = {"BBB": "血脑屏障渗透", "hepatotoxicity": "无肝毒性", "solubility": "溶解度"}
    target_summary_html = (
        '<div class="card" style="margin-top:12px"><h3>靶点情报摘要</h3>'
        f'<div style="color:var(--ink)">{_esc(report.get("target_summary"))}</div></div>'
        if report.get("target_summary")
        else ""
    )
    obj_badge = (
        '<span class="badge ok">优化目标：{}</span>'.format(
            " / ".join(OBJ_LABELS.get(o, o) for o in objectives)
        )
        if objectives
        else ""
    )

    # ---- charts
    # These normalisations are mirrored by the client-side radar in
    # frontend/src/pages/Test.tsx. Keep the two in step: SA runs 1 (easy) to
    # 10 (hard), so synthesizability is 1 - sa/10.
    top = cands[0] if cands else {}
    radar_axes = [
        ("Activity", min(1.0, (top.get("pIC50") or 5) / 10)),
        ("BBB", 1.0 if top.get("bbb") else 0.0),
        ("Safety", 0.3 if top.get("hepatotoxic") else 1.0),
        ("Solubility", max(0.0, min(1.0, ((top.get("solubility") or -6) + 10) / 10))),
        ("Synthesizability", max(0.0, min(1.0, 1 - (top.get("sa_score") or 5) / 10))),
    ]
    mpo_items = [(f"#{c.get('id')}", float(c.get("mpo") or 0)) for c in cands]

    round_rows = "".join(
        f"<tr><td class='num'>R{_esc(r.get('round'))}</td><td>{_esc(_localize_summary(r.get('summary')))}"
        + (f"<div class='mini'>{_esc(r.get('narrative'))}</div>" if r.get("narrative") else "")
        + "</td>"
        f"<td>{_esc(r.get('action', ''))}"
        + ("<div class='mini'>" + _esc("；".join(r.get("directive_labels") or [])) + "</div>" if r.get("directive_labels") else "")
        + f"</td><td class='num'>{_esc(r.get('passed'))}</td>"
        f"<td>{_esc(_label(ROUND_DECISION_LABELS, r.get('decision')))}</td></tr>"
        for r in rounds
    )
    evidence_items = "".join(
        f"<li><span class='badge'>{_esc(_label(EVIDENCE_LABELS, e.get('type')))}</span> "
        f"<b>{_esc(_short_id(e.get('id')))}</b>"
        + (
            f" · {_esc(e.get('title'))}"
            if e.get("title") and e.get("title") not in (e.get("id"), _short_id(e.get("id")))
            else ""
        )
        + (f" · 分辨率 {_fmt_resolution(e.get('resolution'))}" if e.get("type") == "pdb" else "")
        + "</li>"
        for e in evidence
    ) or "<li>本次运行没有关联的文献证据（该数据集尚未建立 RAG 索引）</li>"

    generated = _esc(report.get("generated_at"))
    task_id = _esc(report.get("task_id") or task.get("task_id"))
    target = _esc(report.get("target"))
    decision = _esc(_localize_decision(report.get("decision")))
    hypothesis = _esc(report.get("hypothesis"))

    dataset = report.get("dataset") or {}
    model = report.get("activity_model") or {}
    admet_engine = _label(ENGINE_LABELS, report.get("admet_engine") or dataset.get("admet_engine"))
    ds_rows = "".join(
        f'<div class="kv"><span>{_esc(k)}</span><span>{_esc(v)}</span></div>'
        for k, v in [
            ("数据集", dataset.get("dataset_id") or "—"),
            ("来源", dataset.get("source")),
            ("SMILES 列", dataset.get("smiles_column")),
            ("活性列", dataset.get("activity_column")),
            ("有效分子数", dataset.get("n_valid")),
            ("含活性分子数", dataset.get("n_with_activity")),
            ("活性类型", _label(ACTIVITY_KIND_LABELS, dataset.get("activity_kind"))),
        ]
        if v not in (None, "")
    )

    preds = model.get("test_predictions") or []
    metrics_d = model.get("metrics", {})
    # Section 4 owns the held-out metrics; section 2 repeats them only when there
    # is no validation chart to show them with.
    model_rows_data = [
        ("活性模型", _label(MODEL_KIND_LABELS, model.get("kind"))),
        ("训练 / 测试", f"{model.get('n_train', 0)} / {model.get('n_test', 0)}"),
    ]
    if not preds:
        model_rows_data += [
            ("R²", metrics_d.get("r2")),
            ("MAE", metrics_d.get("mae")),
            ("Spearman", metrics_d.get("spearman")),
            ("AUROC(二分类)", metrics_d.get("auroc_binarised")),
        ]
    model_rows_data += [
        ("成药性引擎", admet_engine),
        ("模型文件", _rel_path(model.get("model_path"))),
    ]
    model_rows = "".join(
        f'<div class="kv"><span>{_esc(k)}</span><span>{_esc(v)}</span></div>'
        for k, v in model_rows_data
        if v not in (None, "")
    )

    if preds:
        validation_html = (
            "<h2>4. 模型验证</h2><div class=\"grid\">"
            f'<div class="card"><h3>预测 vs 实测（留出集 {len(preds)} 点）</h3>{_scatter_svg(preds)}</div>'
            '<div class="card"><h3>留出集指标</h3>'
            f'<div class="kv"><span>R²</span><span>{_esc(metrics_d.get("r2"))}</span></div>'
            f'<div class="kv"><span>MAE</span><span>{_esc(metrics_d.get("mae"))}</span></div>'
            f'<div class="kv"><span>Spearman</span><span>{_esc(metrics_d.get("spearman"))}</span></div>'
            f'<div class="kv"><span>训练 / 测试</span><span>{_esc(model.get("n_train"))} / {_esc(model.get("n_test"))}</span></div>'
            '<div class="kv"><span>划分</span><span>scaffold</span></div>'
            "</div></div>"
        )
    else:
        validation_html = ""

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="color-scheme" content="light"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>DiscoveryX Report · {task_id}</title><style>{CSS}</style></head>
<body>
<div class="toolbar">
  <button class="primary" onclick="window.print()">打印 / 另存为 PDF</button>
</div>
<div class="page">
  <h1>DiscoveryX · DMTA 研发报告</h1>
  <div class="sub">{target} · 运行 {task_id} · 生成于 {generated}</div>
  <div class="badges">
    <span class="badge ok">真实数据源：ChEMBL / MoleculeNet / PDB / PMC</span>
    <span class="badge">LLM：DeepSeek</span>
    <span class="badge">可审计</span>
    {obj_badge}
  </div>

  <h2>1. 摘要与决策</h2>
  <div class="summary">
    <div><b>科学假设：</b>{hypothesis}</div>
    <div style="margin-top:8px"><b>决策：</b>{decision}</div>
  </div>
  {target_summary_html}

  <h2>2. 数据与模型</h2>
  <div class="grid">
    <div class="card"><h3>数据集</h3>{ds_rows or '<div class="kv"><span>—</span><span>—</span></div>'}</div>
    <div class="card"><h3>模型</h3>{model_rows or '<div class="kv"><span>—</span><span>—</span></div>'}</div>
  </div>

  <h2>3. 迭代过程（反馈驱动）</h2>
  <table><thead><tr><th>轮次</th><th>摘要</th><th>改进动作</th><th class="num">达标数</th><th>结论</th></tr></thead>
  <tbody>{round_rows or '<tr><td colspan="5">无</td></tr>'}</tbody></table>

  {validation_html}

  <h2>5. 候选化合物（含结构式）</h2>
  <table><thead><tr>{cand_head_html}</tr></thead>
  <tbody>{''.join(rows) or f'<tr><td colspan="{len(cand_head)}">无</td></tr>'}</tbody></table>

  <h2>6. 成药性与多参数评分</h2>
  <div class="grid">
    <div class="card"><h3>成药性雷达（Top 1）</h3>{_radar_svg(radar_axes)}</div>
    <div class="card"><h3>多参数评分 MPO</h3>{_bars_svg(mpo_items)}</div>
  </div>

  <h2>7. 证据与引用</h2>
  <ul>{evidence_items}</ul>

  <h2>8. 运行清单</h2>
  <div class="grid">
    <div class="card"><h3>运行</h3>
      <div class="kv"><span>任务</span><span>{task_id}</span></div>
      <div class="kv"><span>trace_id</span><span>{_esc(task.get('trace_id'))}</span></div>
      <div class="kv"><span>状态</span><span>{_esc(_label(STATUS_LABELS, task.get('status')))}</span></div>
      <div class="kv"><span>迭代轮次</span><span>已完成 {_esc(task.get('round'))} / 共 {_esc(task.get('rounds'))} 轮</span></div>
      <div class="kv"><span>LLM 调用 / 成本</span><span>{_esc(usage.get('calls'))} 次 · ${_esc(usage.get('cost_usd'))}</span></div>
      <div class="kv"><span>tokens (输入 / 输出)</span><span>{_esc(usage.get('prompt_tokens'))} / {_esc(usage.get('completion_tokens'))}</span></div>
    </div>
    <div class="card"><h3>模型</h3>
      <div class="kv"><span>LLM</span><span>DeepSeek · deepseek-chat</span></div>
      <div class="kv"><span>活性模型</span><span>{_esc(_label(MODEL_KIND_LABELS, model.get('kind')))}</span></div>
      <div class="kv"><span>成药性引擎</span><span>{_esc(admet_engine)}</span></div>
    </div>
  </div>

  <footer>
    <span>DiscoveryX · 由平台自动生成</span>
    <span>证据与决策可通过审计日志（JSON Lines）追溯</span>
  </footer>
</div>
</body></html>"""


def _fmt(v: Any, nd: int) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return _esc(v)


def _yn(v: Any, invert: bool = False) -> str:
    if v is None:
        return "—"
    good = (not v) if invert else bool(v)
    return '<span class="badge ok">是</span>' if good else '<span class="badge warn">否</span>'
