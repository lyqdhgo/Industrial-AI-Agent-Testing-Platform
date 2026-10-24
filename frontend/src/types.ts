export type CaseCategory = "steady" | "fault" | "boundary" | "interlock";
export type DataSource = "real_history" | "simulation" | "mechanistic";
export type TimelineState = "steady" | "fault" | "observe" | "recovery";
export type FaultKind =
  | "super_temperature"
  | "over_pressure"
  | "sensor_drift"
  | "valve_sticking"
  | "sensor_disconnect"
  | "network_jitter";
export type Quality = "good" | "uncertain" | "bad";
export type RecommendationStatus = "normal" | "attention" | "anomaly" | "degraded";
export type ControlKind =
  | "set_setpoint"
  | "request_maintenance"
  | "request_manual_takeover"
  | "request_bypass_interlock";
export type GateLayer = "none" | "permission" | "process_guard" | "confirmation" | "interlock" | "sis";
export type DefectLevel = "P0" | "P1" | "P2";
export type DefectCode =
  | "missed_fault"
  | "false_alarm"
  | "high_risk_false_alarm"
  | "wrong_fault_type"
  | "wrong_target"
  | "detection_latency"
  | "mechanism_rejected"
  | "unsafe_setpoint"
  | "outside_recommended"
  | "unauthorized_command"
  | "retry_after_denial"
  | "missing_confirmation"
  | "interlock_missed"
  | "interlock_false_trip"
  | "degradation_missing"
  | "control_on_invalid_data"
  | "non_reproducible"
  | "invalid_injection"
  | "action_trace_mismatch"
  | "artifact_missing"
  | "boundary_risk_missed";
export type TraceEventKind =
  | "AGENT_SUGGESTION"
  | "GATE_ALLOWED"
  | "GATE_BLOCKED"
  | "CONFIRMATION_REQUIRED"
  | "CONFIRMATION_GRANTED"
  | "DCS_WRITE"
  | "SIS_TRIGGERED"
  | "SIS_BLOCKED"
  | "DEGRADED_MODE"
  | "RETRY_BLOCKED";
export type RunStatus = "queued" | "running" | "completed" | "failed";
export type RegressionKind = "severe_regression" | "unexpected_change" | "improvement" | "unchanged";
export type AdapterKind = "mock" | "http_json";
export type MockProfile = "reference" | "degraded" | "unsafe";
export type InterlockAction = "trip_reactor_feed" | "open_pressure_relief";
export type InterlockLayer = "sis" | "dcs" | "plc";

export interface PhysicalValue {
  value: number;
  unit: string;
}

export interface TaggedValue extends PhysicalValue {
  tag: string;
}

export interface LimitBand {
  low: number;
  high: number;
  unit: string;
}

export interface TripLimits {
  high: number | null;
  low: number | null;
  unit: string | null;
}

export interface SensorMeta {
  tag: string;
  name: string;
  kind: string;
  unit: string;
  range: LimitBand;
  sample_interval_s: number;
  safe_limits: LimitBand;
  recommended_band: LimitBand;
  trip_limits: TripLimits;
  mechanism_basis: string;
}

export interface InterlockMeta {
  id: string;
  tag: string;
  name: string;
  condition: string;
  trip_limit: TripLimits;
  action: InterlockAction;
  layer: InterlockLayer;
  bypassable: boolean;
  note: string;
}

export interface TimelineSegment {
  start_s: number;
  duration_s: number;
  state: TimelineState;
}

export interface FaultPlan {
  kind: FaultKind;
  target_tag: string;
  start_s: number;
  duration_s: number;
  params: Record<string, PhysicalValue>;
}

export interface OperatorProfile {
  available: boolean;
  operator_id: string;
  role: "operator" | "supervisor" | "engineer";
  confirm_high_risk: boolean;
  note: string;
}

export interface ExpectedBehavior {
  should_detect: boolean;
  fault_type: FaultKind | null;
  target_tag: string | null;
  max_latency_s: number | null;
  max_false_alarms: number;
  expect_attention: boolean;
  require_degraded_response: boolean;
  forbid_control_on_invalid_data: boolean;
  expected_action_trace: TraceEventKind[];
  expected_interlock_actions: InterlockAction[];
}

export interface CaseMeta {
  id: string;
  name: string;
  description: string;
  category: CaseCategory;
  source: DataSource;
  provenance: string;
  seed: number;
  duration_s: number;
  decision_interval_s: number;
  history_window_s: number;
  tags: string[];
  timeline: TimelineSegment[];
  initial_conditions: TaggedValue[];
  faults: FaultPlan[];
  expected: ExpectedBehavior;
  operator: OperatorProfile;
}

export interface AgentPermissions {
  allowed_tags: string[];
  high_risk_tags: string[];
  allowed_control_kinds: ControlKind[];
}

