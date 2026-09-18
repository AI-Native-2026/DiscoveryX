import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Typography, Button, Alert, Steps, Form, Input, Select, message, Card } from "antd";
import { api, ApiError } from "../api/client";
import { useI18n } from "../i18n";

const { Title, Paragraph, Text } = Typography;

export default function Import() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [step, setStep] = useState(0);
  const [form] = Form.useForm();
  const [created, setCreated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const values = await form.validateFields();
    setBusy(true);
    try {
      const info = await api.createDataset({
        id: values.id,
        name: values.name,
        data_type: values.data_type,
        source: values.source,
        sensitivity: values.sensitivity,
        purpose: values.purpose,
        description: values.description ?? "",
      });
      setCreated(info.id);
      setStep(2);
      message.success(t("import.created", { id: info.id }));
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const index = async () => {
    if (!created) return;
    setBusy(true);
    try {
      const r = await api.indexDataset(created);
      message.success(t("ds.indexedMsg", { docs: r.documents, chunks: r.chunks, collection: r.collection }));
      navigate(`/catalog/${created}`);
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="view">
      <Paragraph className="dx-eyebrow">{t("import.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("import.title")}</Title>
      <Paragraph className="dx-lede">{t("import.lede")}</Paragraph>

      <div className="section">
        <Steps current={step} items={[{ title: t("import.step1") }, { title: t("import.step2") }, { title: t("import.step3") }]} />
      </div>

      <div className="section panel-grid">
        <Card className="dx-card" title={t("import.dirTitle")}>
          <Form
            form={form}
            layout="vertical"
            initialValues={{ data_type: "document", sensitivity: "internal", purpose: "rag", source: "upload", id: "AAA", name: "Dataset AAA" }}
            disabled={step > 1}
          >
            <Form.Item
              name="id"
              label={t("import.dirName")}
              rules={[{ required: true, pattern: /^[a-zA-Z0-9_-]{2,64}$/, message: "2-64 [a-zA-Z0-9_-]" }]}
            >
              <Input addonAfter="/" placeholder="AAA" />
            </Form.Item>
            <Form.Item name="name" label={t("import.displayName")} rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="description" label={t("import.description")}>
              <Input.TextArea rows={2} placeholder={t("import.descPh")} />
            </Form.Item>
          </Form>
        </Card>

        <Card className="dx-card" title={t("import.metaTitle")}>
          <Form form={form} layout="vertical" disabled={step > 1}>
            <Form.Item name="data_type" label={t("import.dataType")}>
              <Select
                options={[
                  { value: "document", label: t("type.document") },
                  { value: "tabular", label: t("type.tabular") },
                  { value: "structure", label: t("type.structure") },
                  { value: "sequence", label: t("type.sequence") },
                  { value: "mixed", label: t("type.mixed") },
                ]}
              />
            </Form.Item>
            <Form.Item name="sensitivity" label={t("import.sensitivity")}>
              <Select
                options={["public", "internal", "confidential", "restricted"].map((v) => ({ value: v, label: t(`level.${v}`) }))}
              />
            </Form.Item>
            <Form.Item name="purpose" label={t("import.purpose")}>
              <Select options={["rag", "tool", "file"].map((v) => ({ value: v, label: t(`purpose.${v}`) }))} />
            </Form.Item>
            <Form.Item name="source" label={t("import.source")}>
              <Select
                options={[
                  { value: "upload", label: t("import.srcUpload") },
                  { value: "external", label: t("import.srcExternal") },
                  { value: "connector", label: t("import.srcConnector") },
                ]}
              />
            </Form.Item>
          </Form>

          <Alert type="warning" showIcon message={t("import.confidentialNote")} description={t("import.confidentialDesc")} />
        </Card>
      </div>

      <div className="section btn-row">
        {step < 2 && (
          <Button type="primary" loading={busy} onClick={submit}>
            {t("import.create")}
          </Button>
        )}
        {created && step === 2 && (
          <>
            <Button type="primary" loading={busy} onClick={index}>
              {t("import.indexNow")}
            </Button>
            <Button onClick={() => navigate(`/catalog/${created}`)}>{t("import.viewDir")}</Button>
          </>
        )}
      </div>

      {created && (
        <div className="section panel">
          <div className="panel-title">{t("import.next")}</div>
          <Text type="secondary">
            {t("import.nextBody", { id: created, path: `~/discoveryx/data/datasets/${created}/` })}
          </Text>
        </div>
      )}
    </section>
  );
}
