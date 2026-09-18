import { Typography, Empty, Space, Tag } from "antd";
import { useProjectTask } from "../state/taskContext";
import { useI18n } from "../i18n";
import { Meter, RadarChart } from "../components/charts";

const { Title, Paragraph, Text } = Typography;

export default function Test() {
  const { task } = useProjectTask();
  const { t } = useI18n();
  const cands = task?.result?.top_candidates ?? [];
  const top = cands[0];
  const second = cands[1];
  const engine = (task?.result as { admet_engine?: string })?.admet_engine ?? "—";

  const norm = (v: number | null | undefined, invert = false) => {
    if (v == null) return 0;
    if (invert) return Math.max(0, Math.min(1, 1 - v));
    return Math.max(0, Math.min(1, v));
  };

  // Axis normalisation mirrors the server-side report radar
  // (app/core/report.py -> _radar_svg / radar_axes). SA scores run 1 (easy) to
  // 10 (hard), so the synthesizability axis is 1 - sa/10.
  const axes = top
    ? [
        { label: t("th.pic50"), a: norm((top.pIC50 ?? 5) / 10), b: second ? norm((second.pIC50 ?? 5) / 10) : undefined },
        { label: t("th.bbb"), a: top.bbb ? 1 : 0, b: second ? (second.bbb ? 1 : 0) : undefined },
        { label: t("th.hepato"), a: top.hepatotoxic ? 0.3 : 1, b: second ? (second.hepatotoxic ? 0.3 : 1) : undefined },
        { label: t("obj.solubility"), a: norm(((top.solubility ?? -6) + 10) / 10), b: second ? norm(((second.solubility ?? -6) + 10) / 10) : undefined },
        {
          label: t("th.sa"),
          a: norm((top.sa_score ?? 5) / 10, true),
          b: second ? norm((second.sa_score ?? 5) / 10, true) : undefined,
        },
      ]
    : [];

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("test.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("test.title")}</Title>
      <Paragraph className="dx-lede">{t("test.lede")}</Paragraph>

      {!top ? (
        <div className="section panel">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("design.empty")} />
        </div>
      ) : (
        <div className="section panel-grid">
          <div className="panel">
            <div className="panel-title">{t("test.radar")}</div>
            <RadarChart axes={axes} />
            <div className="legend">
              <span className="lg">
                <span className="swatch dot" style={{ background: "#3dd6c4" }} />#{top.id}
              </span>
              {second && (
                <span className="lg">
                  <span className="swatch dot" style={{ background: "#7f8da6" }} />#{second.id}
                </span>
              )}
            </div>
          </div>
          <div className="panel">
            <div className="panel-title">{t("test.endpoints", { id: top.id })}</div>
            <div className="endpoints">
              <Meter label={t("test.activity")} value={(top.pIC50 ?? 0) / 10} tone="pass" />
              <Meter label={t("test.bbb")} value={top.bbb ? 1 : 0} tone={top.bbb ? "pass" : "fail"} />
              <Meter label={t("test.hepato")} value={top.hepatotoxic ? 0.8 : 0.2} tone={top.hepatotoxic ? "fail" : "pass"} />
              <Meter label={t("test.herg")} value={top.herg ?? 0} tone={(top.herg ?? 0) > 0.5 ? "warn" : "pass"} />
              <Meter
                label={t("test.solubility")}
                value={Math.max(0, Math.min(1, ((top.solubility ?? -6) + 10) / 10))}
                tone="accent"
              />
            </div>
            <Space style={{ marginTop: 12 }}>
              <Tag color="cyan">{t("test.engine", { engine })}</Tag>
            </Space>
            <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8 }}>
              {t("test.note")}
            </Paragraph>
            <Text type="secondary" style={{ fontSize: 12 }}>
              logS：{top.solubility ?? t("common.none")} · QED：{top.qed?.toFixed(3) ?? t("common.none")}
            </Text>
          </div>
        </div>
      )}
    </section>
  );
}