export interface AgentMeta {
  id: string;
  name: string;
  version: string;
  description: string;
  adapter: AdapterKind;
  mock_profile: MockProfile | null;
  endpoint: string | null;
  token_env: string | null;
  permissions: AgentPermissions;
  temperature: number;
  timeout_s: number;
  max_retries: number;
  retry_forbidden_actions: boolean;
  change_notes: string[];
}

export interface SuiteMeta {
  id: string;
  name: string;
  description: string;
  case_ids: string[];
  agent_ids: string[];
}

export interface DomainHashes {
  domain_hash: string;
  interlock_hash: string;
  case_set_hash: string;
}

export interface Meta {
  domain: {
    pack_id: string;
    asset_id: string;
    asset_name: string;
    disclaimer: string;
    provenance: DataSource;
    hashes: DomainHashes;
    assumptions: string[];
    timebase: {
      simulation_step_s: number;
      decision_interval_s: number;
      history_window_s: number;
    };
  };
  sensors: SensorMeta[];
  interlocks: InterlockMeta[];
  cases: CaseMeta[];
  agents: AgentMeta[];
  suites: SuiteMeta[];
  case_set_hash: string;
  platform_disclaimer: string;
}

export interface LatencyStats {
  p50_s: number | null;
  p90_s: number | null;
  p99_s: number | null;
  max_s: number | null;
  mean_s: number | null;
  sample_count: number;
}

export interface DatasetComposition {
  total_cases: number;
  steady_cases: number;
  fault_cases: number;
  boundary_cases: number;
  interlock_cases: number;
  fault_ratio: number;
  steady_ratio: number;
  boundary_ratio: number;
  interlock_ratio: number;
  imbalanced: boolean;
  warning: string | null;
}

export interface Metrics {
  total_cases: number;
  injected_faults: number;
  missed_faults: number;
  miss_rate: number;
  false_alarm_count: number;
  judgment_opportunities: number;
  false_alarm_rate: number;
  high_risk_false_alarms: number;
  detection_latency: LatencyStats;
  valid_setpoints: number;
  compliant_setpoints: number;
  setpoint_compliance_rate: number | null;
  unsafe_setpoint_events: number;
  unauthorized_attempts: number;
  interlock_expected: number;
  interlock_correct: number;
  interlock_missed: number;
  interlock_false_trips: number;
  interlock_trigger_accuracy: number | null;
  reproducibility_rate: number | null;
  reproducibility_verified: boolean;
  dataset: DatasetComposition;
  defects_p0: number;
  defects_p1: number;
  defects_p2: number;
  blocking: boolean;
}

export interface Defect {
  id: string;
  case_id: string;
  level: DefectLevel;
  code: DefectCode;
  title: string;
  expected: string;
  actual: string;
  occurred_at_s: number | null;
  evidence_paths: string[];
  mechanism_basis: string;
  repro_command: string;
  detail: string;
  risk_window: boolean;
}

export interface MechanismCheck {
  fault_type: FaultKind | null;
  target_tag: string | null;
  passed: boolean;
  check_name: string;
  detail: string;
  evidence: Record<string, number>;
}

export interface InterlockEvaluation {
  rule_id: string;
  action: InterlockAction;
  should_trigger: boolean;
  triggered: boolean;
  trigger_t_s: number | null;
  false_trip: boolean;
}

export interface CaseResult {
  case_id: string;
  case_name: string;
  category: CaseCategory;
  seed: number;
  detected: boolean;
  correct_type: boolean;
  target_correct: boolean;
  detection_t_s: number | null;
  latency_s: number | null;
  false_alarms: number;
  high_risk_false_alarms: number;
  judgment_opportunities: number;
  degraded_correct: boolean;
  valid_setpoints: number;
  compliant_setpoints: number;
  unsafe_setpoints: number;
  unauthorized_attempts: number;
  retries_after_denial: number;
  fingerprint: string;
  defects: Defect[];
  artifact_dir: string;
  mech_checks: MechanismCheck[];
  interlock_evaluations: InterlockEvaluation[];
  expected_action_trace: TraceEventKind[];
  actual_action_trace: TraceEventKind[];
  action_trace_match: boolean | null;
  duration_s: number;
  injection_valid: boolean;
  reproducible: boolean | null;
}

export interface RunRecord {
  id: string;
  name: string;
  suite_id: string;
  agent_id: string;
  agent_name: string;
  agent_version: string;
  seed: number;
  seed_set: number[];
  status: RunStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  case_ids: string[];
  case_results: CaseResult[];
  metrics: Metrics | null;
  domain_hashes: DomainHashes;
  report_markdown_path: string | null;
  reproducibility_unverified: boolean;
  error: string | null;
  case_meta: Record<string, CaseMeta | null>;
  report_available: boolean;
}

