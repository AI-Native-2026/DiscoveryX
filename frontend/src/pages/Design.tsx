import { Typography, Empty } from "antd";
import { CheckCircleTwoTone, CloseCircleTwoTone } from "@ant-design/icons";
import { useProjectTask } from "../state/taskContext";
import { useProject } from "../state/projectContext";
import { useI18n } from "../i18n";
import { MolGlyph } from "../components/charts";

const { Title, Paragraph, Text } = Typography;

export default function Design() {
  const { task } = useProjectTask();
  const { activeProject } = useProject();
  const { t } = useI18n();
  const cands = task?.result?.top_candidates ?? [];

  // Only surface the endpoints this run was optimising. A non-CNS programme has
  // no business showing BBB as a failure.
  const objectives = task?.objectives ?? task?.result?.objectives ?? activeProject?.objectives ?? [];
  const wantBbb = objectives.includes("BBB");
  const wantHep = objectives.includes("hepatotoxicity");
  const wantSol = objectives.includes("solubility");

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("design.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("design.title")}</Title>
      <Paragraph className="dx-lede">{t("design.lede")}</Paragraph>

      {cands.length === 0 ? (
        <div className="section panel">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("design.empty")} />
        </div>
      ) : (
        <>
          <div className="section stat-row">
            <div className="stat">
              <div className="stat-label">{t("design.nCandidates")}</div>
              <div className="stat-value">{cands.length}</div>
            </div>
            {wantBbb && (
              <div className="stat">
                <div className="stat-label">{t("design.bbbPass")}</div>
                <div className="stat-value">{cands.filter((c) => c.bbb).length}</div>
              </div>
            )}
            {wantHep && (
              <div className="stat">
                <div className="stat-label">{t("design.hepatoRisk")}</div>
                <div className="stat-value">{cands.filter((c) => c.hepatotoxic).length}</div>
              </div>
            )}
            <div className="stat">
              <div className="stat-label">SA ≤ 6</div>
              <div className="stat-value">{cands.filter((c) => (c.sa_score ?? 10) <= 6).length}</div>
            </div>
          </div>

          <div className="section panel" style={{ overflowX: "auto" }}>
            <div className="panel-title">{t("design.table")}</div>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("th.id")}</th>
                  <th>{t("th.structure")}</th>
                  <th>{t("th.smiles")}</th>
                  <th>{t("th.pic50")}</th>
                  {wantBbb && <th>{t("th.bbb")}</th>}
                  {wantHep && <th>{t("th.hepato")}</th>}
                  {wantSol && <th>{t("obj.solubility")}</th>}
                  <th>{t("th.sa")}</th>
                  <th>{t("th.qed")}</th>
                  <th>{t("th.mpo")}</th>
                </tr>
              </thead>
              <tbody>
                {cands.map((c) => (
                  <tr key={c.id}>
                    <td className="strong num">{c.id}</td>
                    <td>
                      <MolGlyph seed={c.id} size={40} />
                    </td>
                    <td className="mono" style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {c.smiles}
                    </td>
                    <td className="strong num">{c.pIC50?.toFixed(2) ?? t("common.none")}</td>
                    {wantBbb && (
                      <td>
                        {c.bbb ? (
                          <CheckCircleTwoTone twoToneColor="#35d39a" />
                        ) : (
                          <CloseCircleTwoTone twoToneColor="#f2707a" />
                        )}
                      </td>
                    )}
                    {wantHep && (
                      <td>
                        {c.hepatotoxic ? (
                          <CloseCircleTwoTone twoToneColor="#f2707a" />
                        ) : (
                          <CheckCircleTwoTone twoToneColor="#35d39a" />
                        )}
                      </td>
                    )}
                    {wantSol && <td className="num">{c.solubility?.toFixed(2) ?? t("common.none")}</td>}
                    <td className="num">{c.sa_score?.toFixed(2) ?? t("common.none")}</td>
                    <td className="num">{c.qed?.toFixed(3) ?? t("common.none")}</td>
                    <td>
                      <span className="badge pass">{c.mpo?.toFixed(3) ?? t("common.none")}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {cands[0]?.rationale && (
            <div className="section panel">
              <div className="panel-title">{t("design.rationale")}</div>
              <Text style={{ color: "#c9d4e6" }}>{cands[0].rationale}</Text>
            </div>
          )}
        </>
      )}
    </section>
  );
}
