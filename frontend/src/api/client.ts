/** Thin API client. All calls carry the current role/user so RBAC is exercised. */

import type {
  ApprovalOut,
  AuditEvent,
  CopilotMessage,
  CopilotReply,
  DLPDemoResponse,
  DatasetFileList,
  DatasetInfo,
  HealthResponse,
  RAGResult,
  TaskRequest,
  TaskResponse,
  TaskState,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export interface Principal {
  role: string;
  user: string;
}

let current: Principal = { role: "scientist", user: "alice" };

export function setPrincipal(p: Principal) {
  current = p;
}
export function getPrincipal(): Principal {
  return current;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: Record<string, unknown>;
  constructor(status: number, message: string, code?: string, details?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Role": current.role,
    "X-User": current.user,
    ...(init?.headers as Record<string, string> | undefined),
  };
  const resp = await fetch(`${API_BASE}/api/v1${path}`, { ...init, headers });
  const text = await resp.text();
  const body = text ? JSON.parse(text) : {};
  if (!resp.ok) {
    throw new ApiError(resp.status, body?.message ?? resp.statusText, body?.error, body?.details);
  }
  return body as T;
}

async function requestText(path: string): Promise<string> {
  const resp = await fetch(`${API_BASE}/api/v1${path}`, {
    headers: { "X-Role": current.role, "X-User": current.user },
  });
  if (!resp.ok) throw new ApiError(resp.status, resp.statusText);
  return resp.text();
}

export const api = {
  base: API_BASE,

  health: () => request<HealthResponse>("/health"),

  // projects
  listProjects: () => request<{ items: ProjectOut[]; total: number }>("/projects"),
  createProject: (payload: {
    name: string;
    description?: string;
    target?: string;
    pdb_id?: string;
    objectives?: string[];
    id?: string;
  }) => request<ProjectOut>("/projects", { method: "POST", body: JSON.stringify(payload) }),

  // tasks
  createTask: (payload: TaskRequest) =>
    request<TaskResponse>("/tasks", { method: "POST", body: JSON.stringify(payload) }),
  listTasks: (project?: string | null) =>
    request<TaskState[]>(`/tasks?limit=30${project ? `&project=${encodeURIComponent(project)}` : ""}`),
  getTask: (id: string) => request<TaskState>(`/tasks/${id}`),
  taskReportHtml: (id: string) => requestText(`/tasks/${id}/report`),

  // rag
  ragQuery: (query: string, top_k = 5) =>
    request<RAGResult>("/rag/query", { method: "POST", body: JSON.stringify({ query, top_k }) }),
  ragStatus: () =>
    request<{ collections: { collection: string; chunks: number }[]; total_chunks: number; embedding_model: string }>(
      "/rag/status",
    ),

  // datasets
  listDatasets: () => request<{ items: DatasetInfo[]; total: number }>("/datasets"),
  createDataset: (payload: {
    id: string;
    name: string;
    data_type: string;
    source: string;
    sensitivity: string;
    purpose: string;
    description?: string;
  }) => request<DatasetInfo>("/datasets", { method: "POST", body: JSON.stringify(payload) }),
  getDataset: (id: string) => request<DatasetInfo>(`/datasets/${id}`),
  datasetFiles: (id: string, limit = 200) => request<DatasetFileList>(`/datasets/${id}/files?limit=${limit}`),
  uploadDatasetFiles: async (id: string, files: File[], subdir = "") => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    form.append("subdir", subdir);
    const resp = await fetch(`${API_BASE}/api/v1/datasets/${id}/upload`, {
      method: "POST",
      headers: { "X-Role": current.role, "X-User": current.user },
      body: form,
    });
    const text = await resp.text();
    const body = text ? JSON.parse(text) : {};
    if (!resp.ok) throw new ApiError(resp.status, body?.message ?? resp.statusText, body?.error, body?.details);
    return body as { dataset_id: string; uploaded: number; files: { file: string; bytes: number }[] };
  },
  indexDataset: (id: string) =>
    request<{ dataset_id: string; documents: number; chunks: number; collection: string; task_id: string }>(
      `/datasets/${id}/index`,
      { method: "POST" },
    ),
  deleteDataset: (id: string) =>
    request<{ dataset_id: string; files_removed: boolean; collection_removed: string | null }>(
      `/datasets/${id}`,
      { method: "DELETE" },
    ),

  // copilot
  copilotChat: (message: string, task_id?: string | null, history: CopilotMessage[] = []) =>
    request<CopilotReply>("/copilot/chat", {
      method: "POST",
      body: JSON.stringify({ message, task_id: task_id ?? null, history }),
    }),

  // approvals
  listApprovals: (status?: string) =>
    request<{ items: ApprovalOut[]; total: number; pending: number }>(
      `/approvals${status ? `?status=${status}` : ""}`,
    ),
  decideApproval: (id: string, decision: "approved" | "rejected", comment?: string) =>
    request<ApprovalOut>(`/approvals/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, comment: comment ?? null }),
    }),

  // guardrails
  listAudit: (limit = 50) => request<{ items: AuditEvent[]; total: number }>(`/guardrails/events?limit=${limit}`),
  policy: () => request<{ default_role: string; roles: Record<string, unknown>; dlp_rules: unknown[] }>(
    "/guardrails/policy",
  ),
  dlpCheck: (text: string) =>
    request<DLPDemoResponse>("/guardrails/dlp-check", { method: "POST", body: JSON.stringify({ text }) }),
};
