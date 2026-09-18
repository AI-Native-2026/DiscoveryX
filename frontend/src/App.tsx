import { useEffect, useRef, useState } from "react";
import {
  ConfigProvider,
  Select,
  Tooltip,
  Badge,
  Input,
  Typography,
  Dropdown,
  Modal,
  Form,
  Button,
  Alert,
  message,
  theme as antdTheme,
} from "antd";
import {
  HomeOutlined,
  ExperimentOutlined,
  BookOutlined,
  SafetyOutlined,
  DatabaseOutlined,
  DashboardOutlined,
  ThunderboltFilled,
  UserOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  AimOutlined,
  NodeIndexOutlined,
  MedicineBoxOutlined,
  BarChartOutlined,
  FileTextOutlined,
  UnorderedListOutlined,
  ImportOutlined,
  SearchOutlined,
  BulbOutlined,
  BulbFilled,
  TranslationOutlined,
} from "@ant-design/icons";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, setPrincipal } from "./api/client";
import { TaskProvider } from "./state/taskContext";
import { ProjectProvider, useProject } from "./state/projectContext";
import { useI18n } from "./i18n";
import Copilot from "./components/Copilot";
import Overview from "./pages/Overview";
import TargetIntel from "./pages/TargetIntel";
import Design from "./pages/Design";
import Make from "./pages/Make";
import Test from "./pages/Test";
import Analyze from "./pages/Analyze";
import Report from "./pages/Report";
import Tasks from "./pages/Tasks";
import TaskDetail from "./pages/TaskDetail";
import Catalog from "./pages/Catalog";
import DatasetDetail from "./pages/DatasetDetail";
import Import from "./pages/Import";
import Knowledge from "./pages/Knowledge";
import Rag from "./pages/Rag";
import Guardrails from "./pages/Guardrails";
import System from "./pages/System";

const ROLES = ["guest", "scientist", "engineer", "auditor", "admin"];

const NAV_GROUPS = [
  {
    labelKey: "nav.project",
    items: [
      { key: "/", icon: <HomeOutlined />, labelKey: "nav.overview" },
      { key: "/target", icon: <AimOutlined />, labelKey: "nav.target" },
      { key: "/design", icon: <ExperimentOutlined />, labelKey: "nav.design" },
      { key: "/make", icon: <NodeIndexOutlined />, labelKey: "nav.make" },
      { key: "/test", icon: <MedicineBoxOutlined />, labelKey: "nav.test" },
      { key: "/analyze", icon: <BarChartOutlined />, labelKey: "nav.analyze" },
      { key: "/report", icon: <FileTextOutlined />, labelKey: "nav.report" },
    ],
  },
  {
    labelKey: "nav.run",
    items: [{ key: "/tasks", icon: <UnorderedListOutlined />, labelKey: "nav.tasks" }],
  },
  {
    labelKey: "nav.data",
    items: [
      { key: "/catalog", icon: <DatabaseOutlined />, labelKey: "nav.catalog" },
      { key: "/import", icon: <ImportOutlined />, labelKey: "nav.import" },
      { key: "/knowledge", icon: <BookOutlined />, labelKey: "nav.knowledge" },
    ],
  },
  {
    labelKey: "nav.ops",
    items: [
      { key: "/guardrails", icon: <SafetyOutlined />, labelKey: "nav.guardrails" },
      { key: "/system", icon: <DashboardOutlined />, labelKey: "nav.system" },
    ],
  },
];

