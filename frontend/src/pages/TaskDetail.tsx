import { useEffect, useRef, useState } from "react";
import { Card, Row, Col, Tag, Typography, Timeline, Table, Statistic, Progress, Button, Space, Divider, Alert, Empty } from "antd";
import { ArrowLeftOutlined, CheckCircleTwoTone, CloseCircleTwoTone, DownloadOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import DmtaFlow from "../components/DmtaFlow";
import { api } from "../api/client";
import { useActiveTask } from "../state/taskContext";
import { useI18n } from "../i18n";
import { decisionLabel, roundSummaryLabel } from "../lib/labels";
import type { Candidate, TaskState } from "../api/types";

const { Title, Paragraph, Text } = Typography;

export default function TaskDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t, lang } = useI18n();
  const [task, setTask] = useState<TaskState | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const { setActiveTask } = useActiveTask();

  useEffect(() => {
    if (task) setActiveTask(task);
  }, [task, setActiveTask]);

  useEffect(() => {
    if (!id) return;
    const poll = async () => {
      try {
        const state = await api.getTask(id);
        setTask(state);
        if (state.status === "queued" || state.status === "running") {
          timer.current = window.setTimeout(poll, 2000);
        }
      } catch (e) {
        setErr((e as Error).message);
      }
    };
    poll();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [id]);

  if (err) return <Alert type="error" showIcon message={err} />;
  if (!task) return <Empty description={t("common.loading")} />;

  const report = task.result ?? null;
  const ds = (report?.dataset ?? {}) as Record<string, unknown>;
  const model = (report?.activity_model ?? {}) as Record<string, unknown>;
  const metrics = (model.metrics as Record<string, number>) ?? {};

  // Only surface the endpoints this run was optimising (see Design.tsx).
  const objectives = task.objectives ?? report?.objectives ?? [];
  const wantBbb = objectives.includes("BBB");
  const wantHep = objectives.includes("hepatotoxicity");
  const wantSol = objectives.includes("solubility");

  return (
    <div>
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/tasks")} style={{ marginBottom: 8 }}>
        {t("detail.back")}
      </Button>

      <Row justify="space-between" align="middle" wrap gutter={12}>
        <Col>
          <Paragraph className="dx-eyebrow" style={{ marginBottom: 4 }}>
            {t("detail.eyebrow")}
          </Paragraph>
          <Title className="dx-h1">
            <Text className="dx-mono" style={{ fontSize: 18, color: "#8b98ad", marginRight: 10 }}>
              {task.task_id}
            </Text>
            {t("detail.title", { target: report?.target ?? task.target ?? "—" })}
          </Title>
        </Col>
        <Col>
          <Space size={16}>
            <Tag color={task.status === "succeeded" ? "success" : task.status === "running" ? "processing" : task.status === "blocked" || task.status === "failed" ? "error" : "default"}>
              {t(`status.${task.status}`)}
            </Tag>
            <div style={{ minWidth: 170 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t("detail.round", { r: task.round, n: task.rounds })} · {task.stage}
              </Text>
              <Progress percent={Math.round(task.progress * 100)} size="small" />
            </div>
          </Space>
        </Col>
      </Row>

      {task.error && <Alert style={{ marginTop: 12 }} type="error" showIcon message={t("detail.error")} description={task.error} />}

      <div className="dx-section">
        <Card className="dx-card" title={t("detail.topology")} extra={<Text type="secondary">{t("detail.topologyNote")}</Text>}>
          <DmtaFlow stage={task.stage} status={task.status} />
        </Card>
      </div>

      <div className="dx-section">
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={14}>
            <Card className="dx-card" title={t("detail.rounds")} style={{ height: "100%" }}>
              {report?.rounds?.length ? (
                <Timeline
                  items={report.rounds.map((r) => ({
                    color: r.decision === "met" ? "green" : "blue",
                    children: (
                      <div>
                        <Space>
                          <Text strong>R{r.round}</Text>
                          <Tag color={r.decision === "met" ? "success" : "processing"}>{t("detail.passed", { n: r.passed })}</Tag>
                        </Space>
                        <div style={{ color: "#b6c2d8", marginTop: 4 }}>{roundSummaryLabel(r.summary, lang)}</div>
                        {r.action && <div className="src-detail" style={{ marginTop: 2 }}>{r.action}</div>}
                        {r.narrative && (
                          <div style={{ color: "#8b98ad", marginTop: 4, fontStyle: "italic" }}>{r.narrative}</div>
                        )}
                      </div>
                    ),
                  }))}
                />
              ) : (
                <Empty description={t("detail.waiting")} />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={10}>
            <Card className="dx-card" title={t("detail.tokens")} style={{ height: "100%" }}>
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic title={t("detail.calls")} value={task.token_usage.calls} />
                </Col>
                <Col span={8}>
                  <Statistic
                    title={t("detail.inout")}
                    value={`${task.token_usage.prompt_tokens} / ${task.token_usage.completion_tokens}`}
                  />
                </Col>
                <Col span={8}>
                  <Statistic title={t("detail.cost")} value={task.token_usage.cost_usd} precision={6} prefix="$" />
                </Col>
              </Row>
              <Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 10 }}>
                {t("detail.tokensNote")}
              </Text>
              <Divider style={{ margin: "12px 0" }} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t("detail.logs", { trace: task.trace_id ?? "-" })}
              </Text>
              <div className="dx-json" style={{ marginTop: 8 }}>
                {task.events.slice(-8).map((e) => JSON.stringify(e)).join("\n") || "—"}
              </div>
            </Card>
          </Col>
        </Row>
      </div>

      {report && (
        <div className="dx-section">
          <Card
            className="dx-card"
            title={t("detail.datasetModel")}
          >
            <div className="manifest">
              <div className="mf-row">
                <span className="mf-key">{t("report.dataset")}</span>
                <span className="mf-val">{String(ds.dataset_id ?? "built-in")}</span>
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
              <div className="mf-row">
                <span className="mf-key">{t("detail.retries")}</span>
                <span className="mf-val">{task.attempts ?? 0}</span>
              </div>
            </div>
          </Card>
        </div>
      )}

      {report && (
        <div className="dx-section">
          <Card
            className="dx-card"
            title={t("detail.report")}
            extra={
              <Button
                icon={<DownloadOutlined />}
                type="primary"
                onClick={() => {
                  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `${task.task_id}-report.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                {t("detail.exportJson")}
              </Button>
            }
            styles={{ body: { padding: 0 } }}
          >
            <Table<Candidate>
              rowKey="id"
              dataSource={report.top_candidates}
              pagination={false}
              columns={[
                { title: t("th.id"), dataIndex: "id", width: 56 },
                {
                  title: t("th.smiles"),
                  dataIndex: "smiles",
                  render: (v: string) => (
                    <Text className="dx-mono" style={{ fontSize: 11 }}>
                      {v.length > 40 ? `${v.slice(0, 40)}…` : v}
                    </Text>
                  ),
                },
                { title: t("th.pic50"), dataIndex: "pIC50", render: (v: number | null) => (v == null ? "—" : <Text strong>{v.toFixed(1)}</Text>) },
                ...(wantBbb
                  ? [
                      {
                        title: t("th.bbb"),
                        dataIndex: "bbb",
                        render: (v: boolean | null) =>
                          v == null ? "—" : v ? (
                            <CheckCircleTwoTone twoToneColor="#35d39a" />
                          ) : (
                            <CloseCircleTwoTone twoToneColor="#f2707a" />
                          ),
                      },
                    ]
                  : []),
                ...(wantHep
                  ? [
                      {
                        title: t("th.hepato"),
                        dataIndex: "hepatotoxic",
                        render: (v: boolean | null) =>
                          v == null ? "—" : v ? (
                            <CloseCircleTwoTone twoToneColor="#f2707a" />
                          ) : (
                            <CheckCircleTwoTone twoToneColor="#35d39a" />
                          ),
                      },
                    ]
                  : []),
                ...(wantSol
                  ? [
                      {
                        title: t("obj.solubility"),
                        dataIndex: "solubility",
                        render: (v: number | null) => (v == null ? "—" : v.toFixed(2)),
                      },
                    ]
                  : []),
                { title: t("th.sa"), dataIndex: "sa_score", render: (v: number | null) => (v == null ? "—" : v.toFixed(1)) },
                { title: t("th.route"), dataIndex: "route_steps", render: (v: number | null) => (v == null ? "—" : `${v}`) },
                { title: t("th.mpo"), dataIndex: "mpo", render: (v: number | null) => (v == null ? "—" : <Tag color="cyan">{v.toFixed(2)}</Tag>) },
              ]}
            />
          </Card>
        </div>
      )}

      <div className="dx-section">
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card className="dx-card" title={t("detail.decision")}>
              <Paragraph style={{ color: "#c9d4e6" }}>{report ? decisionLabel(report.decision, lang) : t("detail.running")}</Paragraph>
              {report?.top_candidates?.[0]?.rationale && (
                <Alert type="info" showIcon message={t("design.rationale")} description={report.top_candidates[0].rationale} />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card className="dx-card" title={t("detail.evidence")}>
              {report?.evidence?.length ? (
                <ul style={{ paddingLeft: 18, color: "#b6c2d8" }}>
                  {report.evidence.map((e, i) => (
                    <li key={i}>
                      <Tag color={e.type === "pdb" ? "blue" : "cyan"}>{e.type.toUpperCase()}</Tag>
                      {e.id} {e.title ? `· ${e.title}` : ""} {e.score ? `· ${e.score}` : ""}
                    </li>
                  ))}
                </ul>
              ) : (
                <Text type="secondary">{t("detail.noEvidence")}</Text>
              )}
            </Card>
          </Col>
        </Row>
      </div>
    </div>
  );
}
