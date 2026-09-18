/** TypeScript types mirroring the backend Pydantic schemas. */

export type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "blocked";
export type Sensitivity = "public" | "internal" | "confidential" | "restricted";

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  calls: number;
  cost_usd: number;
}

export interface TaskRequest {
  hypothesis: string;
  target?: string;
  pdb_id?: string;
  rounds?: number;
  objectives?: string[];
  project?: string;
  sensitivity?: Sensitivity;
  dataset_id?: string | null;
  activity_model?: "qsar" | "knn";
  smiles_column?: string | null;
  activity_column?: string | null;
}

export interface TaskResponse {
  task_id: string;
  status: TaskStatus;
  created_at: string;
  trace_id?: string | null;
}

export interface TaskEvent {
  ts?: string;
  stage: string;
  round?: number;
  message: string;
  [k: string]: unknown;
}

export interface TaskState {
  task_id: string;
  project?: string | null;
  dataset_id?: string | null;
  target?: string | null;
  objectives?: string[];
  status: TaskStatus;
  stage: string;
  round: number;
  rounds: number;
  progress: number;
  trace_id?: string | null;
  attempts?: number;
  created_at: string;
  updated_at: string;
  error?: string | null;
  token_usage: TokenUsage;
  result?: DMTAReport | null;
  events: TaskEvent[];
}

export interface Candidate {
  id: number;
  smiles: string;
  pIC50?: number | null;
  bbb?: boolean | null;
  hepatotoxic?: boolean | null;
  solubility?: number | null;
  herg?: number | null;
  sa_score?: number | null;
  qed?: number | null;
  rationale?: string | null;
  route_steps?: number | null;
  route_available?: boolean | null;
  mpo?: number | null;
}

export interface DMTARound {
  round: number;
  passed: number;
  summary: string;
  decision: string;
  action?: string;
  directives?: string[];
  directive_labels?: string[];
  narrative?: string;
}

export interface DMTAReport {
  task_id: string;
  target: string;
  hypothesis: string;
  target_summary?: string;
  objectives?: string[];
  rounds: DMTARound[];
  top_candidates: Candidate[];
  decision: string;
  evidence: { type: string; id: string; title?: string; score?: number; resolution?: string }[];
  token_usage: TokenUsage;
  generated_at: string;
  dataset?: Record<string, unknown>;
  activity_model?: Record<string, unknown>;
  admet_engine?: string | null;
}

export interface Citation {
  id: string;
  title: string;
  source: string;
  sensitivity: string;
  score: number;
  snippet: string;
}

export interface RAGResult {
  query: string;
  answer: string;
  citations: Citation[];
  used_chunks: number;
  blocked_chunks: number;
  token_usage?: TokenUsage;
}

export interface DatasetInfo {
  id: string;
  name: string;
  data_type: string;
  source: string;
  sensitivity: Sensitivity;
  purpose: string;
  scale: string;
  status: string;
  rag_indexed: boolean;
  path?: string | null;
  owner: string;
  updated_at: string;
  meta: Record<string, unknown>;
  is_directory: boolean;
  n_files: number;
  size_bytes: number;
  file_types: Record<string, number>;
}

export interface DatasetFile {
  name: string;
  rel_path: string;
  ext: string;
  size_bytes: number;
  modified_at: string;
}

export interface DatasetFileList {
  dataset_id: string;
  items: DatasetFile[];
  total: number;
  file_types: Record<string, number>;
}

export interface CopilotStep {
  tool: string;
  detail: string;
  status: string;
}

export interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CopilotReply {
  answer: string;
  citations: Citation[];
  steps: CopilotStep[];
  token_usage: TokenUsage;
  blocked: boolean;
}

export interface ProjectOut {
  id: string;
  name: string;
  description: string;
  target: string;
  pdb_id: string;
  objectives: string[];
  created_by: string;
  created_at: string;
}

export interface ApprovalOut {
  id: string;
  task_id: string;
  kind: string;
  title: string;
  detail: string;
  payload: Record<string, unknown>;
  status: "pending" | "approved" | "rejected";
  requested_by: string;
  requested_at: string;
  decided_by?: string | null;
  decided_at?: string | null;
  comment?: string | null;
}

export interface AuditEvent {
  ts: string;
  trace_id: string;
  actor: string;
  role: string;
  action: string;
  resource: string;
  decision: "ALLOW" | "BLOCKED" | "MASKED";
  reason: string;
  details: Record<string, unknown>;
}

export interface DLPDemoResponse {
  action: "ALLOW" | "MASK" | "BLOCK";
  findings: { rule: string; description: string; action: string; match: string }[];
  masked_text?: string | null;
  blocked: boolean;
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  environment: string;
  components: Record<string, string>;
}
