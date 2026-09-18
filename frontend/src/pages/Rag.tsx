import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, Input, Button, Typography, List, Space, Tag, Row, Col, Alert, Empty, Spin } from "antd";
import { SearchOutlined, LinkOutlined } from "@ant-design/icons";
import { api, ApiError } from "../api/client";
import { useI18n } from "../i18n";
import type { RAGResult } from "../api/types";

const { Title, Paragraph, Text } = Typography;

export default function Rag() {
  const [params] = useSearchParams();
  const { t } = useI18n();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [result, setResult] = useState<RAGResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<{ total_chunks: number; embedding_model: string } | null>(null);

  useEffect(() => {
    api.ragStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.ragQuery(query));
    } catch (e) {
      setError(e instanceof ApiError && e.status === 403 ? `${t("common.notAllowed")}: ${e.message}` : (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("rag.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("rag.title")}</Title>
      <Paragraph className="dx-lede">
        {t("rag.lede")}
        {status && <Text type="secondary"> {t("rag.index", { chunks: status.total_chunks, model: status.embedding_model })}</Text>}
      </Paragraph>

      <div className="section">
        <Space.Compact style={{ width: "100%" }}>
          <Input size="large" value={query} onChange={(e) => setQuery(e.target.value)} onPressEnter={run} prefix={<SearchOutlined />} />
          <Button size="large" type="primary" loading={loading} onClick={run}>
            {t("rag.search")}
          </Button>
        </Space.Compact>
      </div>

      {error && <Alert style={{ marginTop: 16 }} type="error" showIcon message={error} />}

      <div className="section">
        {loading && <Spin />}
        {!loading && result && (
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={13}>
              <Card className="dx-card" title={t("rag.answer")}>
                <Paragraph style={{ color: "#c9d4e6", whiteSpace: "pre-wrap" }}>{result.answer}</Paragraph>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {t("rag.used", { used: result.used_chunks, blocked: result.blocked_chunks })}
                </Text>
                {result.token_usage && result.token_usage.calls > 0 && (
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {t("rag.usage", {
                        calls: result.token_usage.calls,
                        prompt: result.token_usage.prompt_tokens,
                        completion: result.token_usage.completion_tokens,
                        cost: result.token_usage.cost_usd.toFixed(6),
                      })}
                    </Text>
                  </div>
                )}
              </Card>
            </Col>
            <Col xs={24} lg={11}>
              <Card className="dx-card" title={t("rag.sources")}>
                {result.citations.length ? (
                  <List
                    dataSource={result.citations}
                    renderItem={(c) => (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <Space>
                              <Tag color="cyan">{c.id}</Tag>
                              <Text strong>{c.title || "(untitled)"}</Text>
                            </Space>
                          }
                          description={
                            <Space wrap>
                              <Text type="secondary">{c.source}</Text>
                              <Tag color="blue">
                                {t("rag.relevance")} {c.score.toFixed(3)}
                              </Tag>
                              <Tag>{t(`level.${c.sensitivity}`)}</Tag>
                              <LinkOutlined style={{ color: "#8b98ad" }} />
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty description={t("rag.noSources")} />
                )}
              </Card>
            </Col>
          </Row>
        )}
        {!loading && !result && !error && <Empty description={t("rag.empty")} />}
      </div>
    </section>
  );
}
