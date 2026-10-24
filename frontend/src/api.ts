import type {
  AgentMeta,
  BaselineDetail,
  BaselineSummary,
  CaseDetail,
  CaseMeta,
  Dashboard,
  GateDecision,
  InjectionDocument,
  Meta,
  RegressionReport,
  ResponseItem,
  ResponseSummary,
  RunRecord,
  RunSummary,
  SeriesResponse,
  SuiteMeta,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = `请求失败（HTTP ${response.status}）`;
    try {
      const body: unknown = await response.json();
      if (
        body &&
        typeof body === "object" &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        detail = body.detail;
      }
    } catch {
      // 非 JSON 错误体保留状态码文案。
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function queryString(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value));
    }
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export const API_ORIGIN = API_BASE;

export const api = {
  health: () =>
    request<{
      status: string;
      runs: number;
      auto_seed: boolean;
      domain: string;
      version: string;
    }>("/api/health"),

  meta: () => request<Meta>("/api/meta"),

  dashboard: () => request<Dashboard>("/api/dashboard"),

  cases: () => request<CaseMeta[]>("/api/cases"),

  agents: () => request<AgentMeta[]>("/api/agents"),

  suites: () => request<SuiteMeta[]>("/api/suites"),

  listRuns: (params: {
    limit?: number;
    offset?: number;
    suite_id?: string;
    agent_id?: string;
  } = {}) =>
    request<{
      items: RunSummary[];
      count: number;
      total: number;
      limit: number;
      offset: number;
    }>(`/api/runs${queryString(params)}`),

  getRun: (runId: string) => request<RunRecord>(`/api/runs/${encodeURIComponent(runId)}`),

  runSuite: (body: {
    suite_id: string;
    agent_ids?: string[] | null;
    name?: string | null;
    seed?: number | null;
    reproducibility_check?: boolean | null;
  }) =>
    request<{ items: RunSummary[]; count: number }>("/api/runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  runCase: (
    caseId: string,
    body: {
      agent_id: string;
      seed?: number | null;
      reproducibility_check?: boolean | null;
    },
  ) =>
    request<RunSummary>(`/api/runs/case/${encodeURIComponent(caseId)}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  caseDetail: (runId: string, caseId: string) =>
    request<CaseDetail>(
      `/api/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}`,
    ),

  series: (runId: string, caseId: string, tag: string, maxPoints = 900) =>
    request<SeriesResponse>(
      `/api/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/series` +
        queryString({ tag, max_points: maxPoints }),
    ),

  responses: (runId: string, caseId: string) =>
    request<{ items: ResponseSummary[]; count: number }>(
      `/api/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/responses`,
    ),

  response: (runId: string, caseId: string, index: number) =>
    request<ResponseItem>(
      `/api/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/responses/${index}`,
    ),

  artifactJson: <T>(runId: string, caseId: string, path: string) =>
    request<T>(
      `/api/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/artifact` +
        queryString({ path }),
    ),

  artifactText: async (runId: string, caseId: string, path: string): Promise<string> => {
    const response = await fetch(
      `${API_BASE}/api/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/artifact` +
        queryString({ path }),
    );
    if (!response.ok) {
      throw new ApiError(response.status, `证据文件读取失败（HTTP ${response.status}）`);
    }
    return await response.text();
  },

  artifactUrl: (runId: string, caseId: string, path: string) =>
    `${API_BASE}/api/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/artifact` +
    queryString({ path }),

  gateDecisions: (runId: string, caseId: string) =>
    api.artifactJson<GateDecision[]>(runId, caseId, "gate_decisions.json"),

  injection: (runId: string, caseId: string) =>
    api.artifactJson<InjectionDocument>(runId, caseId, "injection.json"),

  report: (runId: string) =>
    request<{ run_id: string; markdown: string; path: string; generated_at: string | null }>(
      `/api/runs/${encodeURIComponent(runId)}/report`,
    ),

  generateReport: (
    runId: string,
    body: { baseline_id?: string | null; regression_id?: string | null } = {},
  ) =>
    request<{ run_id: string; path: string; markdown: string }>(
      `/api/runs/${encodeURIComponent(runId)}/report`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  reportUrl: (runId: string) =>
    `${API_BASE}/api/runs/${encodeURIComponent(runId)}/report.md`,

  listBaselines: () => request<{ items: BaselineSummary[] }>("/api/baselines"),

  createBaseline: (body: { run_id: string; name?: string | null }) =>
    request<BaselineSummary>("/api/baselines", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  baseline: (baselineId: string) =>
    request<BaselineDetail>(`/api/baselines/${encodeURIComponent(baselineId)}`),

  listRegressions: () => request<{ items: RegressionReport[] }>("/api/regressions"),

  regression: (reportId: string) =>
    request<RegressionReport>(`/api/regressions/${encodeURIComponent(reportId)}`),

  createRegression: (body: { candidate_run_id: string; baseline_id?: string | null }) =>
    request<RegressionReport>("/api/regressions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
