import { Typography, Tag, Empty } from "antd";
import { useProjectTask } from "../state/taskContext";
import { useI18n } from "../i18n";
import { RouteDiagram } from "../components/charts";

const { Title, Paragraph, Text } = Typography;

export default function Make() {
  const { task } = useProjectTask();
  const { t } = useI18n();
  const cands = task?.result?.top_candidates ?? [];

  const steps = (n: number | null | undefined) =>
    (n ?? 3) <= 2
      ? [t("make.blockA"), t("make.intermediate"), t("make.product")]
      : [t("make.blockA"), t("make.blockB"), t("make.intermediate"), t("make.product")];

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("make.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("make.title")}</Title>
      <Paragraph className="dx-lede">{t("make.lede")}</Paragraph>

      {cands.length === 0 ? (
        <div className="section panel">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("design.empty")} />
        </div>
      ) : (
        <>
          <div className="section panel">
            <div className="section-head">
              <div className="section-title">{t("make.route", { id: cands[0].id })}</div>
              <div className="section-note">{cands[0].route_available ? t("make.routeOk") : t("make.routeUnknown")}</div>
            </div>
            <RouteDiagram steps={steps(cands[0].route_steps)} />
            <div className="manifest" style={{ marginTop: 16 }}>
              <div className="mf-row">
                <span className="mf-key">{t("make.steps")}</span>
                <span className="mf-val">{cands[0].route_steps ?? t("common.none")}</span>
              </div>
              <div className="mf-row">
                <span className="mf-key">{t("make.avail")}</span>
                <span className={`badge ${cands[0].route_available ? "pass" : "fail"}`}>
                  {cands[0].route_available ? t("make.availYes") : t("make.availNo")}
                </span>
              </div>
              <div className="mf-row">
                <span className="mf-key">{t("make.engine")}</span>
                <span className="mf-val">{t("make.engineVal")}</span>
              </div>
            </div>
          </div>

          <div className="section panel" style={{ overflowX: "auto" }}>
            <div className="panel-title">{t("make.summary")}</div>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("th.id")}</th>
                  <th>{t("th.smiles")}</th>
                  <th>{t("make.steps")}</th>
                  <th>{t("make.avail")}</th>
                  <th>{t("th.sa")}</th>
                </tr>
              </thead>
              <tbody>
                {cands.map((c) => (
                  <tr key={c.id}>
                    <td className="strong num">{c.id}</td>
                    <td className="mono" style={{ maxWidth: 340, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {c.smiles}
                    </td>
                    <td className="num">{c.route_steps ?? t("common.none")}</td>
                    <td>
                      <Tag color={c.route_available ? "success" : "error"}>
                        {c.route_available ? t("make.availYes") : t("make.availNo")}
                      </Tag>
                    </td>
                    <td className="num">{c.sa_score?.toFixed(2) ?? t("common.none")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("make.note")}
            </Text>
          </div>
        </>
      )}
    </section>
  );
}
