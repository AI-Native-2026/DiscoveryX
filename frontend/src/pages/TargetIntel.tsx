import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Typography, Tag, Button, Empty, Space } from "antd";
import { BookOutlined } from "@ant-design/icons";
import { api, ApiError } from "../api/client";
import { useProjectTask } from "../state/taskContext";
import { useProject } from "../state/projectContext";
import { useI18n } from "../i18n";
import { MolGlyph } from "../components/charts";

const { Title, Paragraph, Text } = Typography;

export default function TargetIntel() {
  const { task } = useProjectTask();
  const { activeProject } = useProject();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [query, setQuery] = useState(activeProject?.target ? `${activeProject.target} inhibitor` : "");
  const [answer, setAnswer] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const evidence = task?.result?.evidence ?? [];
  const pdb = evidence.find((e) => e.type === "pdb");
  const papers = evidence.filter((e) => e.type === "pmc");

  const ask = async () => {
    setLoading(true);
    try {
      const r = await api.ragQuery(query, 4);
      setAnswer(r.answer);
    } catch (e) {
      setAnswer(e instanceof ApiError && e.status === 403 ? `${t("common.notAllowed")}: ${e.message}` : (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("target.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("target.title", { target: activeProject?.target ?? t("common.none") })}</Title>
      <Paragraph className="dx-lede">{t("target.lede")}</Paragraph>

      <div className="section">
        <div className="field">
          <input value={query} onChange={(e) => setQuery(e.target.value)} />
          <Button type="primary" loading={loading} onClick={ask}>
            {t("target.search")}
          </Button>
        </div>
      </div>

      {task?.result?.target_summary && (
        <div className="section panel">
          <div className="section-head">
            <div className="section-title">{t("target.intel")}</div>
            <div className="section-note">{t("target.intelNote")}</div>
          </div>
          <Paragraph style={{ color: "#c9d4e6", whiteSpace: "pre-wrap", marginBottom: 0 }}>
            {task.result.target_summary}
          </Paragraph>
        </div>
      )}

      <div className="section panel-grid">
        <div className="panel">
          <div className="section-head">
            <div className="section-title">{t("target.summary")}</div>
            <div className="section-note">{t("target.summaryNote")}</div>
          </div>
          {answer ? (
            <Paragraph style={{ color: "#c9d4e6", whiteSpace: "pre-wrap" }}>{answer}</Paragraph>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("target.summaryEmpty")} />
          )}
        </div>
        <div className="panel">
          <div className="section-head">
            <div className="section-title">{t("target.sources")}</div>
            <div className="section-note">{papers.length}</div>
          </div>
          {papers.length === 0 && <Text type="secondary">{t("target.sourcesEmpty")}</Text>}
          {papers.map((p, i) => (
            <div className="src-item" key={i}>
              <span className="src-idx">{i + 1}</span>
              <div className="src-main">
                <div className="src-title">{p.title || p.id}</div>
                <div className="src-src">{p.id}</div>
              </div>
              {p.score != null && <span className="src-score">{p.score.toFixed(2)}</span>}
            </div>
          ))}
        </div>
      </div>

      <div className="section panel-grid">
        <div className="panel">
          <div className="panel-title">{t("target.structure")}</div>
          <div className="struct-card">
            <div className="struct-visual">
              <MolGlyph seed={99} size={96} />
            </div>
            <div className="struct-meta">
              <div className="struct-pdb">{pdb?.id ?? activeProject?.pdb_id ?? "4WY1"}</div>
              <div className="src-detail">{pdb?.title ?? "—"}</div>
              {pdb?.resolution && <Tag color="blue">{String(pdb.resolution)} Å</Tag>}
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-title">{t("target.druggability")}</div>
          <div className="manifest">
            <div className="mf-row">
              <span className="mf-key">{t("target.targetType")}</span>
              <span className="badge pass">{activeProject?.target ?? "—"}</span>
            </div>
            <div className="mf-row">
              <span className="mf-key">{t("target.structureSrc")}</span>
              <span className="mf-val">RCSB PDB</span>
            </div>
            <div className="mf-row">
              <span className="mf-key">{t("target.litSrc")}</span>
              <span className="mf-val">Europe PMC</span>
            </div>
          </div>
          <Space style={{ marginTop: 12 }}>
            <Button icon={<BookOutlined />} onClick={() => navigate("/rag")}>
              {t("target.openRag")}
            </Button>
          </Space>
        </div>
      </div>
    </section>
  );
}
