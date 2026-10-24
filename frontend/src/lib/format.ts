import type {
  CaseCategory,
  DataSource,
  DefectCode,
  DefectLevel,
  FaultKind,
  GateLayer,
  Quality,
  RegressionKind,
  RunStatus,
  TimelineState,
  TraceEventKind,
} from "../types";

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(digits);
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat("zh-CN", {
    notation: value >= 10000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatSeconds(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(digits)} s`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

export function formatUnit(unit: string | null | undefined): string {
  if (!unit) {
    return "";
  }
  const normalized: Record<string, string> = {
    degC: "°C",
    "t/h": "t/h",
    MPa: "MPa",
    "%": "%",
    kPa: "kPa",
    bar: "bar",
    "m3/h": "m³/h",
  };
  return normalized[unit] ?? unit;
}

export function formatValueUnit(value: number | null | undefined, unit: string | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${formatNumber(value, Math.abs(value) < 10 ? 2 : 1)} ${formatUnit(unit)}`.trim();
}

export function shortHash(hash: string | null | undefined, length = 12): string {
  if (!hash) {
    return "—";
  }
  return hash.length > length ? hash.slice(0, length) : hash;
}

export const caseCategoryLabels: Record<CaseCategory, string> = {
  steady: "稳态",
  fault: "故障",
  boundary: "边界",
  interlock: "联锁闭环",
};

export const dataSourceLabels: Record<DataSource, string> = {
  real_history: "真实历史",
  simulation: "仿真",
  mechanistic: "机理构造",
};

export const faultLabels: Record<FaultKind, string> = {
  super_temperature: "超温",
  over_pressure: "超压",
  sensor_drift: "仪表漂移",
  valve_sticking: "阀门卡涩",
  sensor_disconnect: "传感器断线",
  network_jitter: "网络抖动",
};

export const qualityLabels: Record<Quality, string> = {
  good: "良好",
  uncertain: "可疑",
  bad: "坏质量",
};

export const defectLevelLabels: Record<DefectLevel, string> = {
  P0: "P0 阻断",
  P1: "P1 风险",
  P2: "P2 观察",
};

export const defectCodeLabels: Record<DefectCode, string> = {
  missed_fault: "故障漏报",
  false_alarm: "误报",
  high_risk_false_alarm: "高风险期误报",
  wrong_fault_type: "故障类型错误",
  wrong_target: "目标位号错误",
  detection_latency: "检测时延超限",
  mechanism_rejected: "机理校验失败",
  unsafe_setpoint: "越安全边界设定值",
  outside_recommended: "偏离推荐区间",
  unauthorized_command: "越权控制",
  retry_after_denial: "被拒后重试",
  missing_confirmation: "缺少人工确认",
  interlock_missed: "联锁应触发未触发",
  interlock_false_trip: "联锁误动作",
  degradation_missing: "缺少安全降级",
  control_on_invalid_data: "坏数据上仍控制",
  non_reproducible: "不可复现",
  invalid_injection: "注入无效",
  action_trace_mismatch: "动作轨迹不符",
  artifact_missing: "证据缺失",
  boundary_risk_missed: "边界风险漏判",
};

export const controlKindLabels = {
  set_setpoint: "写设定值",
  request_maintenance: "请求维护",
  request_manual_takeover: "请求人工接管",
  request_bypass_interlock: "请求旁路联锁",
} as const;

export const timelineStateLabels: Record<TimelineState, string> = {
  steady: "稳态",
  fault: "故障",
  observe: "观察",
  recovery: "恢复",
};

export const traceEventLabels: Record<TraceEventKind, string> = {
  AGENT_SUGGESTION: "Agent 建议",
  GATE_ALLOWED: "门禁放行",
  GATE_BLOCKED: "门禁阻断",
  CONFIRMATION_REQUIRED: "请求人工确认",
  CONFIRMATION_GRANTED: "人工确认",
  DCS_WRITE: "DCS 写入",
  SIS_TRIGGERED: "SIS 联锁动作",
  SIS_BLOCKED: "SIS 阻断",
  DEGRADED_MODE: "安全降级",
  RETRY_BLOCKED: "重试被阻断",
};

export const gateLayerLabels: Record<GateLayer, string> = {
  none: "无",
  permission: "权限层",
  process_guard: "工艺边界层",
  confirmation: "人工确认层",
  interlock: "联锁层",
  sis: "SIS 层",
};

export const runStatusLabels: Record<RunStatus, string> = {
  queued: "排队中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

export const regressionKindLabels: Record<RegressionKind, string> = {
  severe_regression: "严重回归",
  unexpected_change: "非预期变化",
  improvement: "改进",
  unchanged: "未变化",
};

export const actionLabels = {
  trip_reactor_feed: "切断反应进料",
  open_pressure_relief: "开启泄压",
} as const;

export function levelRank(level: DefectLevel): number {
  return level === "P0" ? 0 : level === "P1" ? 1 : 2;
}

export function defectSort<T extends { level: DefectLevel }>(items: T[]): T[] {
  return [...items].sort((a, b) => levelRank(a.level) - levelRank(b.level));
}
