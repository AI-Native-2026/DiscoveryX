import { useEffect, useState } from "react";
import { Card, Row, Col, Typography, Statistic, Space, List, Divider, Tag, Alert } from "antd";
import { CheckCircleFilled, CloseCircleFilled } from "@ant-design/icons";
import { api } from "../api/client";
import { useI18n } from "../i18n";
import type { HealthResponse } from "../api/types";

const { Title, Paragraph, Text } = Typography;

const COMPONENT_LABEL: Record<string, string> = {
  redis: "Redis",
  llm: "DeepSeek",
  chroma: "ChromaDB",
};

export default function System() {
  const { t } = useI18n();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [rag, setRag] = useState<{ total_chunks: number; embedding_model: string } | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    let alive = true;
    api
      .health()
      .then((h) => {
        if (!alive) return;
        setHealth(h);
        setStatus("ok");
      })
      .catch(() => alive && setStatus("error"));
    api.ragStatus().then((r) => alive && setRag(r)).catch(() => alive && setRag(null));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("sys.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("sys.title")}</Title>
      <Paragraph className="dx-lede">{t("sys.lede")}</Paragraph>

      {status === "loading" && <Alert type="info" showIcon message={t("sys.loading")} />}
      {status === "error" && <Alert type="error" showIcon message={t("sys.error")} description={t("sys.errorDesc", { api: api.base })} />}

      {health && (
        <>
          <div className="section">
            <Row gutter={[16, 16]}>
              {Object.entries(health.components).map(([k, v]) => (
                <Col xs={24} sm={12} lg={8} key={k}>
                  <Card className="dx-card" size="small">
                    <Space>
                      {v === "ok" || v === "configured" ? (
                        <CheckCircleFilled style={{ color: "#35d39a" }} />
                      ) : (
                        <CloseCircleFilled style={{ color: "#f5b544" }} />
                      )}
                      <Text strong>{COMPONENT_LABEL[k] ?? k}</Text>
                      <Tag>{v}</Tag>
                    </Space>
                  </Card>
                </Col>
              ))}
            </Row>
          </div>

          <div className="section">
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={10}>
                <Card className="dx-card" title={t("sys.service")}>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Statistic title={t("sys.version")} value={health.version} />
                    </Col>
                    <Col span={12}>
                      <Statistic title={t("sys.env")} value={health.environment} />
                    </Col>
                    <Col span={12} style={{ marginTop: 12 }}>
                      <Statistic title={t("sys.ragChunks")} value={rag?.total_chunks ?? 0} />
                    </Col>
                    <Col span={12} style={{ marginTop: 12 }}>
                      <Statistic title={t("sys.embedding")} value={rag?.embedding_model ?? "—"} valueStyle={{ fontSize: 14 }} />
                    </Col>
                  </Row>
                  <Divider style={{ margin: "12px 0" }} />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {t("sys.apiBase", { api: api.base })}
                  </Text>
                </Card>
              </Col>
              <Col xs={24} lg={14}>
                <Card className="dx-card" title={t("sys.arch")}>
                  <List
                    size="small"
                    dataSource={[
                      "FastAPI · RESTful API (/api/v1/tasks, /guardrails, /rag, /datasets, /projects)",
                      "Async worker (ARQ + Redis) · long-running DMTA tasks",
                      "ChromaDB · literature vectors (bge-m3), partitioned by sensitivity",
                      "DeepSeek API · deepseek-chat / deepseek-reasoner (only provider)",
                      "ADMET-AI · pretrained Chemprop models (hERG / DILI / BBBP / solubility …)",
                      "Real sources · PDB 4WY1 / MoleculeNet BACE / Europe PMC / ChEMBL",
                      "Structured JSON logs · trace_id across API → worker → agents",
                    ]}
                    renderItem={(item) => (
                      <List.Item>
                        <Text type="secondary">• {item}</Text>
                      </List.Item>
                    )}
                  />
                </Card>
              </Col>
            </Row>
          </div>
        </>
      )}
    </section>
  );
}
