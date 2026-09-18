import { useState } from "react";
import { Typography, Button, Empty, message, Space } from "antd";
import { FilePdfOutlined, FileTextOutlined } from "@ant-design/icons";
import { useProjectTask } from "../state/taskContext";
import { useProject } from "../state/projectContext";
import { useI18n } from "../i18n";
import { decisionLabel, roundSummaryLabel } from "../lib/labels";
import { api } from "../api/client";

const { Title, Paragraph, Text } = Typography;

export default function Report() {
  const { task } = useProjectTask();
  const { activeProject } = useProject();
  const { t, lang } = useI18n();
  const report = task?.result;
  const [busy, setBusy] = useState(false);

  const ds = (report?.dataset ?? {}) as Record<string, unknown>;
  const model = (report?.activity_model ?? {}) as Record<string, unknown>;
  const metrics = (model.metrics as Record<string, number>) ?? {};

  const openHtml = async () => {
    if (!task) return;
    setBusy(true);
    try {
      const html = await api.taskReportHtml(task.task_id);
      window.open(URL.createObjectURL(new Blob([html], { type: "text/html" })), "_blank");
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const downloadJson = () => {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${task?.task_id ?? "report"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("report.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("report.title")}</Title>
      <Paragraph className="dx-lede">{t("report.lede")}</Paragraph>

      {!report ? (
        <div className="section panel">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("report.empty")} />
        </div>
      ) : (
        <>
          <div className="section btn-row">
            <Space>
              <Button type="primary" icon={<FilePdfOutlined />} loading={busy} onClick={openHtml}>
                {t("report.generate")}
              </Button>
              <Button icon={<FileTextOutlined />} onClick={downloadJson}>
                {t("report.exportJson")}
              </Button>
            </Space>
          </div>

          <div className="section">
            <div className="panel">
              <div className="panel-title">{t("report.contains")}</div>
              <div className="evidence">
                {["report.c1", "report.c2", "report.c3", "report.c4"].map((k) => (
                  <div className="ev-item" key={k}>
                    <span className="bullet">•</span>
                    <span>{t(k)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="section panel-grid">
            <div className="report-frame">
              <div className="rf-title">{t("report.frameTitle", { name: activeProject?.name ?? "Project" })}</div>
              <div className="rf-sub">
                {task?.task_id} · {report.generated_at}
              </div>
              <div className="rf-hr" />
              <div className="rf-h">{t("report.hypothesis")}</div>
              <ul>
                <li>{report.hypothesis}</li>
              </ul>
              {report.target_summary && (
                <>
                  <div className="rf-hr" />
                  <div className="rf-h">{t("target.intel")}</div>
                  <ul>
                    <li>{report.target_summary}</li>
                  </ul>
                </>
              )}
              <div className="rf-hr" />
              <div className="rf-h">{t("report.decision")}</div>
              <ul>
                <li>{decisionLabel(report.decision, lang)}</li>
              </ul>
              <div className="rf-hr" />
              <div className="rf-h">{t("report.roundSummary")}</div>
              <ul>
                {report.rounds.map((r) => (
                  <li key={r.round}>
                    R{r.round}：{roundSummaryLabel(r.summary, lang)}
                    {r.action ? ` — ${r.action}` : ""}
                    {r.narrative ? <div className="src-detail" style={{ marginTop: 2 }}>{r.narrative}</div> : null}
                  </li>
                ))}
              </ul>
              <div className="rf-hr" />
              <div className="rf-h">{t("report.citations")}</div>
              <ul>
                {report.evidence.map((e, i) => (
                  <li key={i}>
                    [{e.type}] {e.id} {e.title ? `· ${e.title}` : ""}
                  </li>
                ))}
                {report.evidence.length === 0 && <li>{t("report.none")}</li>}
              </ul>
            </div>

            <div>
              <div className="panel" style={{ marginBottom: 16 }}>
                <div className="panel-title">{t("report.datasetModel")}</div>
                <div className="manifest">
                  <div className="mf-row">
                    <span className="mf-key">{t("report.dataset")}</span>
                    <span className="mf-val">{String(ds.dataset_id ?? "—")}</span>
                  </div>
                  <div className="mf-row">
                    <span className="mf-key">{t("report.sourceFile")}</span>
                    <span className="mf-val">{String(ds.source ?? "—")}</span>
                  </div>
                  <div className="mf-row">
                    <span className="mf-key">{t("report.validWithActivity")}</span>
                    <span className="mf-val">
                      {String(ds.n_valid ?? "—")} / {String(ds.n_with_activity ?? "—")}
                    </span>
                  </div>
                  <div className="mf-row">
                    <span className="mf-key">{t("report.activityColumn")}</span>
                    <span className="mf-val">{String(ds.activity_column ?? "—")}</span>
                  </div>
                  <div className="mf-row">
                    <span className="mf-key">{t("report.activityModel")}</span>
                    <span className="mf-val">
                      {String(model.kind ?? "—")}
                      {metrics.r2 != null ? ` · R²=${metrics.r2} · MAE=${metrics.mae}` : ""}
                    </span>
                  </div>
                  <div className="mf-row">
                    <span className="mf-key">{t("report.admetEngine")}</span>
                    <span className="mf-val">{report.admet_engine ?? "—"}</span>
                  </div>
                </div>
              </div>

              <div className="panel" style={{ marginBottom: 16 }}>
                <div className="panel-title">{t("report.manifest")}</div>
                <div className="manifest">
                  <div className="mf-row">
                    <span className="mf-key">{t("report.task")}</span>
                    <span className="mf-val">{task?.task_id}</span>
                  </div>
                  <div className="mf-row">
                    <span className="mf-key">trace_id</span>
                    <span className="mf-val">{task?.trace_id ?? "—"}</span>
                  </div>
                  <div className="mf-row">
                    <span className="mf-key">{t("report.rounds")}</span>
                    <span className="mf-val">
                      {task?.round}/{task?.rounds}
                    </span>
                  </div>
                  <div className="mf-row">
                    <span className="mf-key">{t("report.status")}</span>
                    <span className="mf-val">{task ? t(`status.${task.status}`) : "—"}</span>
                  </div>
                  <div className="mf-row">
                    <span className="mf-key">{t("detail.retries")}</span>
                    <span className="mf-val">{task?.attempts ?? 0}</span>
                  </div>
                </div>
                <div className="panel-note">{t("report.audit")}</div>
              </div>
            </div>
          </div>

          <Text type="secondary" style={{ fontSize: 12 }}>
            {t("report.footer", { api: api.base })}
          </Text>
        </>
      )}
    </section>
  );
}
