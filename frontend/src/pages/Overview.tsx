import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Typography, Tag, Button, Alert, message } from "antd";
import { ArrowRightOutlined, AimOutlined, CloseOutlined } from "@ant-design/icons";
import { api, ApiError } from "../api/client";
import { useProjectTask } from "../state/taskContext";
import { useProject } from "../state/projectContext";
import { useI18n } from "../i18n";
import type { DatasetInfo, TaskState } from "../api/types";

const { Title, Paragraph, Text } = Typography;

const DEMO_DISMISSED_KEY = "discoveryx.demoCardDismissed";

export default function Overview() {
  const { task } = useProjectTask();
  const { activeProject } = useProject();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskState[]>([]);
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [demoDismissed, setDemoDismissed] = useState(() => localStorage.getItem(DEMO_DISMISSED_KEY) === "1");

  useEffect(() => {
    if (!activeProject) {
      setTasks([]);
      return;
    }
    api.listTasks(activeProject.id).then(setTasks).catch(() => setTasks([]));
    api.listDatasets().then((r) => setDatasets(r.items)).catch(() => setDatasets([]));
  }, [activeProject]);

  // LLM usage is consolidated here at project level; the per-run breakdown lives
  // on the task detail page.
  const usage = tasks.reduce(
    (acc, x) => ({
      calls: acc.calls + (x.token_usage?.calls ?? 0),
      prompt: acc.prompt + (x.token_usage?.prompt_tokens ?? 0),
      completion: acc.completion + (x.token_usage?.completion_tokens ?? 0),
      cost: acc.cost + (x.token_usage?.cost_usd ?? 0),
    }),
    { calls: 0, prompt: 0, completion: 0, cost: 0 },
  );

  const runDemo = async () => {    if (!activeProject) {
      message.warning(t("ov.needProject"));
      return;
    }
    setDemoBusy(true);
    setDemoError(null);
    try {
      const res = await api.createTask({
        hypothesis: activeProject.description || `Find a ${activeProject.target} inhibitor: brain-penetrant, non-hepatotoxic.`,
        target: activeProject.target,
        pdb_id: activeProject.pdb_id,
        objectives: activeProject.objectives,
        rounds: 3,
        project: activeProject.id,
        dataset_id: null,
        activity_model: "qsar",
      });
      message.success(t("tasks.submitted", { id: res.task_id }));
      navigate(`/tasks/${res.task_id}`);
    } catch (e) {
      setDemoError(e instanceof ApiError && e.status === 403 ? t("tasks.guardrail", { msg: e.message }) : (e as Error).message);
    } finally {
      setDemoBusy(false);
    }
  };

  const dismissDemo = () => {
    setDemoDismissed(true);
    localStorage.setItem(DEMO_DISMISSED_KEY, "1");
  };

  const report = task?.result ?? null;
  const passed = report?.rounds?.reduce((a, r) => a + r.passed, 0) ?? 0;

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("ov.eyebrow")}</Paragraph>
      <Title className="dx-h1">{activeProject?.name ?? t("nav.overview")}</Title>
      <Paragraph className="dx-lede">{activeProject?.description || t("ov.lede")}</Paragraph>

      {demoError && <Alert style={{ marginTop: 16 }} type="error" showIcon message={demoError} />}

      {!demoDismissed && activeProject && (
        <div className="section">
          <div className="dx-demo">
            <button className="dx-demo-close" onClick={dismissDemo} aria-label={t("common.close")}>
              <CloseOutlined />
            </button>
            <div style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}>
              <div className="dx-demo-icon">
                <AimOutlined />
              </div>
              <div style={{ flex: 1, minWidth: 260 }}>
                <div className="dx-demo-title">{t("ov.demoTitle", { name: activeProject.name })}</div>
                <div className="dx-cap-desc">{t("ov.demoDesc")}</div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <Button type="primary" size="large" loading={demoBusy} onClick={runDemo}>
                  {t("ov.runDemo")} <ArrowRightOutlined />
                </Button>
                <Button size="large" onClick={() => navigate("/catalog")}>
                  {t("ov.viewCatalog")}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="section panel">
        <div className="section-head">
          <div className="section-title">{t("ov.objective")}</div>
          <div className="section-note">
            {task ? `${task.task_id} · ${t("detail.round", { r: task.round, n: task.rounds })}` : t("ov.noRun")}
          </div>
        </div>
        <div className="objective">
          {report?.hypothesis || activeProject?.description || "—"}
        </div>
        <div className="manifest" style={{ marginTop: 14 }}>
          <div className="mf-row">
            <span className="mf-key">{t("project.target")}</span>
            <span className="mf-val">{activeProject?.target ?? "—"}</span>
          </div>
          <div className="mf-row">
            <span className="mf-key">{t("project.pdb")}</span>
            <span className="mf-val">{activeProject?.pdb_id ?? "—"}</span>
          </div>
          <div className="mf-row">
            <span className="mf-key">{t("project.objectives")}</span>
            <span className="mf-val">{(activeProject?.objectives ?? []).map((o) => t(`obj.${o}`)).join(" · ") || "—"}</span>
          </div>
        </div>
      </div>

      <div className="section metric-row">
        <div className="metric-card">
          <div className="metric-label">{t("ov.kpi.rounds")}</div>
          <div className="metric-value tone-accent">{task ? `${task.round}/${task.rounds}` : "—"}</div>
          <div className="metric-sub">{t("ov.kpi.dmtaSub")}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">{t("ov.kpi.passed")}</div>
          <div className="metric-value tone-good">{passed}</div>
          <div className="metric-sub">{t("ov.kpi.passedSub")}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">{t("ov.kpi.top")}</div>
          <div className="metric-value">{report?.top_candidates?.length ?? 0}</div>
          <div className="metric-sub">{t("ov.kpi.topSub")}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">{t("ov.kpi.tokens")}</div>
          <div className="metric-value tone-accent">{usage.calls.toLocaleString()}</div>
          <div className="metric-sub">${usage.cost.toFixed(6)}</div>
        </div>
      </div>

      <div className="section panel">
        <div className="section-head">
          <div className="section-title">{t("ov.llmUsage")}</div>
          <div className="section-note">{t("ov.llmUsageNote")}</div>
        </div>
        <div className="manifest">
          <div className="mf-row">
            <span className="mf-key">{t("report.calls")}</span>
            <span className="mf-val">{usage.calls}</span>
          </div>
          <div className="mf-row">
            <span className="mf-key">{t("report.inout")}</span>
            <span className="mf-val">
              {usage.prompt.toLocaleString()} / {usage.completion.toLocaleString()}
            </span>
          </div>
          <div className="mf-row">
            <span className="mf-key">{t("report.cost")}</span>
            <span className="mf-val">${usage.cost.toFixed(6)}</span>
          </div>
          <div className="mf-row">
            <span className="mf-key">{t("ov.llmRuns")}</span>
            <span className="mf-val">{tasks.length}</span>
          </div>
        </div>
        <div className="panel-note">{t("detail.tokensNote")}</div>
      </div>

      <div className="section">
        <div className="section-head">
          <div className="section-title">{t("ov.dmta")}</div>
          <div className="section-note">{t("ov.dmtaNote")}</div>
        </div>
        <div className="loop">
          {[
            ["target", "stage.target"],
            ["design", "stage.design"],
            ["make", "stage.make"],
            ["test", "stage.test"],
            ["analyze", "stage.analyze"],
          ].map(([key, labelKey], i, arr) => {
            const idx = task ? arr.findIndex(([k]) => k === task.stage) : -1;
            const done = task?.status === "succeeded";
            const state = !task ? "pending" : done ? "done" : idx === -1 ? "pending" : i < idx ? "done" : i === idx ? "running" : "pending";
            return (
              <span key={key} style={{ display: "contents" }}>
                {i > 0 && <span className="loop-arrow">→</span>}
                <div className={`loop-node ${state}`}>
                  <span className="loop-dot" />
                  {t(labelKey)}
                </div>
              </span>
            );
          })}
        </div>
      </div>

      <div className="section panel-grid">
        <div className="panel">
          <div className="panel-title">{t("ov.dataSources")}</div>
          <div className="src-list">
            {datasets.slice(0, 6).map((d) => (
              <div className="src-row" key={d.id} onClick={() => navigate(`/catalog/${d.id}`)} style={{ cursor: "pointer" }}>
                <div>
                  <div className="src-name">{d.name}</div>
                  <div className="src-detail">
                    {d.n_files} {t("common.files")} · {d.source}
                  </div>
                </div>
                <Tag color={d.sensitivity === "public" ? "success" : d.sensitivity === "internal" ? "warning" : "error"}>
                  {t(`level.${d.sensitivity}`)}
                </Tag>
              </div>
            ))}
            {datasets.length === 0 && <Text type="secondary">{t("catalog.empty")}</Text>}
          </div>
        </div>
        <div className="panel">
          <div className="panel-title">{t("ov.recentRuns")}</div>
          <table className="table">
            <thead>
              <tr>
                <th>{t("th.run")}</th>
                <th>{t("th.status")}</th>
                <th>{t("th.rounds")}</th>
                <th>{t("th.updated")}</th>
              </tr>
            </thead>
            <tbody>
              {tasks.slice(0, 5).map((x) => (
                <tr key={x.task_id} onClick={() => navigate(`/tasks/${x.task_id}`)} style={{ cursor: "pointer" }}>
                  <td className="strong mono">{x.task_id}</td>
                  <td>
                    <Tag color={x.status === "succeeded" ? "success" : x.status === "running" ? "processing" : x.status === "blocked" ? "error" : "default"}>
                      {t(`status.${x.status}`)}
                    </Tag>
                  </td>
                  <td className="num">
                    {x.round}/{x.rounds}
                  </td>
                  <td className="num">{x.updated_at.slice(11, 19)}</td>
                </tr>
              ))}
              {tasks.length === 0 && (
                <tr>
                  <td colSpan={4}>
                    <Text type="secondary">{t("ov.noRun")}</Text>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
