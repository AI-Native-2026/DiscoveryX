import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Typography, Alert, Empty, Tag, Progress, Button } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { api } from "../api/client";
import { useI18n } from "../i18n";
import type { DatasetInfo } from "../api/types";

const { Title, Paragraph, Text } = Typography;

interface RagStatus {
  store: string;
  path: string;
  embedding_model: string;
  collections: { collection: string; chunks: number }[];
  total_chunks: number;
}

export default function Knowledge() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    api.ragStatus().then((s) => setStatus(s as RagStatus)).catch((e) => setError((e as Error).message));
    api.listDatasets().then((r) => setDatasets(r.items)).catch(() => setDatasets([]));
  };

  useEffect(load, []);

  const maxChunks = Math.max(1, ...(status?.collections ?? []).map((c) => c.chunks));

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("kn.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("kn.title")}</Title>
      <Paragraph className="dx-lede">{t("kn.lede")}</Paragraph>

      {error && <Alert style={{ marginTop: 16 }} type="warning" showIcon message={error} />}

      <div className="section stat-row">
        <div className="stat">
          <div className="stat-label">{t("kn.embedding")}</div>
          <div className="stat-value" style={{ fontSize: 15 }}>
            {status?.embedding_model ?? t("common.none")}
          </div>
        </div>
        <div className="stat">
          <div className="stat-label">{t("kn.store")}</div>
          <div className="stat-value" style={{ fontSize: 15 }}>
            {status?.store ?? t("common.none")}
          </div>
        </div>
        <div className="stat">
          <div className="stat-label">{t("kn.collections")}</div>
          <div className="stat-value">{status?.collections.length ?? 0}</div>
        </div>
        <div className="stat">
          <div className="stat-label">{t("kn.chunks")}</div>
          <div className="stat-value tone-accent">{status?.total_chunks ?? 0}</div>
        </div>
      </div>

      <div className="section panel">
        <div className="section-head">
          <div className="panel-title" style={{ marginBottom: 0 }}>
            {t("kn.distribution")}
          </div>
          <Button size="small" icon={<ReloadOutlined />} onClick={load}>
            {t("common.refresh")}
          </Button>
        </div>
        {!status || status.collections.length === 0 ? (
          <Empty description={t("kn.empty")} />
        ) : (
          <div className="endpoints" style={{ marginTop: 12 }}>
            {status.collections.map((c) => (
              <div key={c.collection}>
                <div className="ep-head">
                  <span className="mono">{c.collection}</span>
                  <span>{c.chunks} chunks</span>
                </div>
                <Progress percent={Math.round((c.chunks / maxChunks) * 100)} showInfo={false} strokeColor="#3dd6c4" />
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="section panel">
        <div className="panel-title">{t("kn.datasetIndex")}</div>
        <table className="table">
          <thead>
            <tr>
              <th>{t("th.name")}</th>
              <th>{t("common.sensitivity")}</th>
              <th>{t("th.fileCount")}</th>
              <th>{t("th.purpose")}</th>
              <th>{t("th.rag")}</th>
            </tr>
          </thead>
          <tbody>
            {datasets.map((d) => (
              <tr key={d.id} onClick={() => navigate(`/catalog/${d.id}`)} style={{ cursor: "pointer" }}>
                <td className="strong mono">{d.id}</td>
                <td>
                  <Tag color={d.sensitivity === "public" ? "success" : d.sensitivity === "internal" ? "warning" : "error"}>
                    {t(`level.${d.sensitivity}`)}
                  </Tag>
                </td>
                <td className="num">{d.n_files}</td>
                <td>
                  <Text type="secondary">{t(`purpose.${d.purpose}`)}</Text>
                </td>
                <td>{d.rag_indexed ? <Tag color="success">{t("ds.indexed")}</Tag> : <Tag>{t("ds.notIndexed")}</Tag>}</td>
              </tr>
            ))}
            {datasets.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <Text type="secondary">{t("catalog.empty")}</Text>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Text type="secondary" style={{ fontSize: 12 }}>
        {t("kn.storage", { path: status?.path ?? "—" })}
      </Text>
    </section>
  );
}