function Shell({ themeMode, onToggleTheme }: { themeMode: "dark" | "light"; onToggleTheme: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { t, lang, toggle } = useI18n();

  const [role, setRole] = useState("scientist");
  const [health, setHealth] = useState<string>("checking");
  const [pendingApprovals, setPendingApprovals] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [copilotCollapsed, setCopilotCollapsed] = useState(false);
  const [sidebarW, setSidebarW] = useState(232);
  const [copilotW, setCopilotW] = useState(336);
  const [search, setSearch] = useState("");
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [projectForm] = Form.useForm();
  const { projects, activeProject, setActiveProject, refresh: refreshProjects } = useProject();
  const drag = useRef<{ side: "left" | "right"; x: number } | null>(null);

  useEffect(() => {
    setPrincipal({ role, user: role === "guest" ? "anonymous" : role });
  }, [role]);

  useEffect(() => {
    let alive = true;
    const check = () => {
      api
        .health()
        .then((h) => alive && setHealth(h.status === "ok" ? "online" : h.status))
        .catch(() => alive && setHealth("offline"));
      api
        .listApprovals("pending")
        .then((r) => alive && setPendingApprovals(r.pending))
        .catch(() => alive && setPendingApprovals(0));
    };
    check();
    const timer = setInterval(check, 10000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [role]);

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--sidebar-w", (sidebarCollapsed ? 58 : sidebarW) + "px");
    root.style.setProperty("--copilot-w", (copilotCollapsed ? 0 : copilotW) + "px");
  }, [sidebarCollapsed, sidebarW, copilotCollapsed, copilotW]);

  const onMouseDown = (side: "left" | "right") => (e: React.MouseEvent) => {
    drag.current = { side, x: e.clientX };
    document.body.classList.add("resizing");
    e.preventDefault();
  };

  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!drag.current) return;
      const dx = e.clientX - drag.current.x;
      drag.current.x = e.clientX;
      if (drag.current.side === "left") setSidebarW((w) => Math.max(176, Math.min(340, w + dx)));
      else setCopilotW((w) => Math.max(280, Math.min(520, w - dx)));
    };
    const up = () => {
      drag.current = null;
      document.body.classList.remove("resizing");
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, []);

  const selected =
    NAV_GROUPS.flatMap((g) => g.items).find((m) => m.key !== "/" && location.pathname.startsWith(m.key))?.key ?? "/";

  const healthText = health === "online" ? t("status.online") : health === "checking" ? t("status.checking") : t("status.offline");

  return (
    <div className="app-shell">
      <header className="topbar glass">
        <div className="topbar-left">
          <button
            className={`panel-toggle ${sidebarCollapsed ? "" : "active"}`}
            onClick={() => setSidebarCollapsed((v) => !v)}
            aria-label={t("nav.collapse")}
          >
            {sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>
          <div className="brand">
            <div className="brand-mark">
              <ThunderboltFilled />
            </div>
            <div>
              <div className="brand-name">{t("app.name")}</div>
              <div className="brand-sub">{t("app.sub")}</div>
            </div>
          </div>
        </div>

        <label className="search">
          <SearchOutlined />
          <Input
            variant="borderless"
            placeholder={t("common.search")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onPressEnter={() => {
              if (search.trim()) navigate(`/rag?q=${encodeURIComponent(search.trim())}`);
            }}
          />
          <kbd>/</kbd>
        </label>

        <div className="topbar-right">
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                ...projects.map((p) => ({
                  key: p.id,
                  label: (
                    <div style={{ minWidth: 200 }}>
                      <div style={{ fontWeight: 550 }}>{p.name}</div>
                      <div style={{ fontSize: 11, color: "#8b98ad" }}>
                        {p.target} · {p.pdb_id}
                      </div>
                    </div>
                  ),
                })),
                { type: "divider" as const },
                { key: "__new__", label: t("project.new") },
              ],
              onClick: ({ key }) => {
                if (key === "__new__") {
                  projectForm.resetFields();
                  setNewProjectOpen(true);
                  return;
                }
                const p = projects.find((x) => x.id === key);
                if (p) {
                  setActiveProject(p);
                  message.success(t("project.switched", { name: p.name }));
                }
              },
            }}
          >
            <button className="project-btn">
              <span className="dot" />
              {activeProject?.name ?? t("project.select")}
              <span className="caret">▾</span>
            </button>
          </Dropdown>

          <button className="icon-btn" onClick={toggle} title={t("common.language")} aria-label={t("common.language")}>
            <TranslationOutlined />
            <span className="lang-tag">{lang === "zh" ? "中" : "EN"}</span>
          </button>
          <button className="icon-btn" onClick={onToggleTheme} title={t("common.theme")} aria-label={t("common.theme")}>
            {themeMode === "dark" ? <BulbOutlined /> : <BulbFilled />}
          </button>
          <div className="segmented">
            <Select
              size="small"
              variant="borderless"
              value={role}
              onChange={setRole}
              options={ROLES.map((r) => ({ value: r, label: `role: ${r}` }))}
              style={{ width: 140 }}
            />
          </div>
          <Tooltip title={`API: ${healthText}`}>
            <Badge status={health === "online" ? "success" : health === "checking" ? "processing" : "error"} />
          </Tooltip>
          <button
            className={`panel-toggle ${copilotCollapsed ? "" : "active"}`}
            onClick={() => setCopilotCollapsed((v) => !v)}
            aria-label="Copilot"
          >
            <ExperimentOutlined />
          </button>
          <div className="avatar" title={t("app.name")}>
            <UserOutlined />
          </div>
        </div>
      </header>

      <div className="app-body">
        <aside className={`sidebar glass ${sidebarCollapsed ? "collapsed" : ""}`}>
          <div className="sidebar-scroll">
            {NAV_GROUPS.map((g) => (
              <div key={g.labelKey}>
                <div className="nav-group-label">{t(g.labelKey)}</div>
                <nav className="nav">
                  {g.items.map((n) => (
                    <div
                      key={n.key}
                      className={`nav-item ${selected === n.key ? "active" : ""}`}
                      role="button"
                      tabIndex={0}
                      title={t(n.labelKey)}
                      onClick={() => navigate(n.key)}
                      onKeyDown={(e) => e.key === "Enter" && navigate(n.key)}
                    >
                      {n.icon}
                      <span className="ni-label">{t(n.labelKey)}</span>
                      {n.key === "/guardrails" && pendingApprovals > 0 && (
                        <span className="nav-badge">{pendingApprovals}</span>
                      )}
                    </div>
                  ))}
                </nav>
                <div className="divider" />
              </div>
            ))}
          </div>
          <div className="sidebar-foot">
            <button className="sf-btn" onClick={() => setSidebarCollapsed((v) => !v)} aria-label={t("nav.collapse")}>
              {sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              <span className="sf-label">{t("nav.collapse")}</span>
            </button>
          </div>
        </aside>

        <div className="resizer resizer-left" onMouseDown={onMouseDown("left")} />

        <main className="main" tabIndex={-1}>
          {projects.length === 0 && (
            <Alert
              style={{ marginBottom: 16 }}
              type="info"
              showIcon
              message={t("project.none")}
              description={t("project.noneDesc")}
              action={
                <Button
                  type="primary"
                  onClick={() => {
                    projectForm.resetFields();
                    setNewProjectOpen(true);
                  }}
                >
                  {t("project.new")}
                </Button>
              }
            />
          )}
          <Routes>
            <Route path="/" element={<Overview key={role} />} />
            <Route path="/target" element={<TargetIntel key={role} />} />
            <Route path="/design" element={<Design key={role} />} />
            <Route path="/make" element={<Make key={role} />} />
            <Route path="/test" element={<Test key={role} />} />
            <Route path="/analyze" element={<Analyze key={role} />} />
            <Route path="/report" element={<Report key={role} />} />
            <Route path="/tasks" element={<Tasks key={role} />} />
            <Route path="/tasks/:id" element={<TaskDetail key={role} />} />
            <Route path="/catalog" element={<Catalog key={role} />} />
            <Route path="/catalog/:id" element={<DatasetDetail key={role} />} />
            <Route path="/import" element={<Import key={role} />} />
            <Route path="/knowledge" element={<Knowledge key={role} />} />
            <Route path="/rag" element={<Rag key={role} />} />
            <Route path="/guardrails" element={<Guardrails key={role} />} />
            <Route path="/system" element={<System key={role} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        <div className="resizer resizer-right" onMouseDown={onMouseDown("right")} />

        <aside className={`copilot glass ${copilotCollapsed ? "collapsed" : ""}`}>
          <Copilot />
        </aside>
      </div>

      <footer className="app-footer">
        <span>{t("app.footer")}</span>
        <span>{t("app.footerMeta", { role, api: api.base })}</span>
      </footer>

      <Modal
        title={t("project.new")}
        open={newProjectOpen}
        onCancel={() => setNewProjectOpen(false)}
        okText={t("common.create")}
        cancelText={t("common.cancel")}
        onOk={async () => {
          try {
            const v = await projectForm.validateFields();
            const created = await api.createProject({
              name: v.name,
              description: v.description ?? "",
              target: v.target,
              pdb_id: v.pdb_id ?? "4WY1",
              objectives: v.objectives ?? ["BBB", "hepatotoxicity"],
            });
            refreshProjects();
            setActiveProject(created);
            setNewProjectOpen(false);
            message.success(t("project.created", { name: created.name }));
          } catch (e) {
            if ((e as { errorFields?: unknown }).errorFields) return;
            message.error((e as Error).message);
          }
        }}
      >
        <Form
          form={projectForm}
          layout="vertical"
          initialValues={{ target: "", pdb_id: "", objectives: ["hepatotoxicity", "solubility"] }}
        >
          <Form.Item name="name" label={t("project.name")} rules={[{ required: true, min: 2 }]}>
            <Input placeholder={t("project.namePh")} />
          </Form.Item>
          <Form.Item name="description" label={t("project.description")}>
            <Input.TextArea rows={2} placeholder={t("project.descPh")} />
          </Form.Item>
          <Form.Item name="target" label={t("project.target")} rules={[{ required: true }]}>
            <Input placeholder={t("project.targetPh")} />
          </Form.Item>
          <Form.Item name="pdb_id" label={t("project.pdb")}>
            <Input placeholder={t("project.pdbPh")} />
          </Form.Item>
          <Form.Item name="objectives" label={t("project.objectives")}>
            <Select
              mode="multiple"
              options={[
                { value: "BBB", label: t("obj.BBB") },
                { value: "hepatotoxicity", label: t("obj.hepatotoxicity") },
                { value: "solubility", label: t("obj.solubility") },
                { value: "potency", label: t("obj.potency") },
                { value: "selectivity", label: t("obj.selectivity") },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default function App() {
  const [themeMode, setThemeMode] = useState<"dark" | "light">("dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", themeMode);
  }, [themeMode]);

  return (
    <ConfigProvider
      theme={{
        algorithm: themeMode === "dark" ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: "#3dd6c4",
          colorInfo: "#5b8cff",
          borderRadius: 10,
          colorBgLayout: "transparent",
          colorBgContainer: themeMode === "dark" ? "#121a29" : "#ffffff",
          colorBgElevated: themeMode === "dark" ? "#162033" : "#ffffff",
          colorBorder: themeMode === "dark" ? "rgba(255,255,255,0.12)" : "rgba(16,30,60,0.14)",
          fontFamily:
            "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', sans-serif",
        },
        components: {
          Table: {
            headerBg: "transparent",
            colorBgContainer: "transparent",
            rowHoverBg: themeMode === "dark" ? "rgba(255,255,255,0.03)" : "rgba(16,30,60,0.03)",
          },
          Card: { colorBgContainer: themeMode === "dark" ? "#121a29" : "#ffffff" },
        },
      }}
    >
      <TaskProvider>
        <ProjectProvider>
          <Shell themeMode={themeMode} onToggleTheme={() => setThemeMode((m) => (m === "dark" ? "light" : "dark"))} />
        </ProjectProvider>
      </TaskProvider>
    </ConfigProvider>
  );
}
