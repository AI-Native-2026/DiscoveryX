import { useEffect, useMemo, useState } from "react";
import { Card, Table, Tag, Typography, Button, Space, Form, Input, Select, Row, Col, message, Alert, Tooltip } from "antd";
import { PlusOutlined, ReloadOutlined, CheckCircleFilled, WarningFilled } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useProject } from "../state/projectContext";
import { useI18n } from "../i18n";
import type { DatasetInfo, TaskState } from "../api/types";

const { Title, Paragraph, Text } = Typography;

interface CompoundInfo {
  smiles_column?: string;
  activity_column?: string;
  activity_kind?: string;
  usable_for_dmta?: boolean;
  reason?: string;
  file?: string;
}

export default function Tasks() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [form] = Form.useForm();
  const { activeProject } = useProject();
  const [tasks, setTasks] = useState<TaskState[]>([]);
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const compoundOf = (d: DatasetInfo): CompoundInfo => ((d.meta?.compound as CompoundInfo) ?? {});

  const load = () => {
    api.listTasks(activeProject?.id).then(setTasks).catch(() => setTasks([]));
    api.listDatasets().then((r) => setDatasets(r.items)).catch(() => setDatasets([]));
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  const compoundDatasets = useMemo(
    () => datasets.filter((d) => Object.keys(compoundOf(d)).length > 0),
    [datasets],
  );

  const datasetOptions = [
    { value: "", label: t("tasks.builtinDataset") },
    ...compoundDatasets.map((d) => {
      const c = compoundOf(d);
      return {
        value: d.id,
        label: `${c.usable_for_dmta ? "✓" : "✗"} ${d.name} (${d.id})${c.activity_column ? ` · ${c.activity_column}` : ""}`,
      };
    }),
  ];

  const submit = async () => {
    const values = await form.validateFields();
    setLoading(true);
    setError(null);
    try {
      const res = await api.createTask({
        hypothesis: values.hypothesis,
        target: values.target,
        pdb_id: values.pdb_id,
        rounds: values.rounds,
        objectives: values.objectives,
        project: activeProject?.id,
        dataset_id: values.dataset_id || null,
        activity_model: values.activity_model,
      });
      message.success(t("tasks.submitted", { id: res.task_id }));
      navigate(`/tasks/${res.task_id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setError(t("tasks.guardrail", { msg: e.message }));
      else if (e instanceof ApiError && e.status === 422) setError(t("tasks.datasetInvalid", { msg: e.message }));
      else setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const selected = Form.useWatch("dataset_id", form);
  const selectedDataset = compoundDatasets.find((d) => d.id === selected);

  return (
    <div>
      <Paragraph className="dx-eyebrow">{t("tasks.eyebrow")}</Paragraph>
      <Title className="dx-h1">{t("tasks.title")}</Title>
      <Paragraph className="dx-lede">{t("tasks.lede")}</Paragraph>

      {error && <Alert style={{ marginTop: 16 }} type="error" showIcon message={error} />}

      <div className="dx-section">
        <Card className="dx-card" title={t("tasks.new")}>
          <Form
            form={form}
            layout="vertical"
            initialValues={{
              target: activeProject?.target ?? "",
              pdb_id: activeProject?.pdb_id ?? "",
              rounds: 3,
              objectives: activeProject?.objectives ?? ["hepatotoxicity", "solubility"],
              dataset_id: "",
              activity_model: "qsar",
              hypothesis: activeProject?.description ?? "",
            }}
          >
            <Form.Item name="hypothesis" label={t("tasks.hypothesis")} rules={[{ required: true, min: 8 }]}>
              <Input.TextArea rows={2} />
            </Form.Item>

            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item name="dataset_id" label={t("tasks.dataset")} extra={t("tasks.datasetExtra")}>
                  <Select options={datasetOptions} />
                </Form.Item>
              </Col>
              <Col xs={24} md={6}>
                <Form.Item name="activity_model" label={t("tasks.activityModel")}>
                  <Select
                    options={[
                      { value: "qsar", label: t("tasks.modelQsv") },
                      { value: "knn", label: t("tasks.modelKnn") },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={6}>
                <Form.Item name="rounds" label={t("tasks.rounds")} extra={t("tasks.roundsExtra")}>
                  <Select options={[1, 2, 3, 4, 5].map((n) => ({ value: n, label: t("tasks.roundsUnit", { n }) }))} />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col xs={24} md={6}>
                <Form.Item name="target" label={t("tasks.target")}>
                  <Input />
                </Form.Item>
              </Col>
              <Col xs={24} md={6}>
                <Form.Item name="pdb_id" label={t("tasks.pdb")}>
                  <Input />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item name="objectives" label={t("tasks.objectives")}>
                  <Select
                    mode="multiple"
                    options={["BBB", "hepatotoxicity", "solubility"].map((o) => ({ value: o, label: t(`obj.${o}`) }))}
                  />
                </Form.Item>
              </Col>
            </Row>

            {selected && selectedDataset && (
              <Alert
                style={{ marginBottom: 16 }}
                type={compoundOf(selectedDataset).usable_for_dmta ? "success" : "warning"}
                showIcon
                message={
                  compoundOf(selectedDataset).usable_for_dmta
                    ? t("tasks.usable", {
                        smiles: compoundOf(selectedDataset).smiles_column ?? "—",
                        activity: compoundOf(selectedDataset).activity_column ?? "—",
                        file: compoundOf(selectedDataset).file ?? "—",
                      })
                    : t("tasks.notUsable", { reason: compoundOf(selectedDataset).reason ?? "" })
                }
              />
            )}

            <Space>
              <Button type="primary" icon={<PlusOutlined />} loading={loading} onClick={submit}>
                {t("common.submit")}
              </Button>
              <Button icon={<ReloadOutlined />} onClick={() => form.resetFields()}>
                {t("common.reset")}
              </Button>
            </Space>
          </Form>
        </Card>
      </div>

      <div className="dx-section">
        <Card className="dx-card" title={t("tasks.available")} styles={{ body: { padding: 0 } }}>
          <Table<DatasetInfo>
            rowKey="id"
            dataSource={compoundDatasets}
            pagination={false}
            size="small"
            columns={[
              { title: t("tasks.datasetCol"), dataIndex: "name" },
              { title: "ID", dataIndex: "id", render: (v: string) => <Text className="dx-mono">{v}</Text> },
              {
                title: t("tasks.smilesCol"),
                render: (_, d) => <Text className="dx-mono">{compoundOf(d).smiles_column ?? "—"}</Text>,
              },
              {
                title: t("tasks.activityCol"),
                render: (_, d) => <Text className="dx-mono">{compoundOf(d).activity_column ?? "—"}</Text>,
              },
              {
                title: t("tasks.usableCol"),
                render: (_, d) => {
                  const c = compoundOf(d);
                  return (
                    <Tooltip title={c.reason}>
                      {c.usable_for_dmta ? (
                        <Tag color="success" icon={<CheckCircleFilled />}>
                          {t("tasks.usableYes")}
                        </Tag>
                      ) : (
                        <Tag color="warning" icon={<WarningFilled />}>
                          {t("tasks.usableNo")}
                        </Tag>
                      )}
                    </Tooltip>
                  );
                },
              },
            ]}
          />
        </Card>
      </div>

      <div className="dx-section">
        <Card className="dx-card" title={t("tasks.list")} styles={{ body: { padding: 0 } }}>
          <Table<TaskState>
            rowKey="task_id"
            dataSource={tasks}
            pagination={false}
            onRow={(r) => ({ onClick: () => navigate(`/tasks/${r.task_id}`), style: { cursor: "pointer" } })}
            columns={[
              { title: "Task ID", dataIndex: "task_id", render: (v: string) => <Text className="dx-mono">{v}</Text> },
              {
                title: t("th.status"),
                dataIndex: "status",
                render: (s: string) => (
                  <Tag color={s === "succeeded" ? "success" : s === "running" ? "processing" : s === "blocked" || s === "failed" ? "error" : "default"}>
                    {t(`status.${s}`)}
                  </Tag>
                ),
              },
              { title: t("stage.setup"), dataIndex: "stage" },
              { title: t("th.rounds"), render: (_, r) => `${r.round}/${r.rounds}` },
              {
                title: t("tasks.datasetCol"),
                render: (_, r) => <Text className="dx-mono">{r.dataset_id ?? "built-in"}</Text>,
              },
            ]}
          />
        </Card>
      </div>
    </div>
  );
}