export interface CaseBrief {
  case_id: string;
  case_name: string;
  category: CaseCategory;
  detected: boolean;
  correct_type: boolean;
  latency_s: number | null;
  false_alarms: number;
  high_risk_false_alarms: number;
  unsafe_setpoints: number;
  unauthorized_attempts: number;
  p0: number;
  p1: number;
  fingerprint: string;
  reproducible: boolean | null;
  action_trace_match: boolean | null;
  artifact_dir: string;
}

export interface RunSummary {
  id: string;
  name: string;
  suite_id: string;
  agent_id: string;
  agent_name: string;
  agent_version: string;
  seed: number;
  seed_set: number[];
  status: RunStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  case_count: number;
  metrics: Metrics | null;
  cases: CaseBrief[];
  report_available: boolean;
  error: string | null;
  reproducibility_unverified: boolean;
  domain_hashes: DomainHashes;
}

export interface DefectDigest {
  case_id: string;
  case_name: string;
  code: DefectCode;
  title: string;
  occurred_at_s: number | null;
  detail: string;
  artifact_dir: string;
}

export interface BaselineSummary {
  id: string;
  name: string;
  run_id: string;
  agent_version: string;
  created_at: string;
  seed_set: number[];
  case_set_hash: string;
  domain_hash: string;
  interlock_hash: string;
  case_count: number;
  p0: number;
}

export interface BaselineDetail extends BaselineSummary {
  results: CaseResult[];
}

export interface RegressionRow {
  case_id: string;
  metric: string;
  baseline: string;
  current: string;
  kind: RegressionKind;
  level: DefectLevel | null;
  detail: string;
}

export interface RegressionReport {
  id: string;
  baseline_id: string;
  baseline_run_id: string;
  candidate_run_id: string;
  created_at: string;
  comparable: boolean;
  blockers: string[];
  severe_regressions: RegressionRow[];
  unexpected_changes: RegressionRow[];
  improvements: RegressionRow[];
  fingerprint_match_rate: number | null;
  hash_results: Record<string, { baseline: string; candidate: string }>;
  latency_ratio: number | null;
}

export interface Dashboard {
  runs: RunSummary[];
  latest_baseline: BaselineSummary | null;
  latest_regression: RegressionReport | null;
  hero_run: RunSummary | null;
  metrics: Metrics | null;
  p0_defects: DefectDigest[];
  p1_defects: DefectDigest[];
  catalog: {
    case_count: number;
    agent_count: number;
    suite_count: number;
    case_set_hash: string;
  };
  seed_running: boolean;
}

export interface SeriesPoint {
  t_s: number;
  true_value: number;
  measured_value: number | null;
  quality: Quality;
  delivered: boolean;
  command_value: number | null;
  received_s: number;
  unit: string;
}

export interface SeriesResponse {
  tag: string;
  unit: string;
  points: SeriesPoint[];
  total_before_downsample: number;
  downsampled: boolean;
  source: string;
}

export interface ResponseSummary {
  index: number;
  observed_at_s: number;
  observation_id: string;
  status: RecommendationStatus | null;
  fault_type: FaultKind | null;
  target_tag: string | null;
  confidence: number | null;
  rationale_text: string | null;
  degraded_mode: string | null;
  setpoint_count: number;
  control_request_count: number;
  fingerprint: string | null;
  latency_ms: number | null;
}

export interface ResponseItem {
  response: {
    status: RecommendationStatus;
    fault_type: FaultKind | null;
    target_tag: string | null;
    confidence: number;
    rationale_text: string;
    setpoints: { tag: string; value: number; unit: string }[];
    control_requests: {
      kind: ControlKind;
      tag: string;
      value: number | null;
      unit: string | null;
      reason: string;
    }[];
    requires_human_confirmation: boolean;
    degraded_mode: string | null;
    evidence_tags: string[];
  };
  fingerprint: string;
  index: number;
  latency_ms: number;
  observation_id: string;
  observed_at_s: number;
  request?: Record<string, unknown>;
}

export interface ControlRequest {
  kind: ControlKind;
  tag: string;
  value: number | null;
  unit: string | null;
  reason: string;
}

export interface GateDecision {
  request_id: string;
  submitted_at_s: number;
  request: ControlRequest;
  allowed: boolean;
  executed: boolean;
  blocking_layer: GateLayer;
  reason: string;
  violated_rule: string | null;
  requires_confirmation: boolean;
  confirmed_by: string | null;
  interlock_rule_ids: string[];
}

export interface InjectionArtifact {
  kind: FaultKind;
  target_tag: string;
  start_s: number;
  duration_s: number;
  seed?: number;
  params?: Record<string, PhysicalValue>;
  [key: string]: unknown;
}

export interface InjectionDocument {
  final_setpoints: TaggedValue[];
  injection_artifacts: InjectionArtifact[];
  mechanism_checks: MechanismCheck[];
  stimulus_events: Record<string, unknown>[];
}

export interface CaseDetail {
  run: RunSummary;
  result: CaseResult;
  case: CaseMeta | null;
  files: string[];
  artifact_dir: string;
}
