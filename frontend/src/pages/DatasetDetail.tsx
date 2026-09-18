import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Typography, Tag, Button, Alert, message, Empty, Space, Upload, Card, Popconfirm } from "antd";
import { ArrowLeftOutlined, ReloadOutlined, DatabaseOutlined, InboxOutlined, DeleteOutlined } from "@ant-design/icons";
import { api, ApiError } from "../api/client";
import { useI18n } from "../i18n";
import type { DatasetFile, DatasetInfo } from "../api/types";

const { Title, Paragraph, Text } = Typography;

function humanSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function DatasetDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [info, setInfo] = useState<DatasetInfo | null>(null);
  const [files, setFiles] = useState<DatasetFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    if (!id) return;
    setError(null);
    api
      .getDataset(id)
      .then(setInfo)
      .catch((e) => setError(e instanceof ApiError ? e.message : (e as Error).message));
    api.datasetFiles(id).then((r) => setFiles(r.items)).catch(() => setFiles([]));
  };

  useEffect(load, [id]);

  const index = async () => {
    if (!id) return;
    setBusy(true);
    try {
      const r = await api.indexDataset(id);
      message.success(t("ds.indexedMsg", { docs: r.documents, chunks: r.chunks, collection: r.collection }));
      load();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!id) return;
    setBusy(true);
    try {
      await api.deleteDataset(id);
      message.success(t("ds.deleted", { id }));
      navigate("/catalog");
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (error) return <Alert type="error" showIcon message={error} />;
  if (!info) return <Empty description={t("common.loading")} />;

  const compound = (info.meta?.compound as Record<string, unknown>) ?? {};
  const hasCompound = Object.keys(compound).length > 0;
  const usable = Boolean(compound.usable_for_dmta);

  return (
    <section className="view">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/catalog")} style={{ marginBottom: 8 }}>
        {t("common.back")}
      </Button>

      <Paragraph className="dx-eyebrow">{t("ds.eyebrow")}</Paragraph>
      <Title className="dx-h1">
        {info.name} <Tag color={info.sensitivity === "public" ? "success" : info.sensitivity === "internal" ? "warning" : "error"}>{t(`level.${info.sensitivity}`)}</Tag>
      </Title>
      <Paragraph className="dx-lede">
        {t("common.source")}：{info.source} · {t("ds.owner")}：{info.owner} · {t("ds.path")}：<Text className="dx-mono">{info.path}</Text>
      </Paragraph>

      <div className="section stat-row">
        <div className="stat">
          <div className="stat-label">{t("ds.nFiles")}</div>
          <div className="stat-value">{info.n_files}</div>
        </div>
        <div className="stat">
          <div className="stat-label">{t("ds.size")}</div>
          <div className="stat-value">{humanSize(info.size_bytes)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">{t("ds.formats")}</div>
          <div className="stat-value" style={{ fontSize: 13 }}>
            {Object.entries(info.file_types)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 3)
              .map(([e, n]) => `${e} ${n}`)
              .join(" · ") || t("common.none")}
          </div>
        </div>
        <div className="stat">
          <div className="stat-label">{t("ds.ragIndex")}</div>
          <div className="stat-value" style={{ fontSize: 14 }}>
            {info.rag_indexed ? <Tag color="success">{t("ds.indexed")}</Tag> : <Tag>{t("ds.notIndexed")}</Tag>}
          </div>
        </div>
      </div>

      <div className="section btn-row">
        <Button type="primary" icon={<DatabaseOutlined />} loading={busy} onClick={index}>
          {t("ds.index")}
        </Button>
        <Button icon={<ReloadOutlined />} onClick={load}>
          {t("common.refresh")}
        </Button>
        <Popconfirm
          title={t("ds.delete")}
          description={t("ds.deleteConfirm", { name: info.name })}
          okText={t("ds.delete")}
          okButtonProps={{ danger: true }}
          cancelText={t("common.cancel")}
          onConfirm={remove}
        >
          <Button danger icon={<DeleteOutlined />} loading={busy}>
            {t("ds.delete")}
          </Button>
        </Popconfirm>
      </div>

      {hasCompound && (
        <div className="section panel">
          <div className="section-head">
            <div className="panel-title" style={{ marginBottom: 0 }}>
              {t("ds.compound")}
            </div>
            <Tag color={usable ? "success" : "warning"}>{usable ? t("ds.usableYes") : t("ds.usableNo")}</Tag>
          </div>
          <div className="manifest">
            <div className="mf-row">
              <span className="mf-key">{t("ds.file")}</span>
              <span className="mf-val">{String(compound.file ?? t("common.none"))}</span>
            </div>
            <div className="mf-row">
              <span className="mf-key">{t("ds.smilesCol")}</span>
              <span className="mf-val">{String(compound.smiles_column ?? t("common.none"))}</span>
            </div>
            <div className="mf-row">
              <span className="mf-key">{t("ds.activityCol")}</span>
              <span className="mf-val">{String(compound.activity_column ?? t("common.none"))}</span>
            </div>
            <div className="mf-row">
              <span className="mf-key">{t("ds.activityKind")}</span>
              <span className="mf-val">{String(compound.activity_kind ?? t("common.none"))}</span>
            </div>
          </div>
          {!usable && <div className="panel-note">{t("ds.reason", { reason: String(compound.reason ?? "") })}</div>}
        </div>
      )}

      <div className="section">
        <Card className="dx-card" title={t("ds.upload")}>
          <Upload.Dragger
            multiple
            beforeUpload={() => false}
            showUploadList={false}
            customRequest={async ({ file, onSuccess, onError }) => {
              if (!id) return;
              try {
                const r = await api.uploadDatasetFiles(id, [file as File]);
                message.success(t("ds.uploaded", { n: r.uploaded }));
                load();
                onSuccess?.(r);
              } catch (e) {
                message.error(e instanceof ApiError ? e.message : (e as Error).message);
                onError?.(e as Error);
              }
            }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">{t("ds.uploadText")}</p>
            <p className="ant-upload-hint">{t("ds.uploadHint", { path: info.path ?? "" })}</p>
          </Upload.Dragger>
          <div className="panel-note">{t("ds.uploadNote")}</div>
        </Card>
      </div>

      <div className="section panel" style={{ overflowX: "auto" }}>
        <div className="panel-title">{t("ds.files", { shown: files.length, total: info.n_files })}</div>
        <table className="table">
          <thead>
            <tr>
              <th>{t("ds.fileName")}</th>
              <th>{t("th.type")}</th>
              <th>{t("ds.fileSize")}</th>
              <th>{t("ds.fileModified")}</th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.rel_path}>
                <td className="mono" style={{ fontSize: 12 }}>
                  {f.rel_path}
                </td>
                <td>
                  <Tag>{f.ext}</Tag>
                </td>
                <td className="num">{humanSize(f.size_bytes)}</td>
                <td className="num">{f.modified_at.replace("T", " ").slice(0, 19)}</td>
              </tr>
            ))}
            {files.length === 0 && (
              <tr>
                <td colSpan={4}>
                  <Text type="secondary">{t("ds.emptyDir")}</Text>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="section panel">
        <div className="panel-title">{t("ds.lineage")}</div>
        <Space wrap>
          <Tag>{t("ds.l1")}</Tag>→<Tag>{t("ds.l2")} ({info.id}/)</Tag>→<Tag>{t("ds.l3")}</Tag>→<Tag>{t("ds.l4")}</Tag>→
          <Tag color={info.rag_indexed ? "success" : "default"}>{info.rag_indexed ? t("ds.l5") : t("ds.l5no")}</Tag>
        </Space>
      </div>
    </section>
  );
}
