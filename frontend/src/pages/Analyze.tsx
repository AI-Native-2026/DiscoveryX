import { Typography, Empty, Tag } from "antd";
import { CheckOutlined } from "@ant-design/icons";
import { useProjectTask } from "../state/taskContext";
import { useI18n } from "../i18n";
import { decisionLabel, roundSummaryLabel } from "../lib/labels";

const { Title, Paragraph, Text } = Typography;

export default function Analyze() {
  const { task } = useProjectTask();
  const { t, lang } = useI18n();
  const report = task?.result;
  const cands = [...(report?.top_candidates ?? [])].sort((a, b) => (b.mpo ?? 0) - (a.mpo ?? 0));
  const rounds = report?.rounds ?? [];
  const risky = cands.filter((c) => c.hepatotoxic).map((c) => `#${c.id}`);

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("analyze.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("analyze.title")}</Title>
      <Paragraph className="dx-lede">{t("analyze.lede")}</Paragraph>

      {!report ? (
        <div className="section panel">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("analyze.empty")} />
        </div>
      ) : (
        <>
          <div className="section decision">
            <div className="dc-icon">
              <CheckOutlined />
            </div>
            <div>
              <div className="dc-label">{t("analyze.decision")}</div>
              <div className="dc-body">{decisionLabel(report.decision, lang)}</div>
              <div className="dc-meta">
                {t("analyze.meta", { passed: rounds.reduce((a, r) => a + r.passed, 0), rounds: rounds.length })}
              </div>
            </div>
          </div>

          <div className="section panel-grid">
            <div className="panel">
              <div className="panel-title">{t("analyze.mpo")}</div>
              <div className="mpo">
                {cands.map((c) => (
                  <div className="mpo-row" key={c.id}>
                    <span className="mpo-id">#{c.id}</span>
                    <div className="mpo-bar">
                      <span style={{ width: `${(c.mpo ?? 0) * 100}%` }} />
                    </div>
                    <span className="mpo-val">{c.mpo?.toFixed(3) ?? t("common.none")}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="panel">
              <div className="panel-title">{t("analyze.history")}</div>
              <div className="evidence">
                {rounds.map((r) => (
                  <div className="ev-item" key={r.round}>
                    <span className="bullet">•</span>
                    <span>
                      <Tag color={r.decision === "met" ? "success" : "processing"}>R{r.round}</Tag>
                      {roundSummaryLabel(r.summary, lang)}
                      {r.action ? <div className="src-detail" style={{ marginTop: 2 }}>{r.action}</div> : null}
                    </span>
                  </div>
                ))}
                {rounds.length === 0 && <Text type="secondary">{t("analyze.empty")}</Text>}
              </div>
            </div>
          </div>

          <div className="section panel">
            <div className="panel-title">{t("analyze.next")}</div>
            <Text style={{ color: "#c9d4e6" }}>
              {t("analyze.nextBody", {
                top: cands.slice(0, 3).map((c) => `#${c.id}`).join(", "),
                risky: risky.length ? risky.join(", ") : t("analyze.noRisky"),
              })}
            </Text>
          </div>
        </>
      )}
    </section>
  );
}
