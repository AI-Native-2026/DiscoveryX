import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Typography, Tag, Alert, Button, Empty } from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { api, ApiError } from "../api/client";
import { useI18n } from "../i18n";
import type { DatasetInfo } from "../api/types";

const { Title, Paragraph, Text } = Typography;

export default function Catalog() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [items, setItems] = useState<DatasetInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");

  const load = () => {
    api
      .listDatasets()
      .then((r) => setItems(r.items))
      .catch((e) => setError(e instanceof ApiError && e.status === 403 ? t("common.notAllowed") : (e as Error).message));
  };

  useEffect(load, []);

  const filters = [
    { key: "all", label: t("catalog.all") },
    { key: "public", label: t("level.public") },
    { key: "internal", label: t("level.internal") },
    { key: "document", label: t("type.document") },
    { key: "tabular", label: t("type.tabular") },
    { key: "structure", label: t("type.structure") },
  ];
  const shown = items.filter((d) => filter === "all" || d.sensitivity === filter || d.data_type === filter);

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("catalog.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("catalog.title")}</Title>
      <Paragraph className="dx-lede">{t("catalog.lede")}</Paragraph>

      {error && <Alert style={{ marginTop: 16 }} type="warning" showIcon message={error} />}

      <div className="section chips">
        {filters.map((f) => (
          <button key={f.key} className={`chip ${filter === f.key ? "active" : ""}`} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
        <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <Button icon={<ReloadOutlined />} onClick={load}>
            {t("common.refresh")}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/import")}>
            {t("catalog.import")}
          </Button>
        </span>
      </div>

      {shown.length === 0 ? (
        <div className="section panel">
          <Empty description={t("catalog.empty")} />
        </div>
      ) : (
        <div className="section panel" style={{ overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>{t("th.name")}</th>
                <th>{t("th.type")}</th>
                <th>{t("common.source")}</th>
                <th>{t("common.sensitivity")}</th>
                <th>{t("th.fileCount")}</th>
                <th>{t("th.formats")}</th>
                <th>{t("th.rag")}</th>
                <th>{t("th.purpose")}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((d) => (
                <tr key={d.id} onClick={() => navigate(`/catalog/${d.id}`)} style={{ cursor: "pointer" }}>
                  <td>
                    <Text strong>{d.name}</Text>
                    <div className="src-detail mono">{d.id}/</div>
                  </td>
                  <td>
                    <Tag>{t(`type.${d.data_type}`)}</Tag>
                  </td>
                  <td>{d.source}</td>
                  <td>
                    <Tag color={d.sensitivity === "public" ? "success" : d.sensitivity === "internal" ? "warning" : "error"}>
                      {t(`level.${d.sensitivity}`)}
                    </Tag>
                  </td>
                  <td className="num">{d.n_files}</td>
                  <td className="mono" style={{ fontSize: 11 }}>
                    {Object.entries(d.file_types)
                      .sort((a, b) => b[1] - a[1])
                      .slice(0, 4)
                      .map(([ext, n]) => `${ext}×${n}`)
                      .join(" ") || t("common.none")}
                  </td>
                  <td>{d.rag_indexed ? <Tag color="success">{t("catalog.indexed")}</Tag> : <Text type="secondary">{t("common.none")}</Text>}</td>
                  <td>
                    <Text type="secondary">{t(`purpose.${d.purpose}`)}</Text>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
