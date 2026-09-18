import { useCallback, useEffect, useState } from "react";
import { Card, Table, Typography, Button, Space, Tag, Row, Col, message, Alert, Empty, Input } from "antd";
import { SafetyOutlined, CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { api, ApiError, getPrincipal } from "../api/client";
import { useI18n } from "../i18n";
import type { ApprovalOut, AuditEvent } from "../api/types";

const { Title, Paragraph, Text } = Typography;

interface PolicyView {
  roles: Record<string, { permissions: string[]; clearance: string }>;
  dlp_rules: { name: string; action: string; pattern: string }[];
}

// Mirrors backend/config/rbac_policy.json so the page does not poll endpoints the
// current role cannot read. The API still enforces the permission either way.
const CAN_READ_AUDIT = new Set(["auditor", "admin", "engineer"]);
const CAN_READ_POLICY = new Set(["auditor", "admin"]);

export default function Guardrails() {
  const { t } = useI18n();
  const [approvals, setApprovals] = useState<ApprovalOut[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [policy, setPolicy] = useState<PolicyView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    const role = getPrincipal().role;
    api
      .listApprovals()
      .then((r) => setApprovals(r.items))
      .catch((e) => setError(e instanceof ApiError && e.status === 403 ? t("gv.needPermission") : (e as Error).message));
    if (CAN_READ_AUDIT.has(role)) {
      api.listAudit(100).then((r) => setEvents(r.items)).catch(() => setEvents([]));
    } else {
      setEvents([]);
    }
    if (CAN_READ_POLICY.has(role)) {
      api.policy().then((p) => setPolicy(p as never)).catch(() => setPolicy(null));
    } else {
      setPolicy(null);
    }
  }, [t]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
  }, [load]);

  const decide = async (a: ApprovalOut, decision: "approved" | "rejected") => {
    setBusy(a.id);
    try {
      await api.decideApproval(a.id, decision, comments[a.id]);
      message.success(decision === "approved" ? t("gv.approved") : t("gv.rejected"));
      load();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const pending = approvals.filter((a) => a.status === "pending");
  const history = approvals.filter((a) => a.status !== "pending");

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("gv.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("gv.title")}</Title>
      <Paragraph className="dx-lede">{t("gv.lede")}</Paragraph>

      {error && <Alert style={{ marginTop: 16 }} type="warning" showIcon message={error} />}

      <div className="section">
        <Card
          className="dx-card"
          title={
            <Space>
              <SafetyOutlined /> {t("gv.pending", { n: pending.length })}
            </Space>
          }
        >
          {pending.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("gv.noPending")} />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {pending.map((a) => (
                <div className="approval" key={a.id}>
                  <div className="ap-title">
                    {a.title} <Tag style={{ marginInlineStart: 8 }}>{a.kind}</Tag>
                  </div>
                  <div className="ap-body">{a.detail}</div>
                  <div className="mf-row" style={{ borderBottom: "none", padding: 0 }}>
                    <span className="mf-key">
                      {a.id} · {a.task_id} · {t("gv.applicant")} {a.requested_by}
                    </span>
                    <span className="mf-val">{a.requested_at.replace("T", " ").slice(0, 19)}</span>
                  </div>
                  <Input
                    size="small"
                    placeholder={t("gv.commentPh")}
                    value={comments[a.id] ?? ""}
                    onChange={(e) => setComments((c) => ({ ...c, [a.id]: e.target.value }))}
                    style={{ margin: "10px 0" }}
                  />
                  <div className="ap-actions">
                    <Button type="primary" icon={<CheckOutlined />} loading={busy === a.id} onClick={() => decide(a, "approved")}>
                      {t("gv.approve")}
                    </Button>
                    <Button danger icon={<CloseOutlined />} loading={busy === a.id} onClick={() => decide(a, "rejected")}>
                      {t("gv.reject")}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {history.length > 0 && (
        <div className="section">
          <Card className="dx-card" title={t("gv.history")} styles={{ body: { padding: 0 } }}>
            <Table<ApprovalOut>
              rowKey="id"
              dataSource={history}
              pagination={{ pageSize: 6 }}
              columns={[
                { title: t("gv.item"), dataIndex: "title" },
                {
                  title: t("gv.decision"),
                  dataIndex: "status",
                  render: (v: string) => <Tag color={v === "approved" ? "success" : "error"}>{v}</Tag>,
                },
                { title: t("gv.decider"), dataIndex: "decided_by" },
                { title: t("gv.time"), dataIndex: "decided_at", render: (v: string) => (v ? v.replace("T", " ").slice(0, 19) : t("common.none")) },
                { title: t("gv.comment"), dataIndex: "comment", render: (v: string) => v || t("common.none") },
              ]}
            />
          </Card>
        </div>
      )}

      <div className="section">
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card className="dx-card" title={t("gv.rbac")}>
              {policy ? (
                <div className="manifest">
                  {Object.entries(policy.roles).map(([role, v]) => (
                    <div className="mf-row" key={role}>
                      <span className="mf-key mono">{role}</span>
                      <span className="mf-val" style={{ fontFamily: "var(--font)", fontSize: 12 }}>
                        {v.clearance} · {v.permissions.join(", ")}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty description={t("gv.needGuardrails")} />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card className="dx-card" title={t("gv.dlpRules")}>
              {policy ? (
                <>
                  <div className="manifest">
                    {policy.dlp_rules.map((r) => (
                      <div className="mf-row" key={r.name}>
                        <span className="mf-key">{r.name}</span>
                        <span>
                          <Tag color={r.action === "BLOCK" ? "error" : "warning"}>{r.action}</Tag>
                          <Text className="dx-mono" type="secondary" style={{ fontSize: 11 }}>
                            {r.pattern}
                          </Text>
                        </span>
                      </div>
                    ))}
                  </div>
                  <Alert style={{ marginTop: 12 }} type="info" showIcon message={t("gv.dlpNote")} />
                </>
              ) : (
                <Empty description={t("gv.needGuardrails")} />
              )}
            </Card>
          </Col>
        </Row>
      </div>

      <div className="section">
        <Card className="dx-card" title={t("gv.audit")} styles={{ body: { padding: 0 } }}>
          <Table<AuditEvent>
            rowKey={(r) => `${r.ts}-${r.trace_id}-${r.action}-${r.resource}`}
            dataSource={events}
            pagination={{ pageSize: 12 }}
            columns={[
              {
                title: t("gv.time"),
                dataIndex: "ts",
                width: 180,
                render: (v: string) => (
                  <Text className="dx-mono" style={{ fontSize: 11 }}>
                    {v.replace("T", " ").slice(0, 19)}
                  </Text>
                ),
              },
              { title: t("th.actor"), dataIndex: "actor", width: 100 },
              { title: t("th.role"), dataIndex: "role", width: 100 },
              { title: t("th.action"), dataIndex: "action", render: (v: string) => <Text className="dx-mono">{v}</Text> },
              { title: t("th.resource"), dataIndex: "resource", width: 140 },
              {
                title: t("gv.decision"),
                dataIndex: "decision",
                width: 100,
                render: (v: string) => <Tag color={v === "ALLOW" ? "success" : v === "BLOCKED" ? "error" : "warning"}>{v}</Tag>,
              },
              { title: t("th.reason"), dataIndex: "reason" },
            ]}
          />
        </Card>
      </div>
    </section>
  );
}
