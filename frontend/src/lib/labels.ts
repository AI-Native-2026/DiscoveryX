import type { Lang } from "../i18n";

/**
 * The DMTA workflow emits its decision and round summary in English so the API
 * stays language-neutral. The clients render them in the active UI language —
 * keep this mapping in step with `backend/app/core/report.py`.
 */
const DECISION_ZH: Record<string, string> = {
  "Objectives met - candidates are ready for synthesis and assay.": "目标已达成，候选化合物可进入合成与活性验证。",
  "Objectives not yet met - refine the series in the next round.": "目标尚未全部达成，下一轮继续优化该系列。",
};

export function decisionLabel(text: string | null | undefined, lang: Lang): string {
  if (!text) return "";
  return lang === "zh" ? (DECISION_ZH[text] ?? text) : text;
}

export function roundSummaryLabel(text: string | null | undefined, lang: Lang): string {
  const s = text ?? "";
  const m = /^round (\d+): (\d+) candidates, (\d+) passed all objectives$/.exec(s);
  if (m && lang === "zh") {
    return `第 ${m[1]} 轮：${m[2]} 个候选，${m[3]} 个通过全部目标`;
  }
  return s;
}
