import {
  ArrowLeft,
  Database,
  Download,
  FileJson,
  Files,
  Fingerprint,
  Gauge,
  ListChecks,
  MessageSquareText,
  ShieldAlert,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { DefectCard, FingerprintLine, TraceChips } from "../components/data";
import { TelemetrySection } from "../components/TelemetryChart";
import {
  Badge,
  EmptyPanel,
  ErrorPanel,
  Hash,
  KeyValue,
  LoadingPanel,
  SectionHeading,
} from "../components/ui";
import {
  controlKindLabels,
  dataSourceLabels,
  defectSort,
  faultLabels,
  formatNumber,
  formatPercent,
  formatSeconds,
  formatUnit,
  gateLayerLabels,
  timelineStateLabels,
} from "../lib/format";
import { useAsync } from "../lib/useAsync";
import type {
  CaseMeta,
  CaseResult,
  ControlRequest,
  GateDecision,
  MechanismCheck,
  ResponseItem,
} from "../types";

type CaseTab = "verdict" | "telemetry" | "responses" | "gates" | "files";

const tabs: { id: CaseTab; label: string; icon: typeof Gauge }[] = [
  { id: "verdict", label: "判定与轨迹", icon: ListChecks },
  { id: "telemetry", label: "时序曲线", icon: Gauge },
  { id: "responses", label: "原始响应", icon: MessageSquareText },
  { id: "gates", label: "门禁决策", icon: ShieldAlert },
  { id: "files", label: "证据文件", icon: Files },
];

function detectionSummary(result: CaseResult, shouldDetect: boolean): {
  tone: "good" | "critical" | "neutral";
  title: string;
  detail: string;
} {
  if (shouldDetect) {
    if (result.detected) {
      return {
        tone: "good",
        title: "已识别目标故障",
        detail: `检测时刻 ${formatSeconds(result.detection_t_s)}，时延 ${formatSeconds(result.latency_s)}。`,
      };
    }
    return {
      tone: "critical",
      title: "漏报",
      detail: "用例期望识别故障，但 Agent 在判定窗口内未给出正确结论。",
    };
  }
  if (result.detected) {
    return {
      tone: "critical",
      title: "误报",
      detail: "用例期望保持正常/仅关注边界，Agent 却给出故障结论。",
    };
  }
  return {
    tone: "neutral",
    title: "无报警",
    detail: "该用例不要求故障识别；仍需检查越权控制与动作轨迹。",
  };
}

export function CaseDetailPage() {
  const { runId, caseId } = useParams();
  const detail = useAsync(
    () =>
      runId && caseId
        ? api.caseDetail(runId, caseId)
        : Promise.reject(new Error("缺少运行或用例 ID")),
    [runId, caseId],
  );
  const meta = useAsync(api.meta, []);
  const [tab, setTab] = useState<CaseTab>("verdict");

  if (detail.loading) {
    return (
      <div className="page">
        <LoadingPanel label="正在读取用例证据链…" />
      </div>
    );
  }
  if (detail.error || !detail.data) {
    return (
      <div className="page">
        <ErrorPanel message={detail.error ?? "用例证据不存在"} onRetry={detail.reload} />
        {runId && (
          <Link className="button button--ghost" to={`/runs/${runId}`}>
            <ArrowLeft size={15} /> 返回运行
          </Link>
        )}
      </div>
    );
  }

  const { result, case: testCase, run } = detail.data;
  const defects = defectSort(result.defects);
  const p0 = defects.filter((item) => item.level === "P0");
  const p1 = defects.filter((item) => item.level === "P1");
  const shouldDetect = testCase?.expected.should_detect ?? false;
  const detection = detectionSummary(result, shouldDetect);

  return (
    <div className="page">
      <div className="page-back">
        <Link className="text-link" to={`/runs/${run.id}`}>
          <ArrowLeft size={14} /> {run.name}
        </Link>
      </div>

      <header className="page-header">
        <div>
          <div className="page-eyebrow">
            CASE EVIDENCE · {result.case_id} · {result.category}
          </div>
          <h1 className="page-title">{testCase?.name ?? result.case_name}</h1>
          <p className="page-description">
            {testCase?.description ?? "用例定义未在本次目录中找到，仅展示运行证据。"}
          </p>
        </div>
        <div className="page-actions">
          <Link className="button button--ghost" to={`/runs/${run.id}`}>
            <ArrowLeft size={15} /> 返回运行
          </Link>
          {run.report_available && (
            <Link className="button button--ghost" to={`/runs/${run.id}/report`}>
              <FileJson size={15} /> 运行报告
            </Link>
          )}
        </div>
      </header>

      {testCase && (
        <div className="provenance-banner">
          <Database size={18} aria-hidden="true" />
          <div>
            <strong>数据来源：{dataSourceLabels[testCase.source]}</strong>
            <p>{testCase.provenance}</p>
          </div>
          <div className="provenance-banner__meta">
            <span>seed <code>{testCase.seed}</code></span>
            <span>时长 {formatSeconds(testCase.duration_s)}</span>
            <span>判定间隔 {formatSeconds(testCase.decision_interval_s)}</span>
          </div>
        </div>
      )}

      <section className="case-summary">
        <div className={`case-summary__verdict case-summary__verdict--${detection.tone}`}>
          <Badge tone={detection.tone}>{detection.title}</Badge>
          <p>{detection.detail}</p>
          <div className="case-summary__verdict-meta">
            <span>
              预期故障 <strong>{testCase?.expected.fault_type ? faultLabels[testCase.expected.fault_type] : "无"}</strong>
            </span>
            <span>
              目标 <strong>{testCase?.expected.target_tag ?? "—"}</strong>
            </span>
            <span>
              安全降级 <strong>{result.degraded_correct ? "正确" : shouldDetect ? "未验证" : "不适用"}</strong>
            </span>
          </div>
        </div>
        <div className="case-summary__facts">
          <div>
            <span>P0 阻断</span>
            <strong className={p0.length > 0 ? "numeric-critical" : ""}>{p0.length}</strong>
          </div>
          <div>
            <span>P1 风险</span>
            <strong className={p1.length > 0 ? "numeric-warning" : ""}>{p1.length}</strong>
          </div>
          <div>
            <span>误报</span>
            <strong>{result.false_alarms}</strong>
          </div>
          <div>
            <span>越权尝试</span>
            <strong className={result.unauthorized_attempts > 0 ? "numeric-critical" : ""}>
              {result.unauthorized_attempts}
            </strong>
          </div>
          <div>
            <span>越安全边界</span>
            <strong className={result.unsafe_setpoints > 0 ? "numeric-critical" : ""}>
              {result.unsafe_setpoints}
            </strong>
          </div>
        </div>
      </section>

      <div className="fingerprint-bar">
        <FingerprintLine fingerprint={result.fingerprint} reproducible={result.reproducible} />
        <span className="muted">指纹只包含结构化结论与动作类型，不包含自然语言措辞与置信度。</span>
      </div>

      {defects.length > 0 && (
        <section className="surface">
          <SectionHeading
            title="缺陷清单"
            eyebrow="P0 FIRST"
            description="先展示 P0，再展示 P1/P2；每条缺陷都绑定证据路径与机制依据。"
            action={<span className="section-count">{defects.length} 条</span>}
          />
          <div className="defect-stack">
            {defects.map((defect) => (
              <DefectCard key={defect.id} defect={defect} runId={run.id} />
            ))}
          </div>
        </section>
      )}

      <div className="tab-bar" role="tablist" aria-label="用例证据视图">
        {tabs.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              className={`tab${tab === item.id ? " tab--active" : ""}`}
              onClick={() => setTab(item.id)}
            >
              <Icon size={15} aria-hidden="true" />
              {item.label}
            </button>
          );
        })}
      </div>

      {tab === "verdict" && (
        <VerdictTab
          runId={run.id}
          caseId={result.case_id}
          result={result}
          testCase={testCase}
          shouldDetect={shouldDetect}
        />
      )}
      {tab === "telemetry" && (
        <section className="surface">
          <SectionHeading
            title="真实过程与测量通道"
            description="每张图独立纵轴，不使用双轴。故障窗口跨测点统一标注；测量坏质量点不参与连线。"
          />
          {meta.data ? (
            <TelemetrySection
              runId={run.id}
              caseId={result.case_id}
              sensors={meta.data.sensors}
              faults={testCase?.faults ?? []}
            />
          ) : meta.error ? (
            <ErrorPanel message={meta.error} onRetry={meta.reload} />
          ) : (
            <LoadingPanel label="正在读取测点定义…" />
          )}
        </section>
      )}
      {tab === "responses" && <ResponsesTab runId={run.id} caseId={result.case_id} />}
      {tab === "gates" && <GatesTab runId={run.id} caseId={result.case_id} />}
      {tab === "files" && (
        <FilesTab
          runId={run.id}
          caseId={result.case_id}
          files={detail.data.files}
          artifactDir={detail.data.artifact_dir}
        />
      )}
    </div>
  );
}

function VerdictTab({
  runId,
  caseId,
  result,
  testCase,
  shouldDetect,
}: {
  runId: string;
  caseId: string;
  result: CaseResult;
  testCase: CaseMeta | null;
  shouldDetect: boolean;
}) {
  return (
    <div className="tab-content">
      <div className="two-column two-column--wide-left">
        <section className="surface">
          <SectionHeading title="期望 vs 实际" eyebrow="CASE CONTRACT" />
          <div className="table-wrap table-wrap--compact">
            <table className="data-table data-table--compact">
              <thead>
                <tr>
                  <th>判定项</th>
                  <th>期望</th>
                  <th>实际</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>故障识别</td>
                  <td>{shouldDetect ? "应识别" : "不要求识别"}</td>
                  <td>{result.detected ? "已给出异常结论" : "未给出异常结论"}</td>
                </tr>
                <tr>
                  <td>故障类型</td>
                  <td>{testCase?.expected.fault_type ? faultLabels[testCase.expected.fault_type] : "—"}</td>
                  <td>{result.correct_type ? "类型正确" : "未验证/错误"}</td>
                </tr>
                <tr>
                  <td>目标位号</td>
                  <td>{testCase?.expected.target_tag ?? "—"}</td>
                  <td>{result.target_correct ? "正确" : "未验证/错误"}</td>
                </tr>
                <tr>
                  <td>检测时延</td>
                  <td>≤ {formatSeconds(testCase?.expected.max_latency_s)}</td>
                  <td>{formatSeconds(result.latency_s)}</td>
                </tr>
                <tr>
                  <td>误报</td>
                  <td>≤ {testCase?.expected.max_false_alarms ?? 0}</td>
                  <td>{result.false_alarms}（高风险 {result.high_risk_false_alarms}）</td>
                </tr>
                <tr>
                  <td>安全降级</td>
                  <td>{testCase?.expected.require_degraded_response ? "必须明确降级" : "未要求"}</td>
                  <td>{result.degraded_correct ? "已正确降级" : "未触发/未验证"}</td>
                </tr>
                <tr>
                  <td>坏数据控制</td>
                  <td>{testCase?.expected.forbid_control_on_invalid_data ? "禁止控制" : "未约束"}</td>
                  <td>{result.actual_action_trace.includes("DCS_WRITE") ? "发生过写入" : "无写入"}</td>
                </tr>
              </tbody>
            </table>
          </div>
          {testCase && (
            <div className="case-plan">
              <div>
                <h4>时序状态</h4>
                <div className="timeline-track">
                  {testCase.timeline.map((segment) => (
                    <div
                      key={`${segment.start_s}-${segment.state}`}
                      className={`timeline-segment timeline-segment--${segment.state}`}
                      style={{ flexGrow: segment.duration_s }}
                      title={`${timelineStateLabels[segment.state]} · ${formatSeconds(segment.start_s)}–${formatSeconds(segment.start_s + segment.duration_s)}`}
                    >
                      <span>{timelineStateLabels[segment.state]}</span>
                      <small>
                        {formatNumber(segment.start_s, 0)}s + {formatNumber(segment.duration_s, 0)}s
                      </small>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h4>初始条件</h4>
                <div className="value-chips">
                  {testCase.initial_conditions.map((item) => (
                    <span className="value-chip" key={item.tag}>
                      <code>{item.tag}</code>
                      {formatNumber(item.value, 2)} {formatUnit(item.unit)}
                    </span>
                  ))}
                </div>
              </div>
              {testCase.faults.length > 0 && (
                <div>
                  <h4>故障计划</h4>
                  <div className="value-chips">
                    {testCase.faults.map((fault, index) => (
                      <span className="value-chip" key={`${fault.kind}-${index}`}>
                        <code>{fault.kind}</code>
                        {fault.target_tag} · {formatSeconds(fault.start_s)} 起，持续 {formatSeconds(fault.duration_s)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        <section className="surface">
          <SectionHeading title="动作轨迹" eyebrow="ACTION TRACE" />
          <div className="trace-panel">
            <div>
              <h4>期望动作</h4>
              <TraceChips trace={testCase?.expected.expected_action_trace ?? result.expected_action_trace} />
            </div>
            <div>
              <h4>实际动作</h4>
              <TraceChips trace={result.actual_action_trace} />
            </div>
            <div className="trace-panel__result">
              {result.action_trace_match === null ? (
                <Badge tone="neutral">未定义期望轨迹</Badge>
              ) : result.action_trace_match ? (
                <Badge tone="good">轨迹一致</Badge>
              ) : (
                <Badge tone="critical">轨迹不一致</Badge>
              )}
            </div>
          </div>
          <div className="counting-note">
            <ShieldCheck size={15} aria-hidden="true" />
            <p>
              动作轨迹按事件类型与顺序比对。DCS 写入必须出现在门禁放行之后；被阻断的请求不得产生写入。
            </p>
          </div>
        </section>
      </div>

      <section className="surface">
        <SectionHeading
          title="机理校验"
          eyebrow="MECHANISM GATE"
          description="注入是否真实改变了应改变的通道；测量漂移不得改变真实过程。"
        />
        {result.mech_checks.length === 0 ? (
          <EmptyPanel title="该用例未执行机理校验" description="稳态与边界用例不注入过程故障。" />
        ) : (
          <div className="check-grid">
            {result.mech_checks.map((check) => (
              <MechanismCard key={`${check.check_name}-${check.target_tag}`} check={check} />
            ))}
          </div>
        )}
      </section>

      <section className="surface">
        <SectionHeading
          title="联锁评估"
          eyebrow="SIS INDEPENDENCE"
          description="联锁逻辑不由 Agent 配置或禁用；此处只展示仿真侧真实值触发结果。"
        />
        {result.interlock_evaluations.length === 0 ? (
          <EmptyPanel title="未记录联锁评估" />
        ) : (
          <div className="table-wrap table-wrap--compact">
            <table className="data-table data-table--compact">
              <thead>
                <tr>
                  <th>规则</th>
                  <th>应触发</th>
                  <th>实际触发</th>
                  <th>触发时刻</th>
                  <th>结论</th>
                </tr>
              </thead>
              <tbody>
                {result.interlock_evaluations.map((item) => {
                  const correct = item.should_trigger === item.triggered && !item.false_trip;
                  return (
                    <tr key={item.rule_id}>
                      <td><code>{item.rule_id}</code></td>
                      <td>{item.should_trigger ? "是" : "否"}</td>
                      <td>{item.triggered ? "是" : "否"}</td>
                      <td>{formatSeconds(item.trigger_t_s)}</td>
                      <td>
                        <Badge tone={correct ? "good" : "critical"}>
                          {correct
                            ? item.triggered
                              ? "正确触发"
                              : "正确未触发"
                            : item.should_trigger
                              ? "漏触发"
                              : "误动作"}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <InjectionPanel runId={runId} caseId={caseId} />
    </div>
  );
}

function MechanismCard({ check }: { check: MechanismCheck }) {
  return (
    <article className="check-card">
      <div className="check-card__head">
        <Badge tone={check.passed ? "good" : "critical"}>
          {check.passed ? "机理校验通过" : "机理校验失败"}
        </Badge>
        <code>{check.check_name}</code>
      </div>
      <p>{check.detail}</p>
      <div className="check-card__meta">
        <span>故障：{check.fault_type ? faultLabels[check.fault_type] : "—"}</span>
        <span>目标：{check.target_tag ?? "—"}</span>
      </div>
      {Object.keys(check.evidence).length > 0 && (
        <dl className="check-evidence">
          {Object.entries(check.evidence).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{formatNumber(value, 3)}</dd>
            </div>
          ))}
        </dl>
      )}
    </article>
  );
}

function InjectionPanel({ runId, caseId }: { runId: string; caseId: string }) {
  const injection = useAsync(
    () => api.injection(runId, caseId),
    [runId, caseId],
  );
  return (
    <section className="surface">
      <SectionHeading
        title="注入与终态设定值"
        eyebrow="INJECTION RECORD"
        description="记录注入参数、随机种子与终态 DCS 设定值，供复现与机理追溯。"
      />
      {injection.loading && <LoadingPanel label="正在读取注入记录…" />}
      {injection.error && <ErrorPanel message={injection.error} onRetry={injection.reload} />}
      {injection.data && (
        <div className="injection-layout">
          <div>
            <h4>注入故障</h4>
            {injection.data.injection_artifacts.length === 0 ? (
              <p className="muted">本用例无故障注入。</p>
            ) : (
              <div className="injection-list">
                {injection.data.injection_artifacts.map((artifact, index) => (
                  <article className="injection-card" key={`${artifact.kind}-${index}`}>
                    <div>
                      <Badge tone="info">{faultLabels[artifact.kind]}</Badge>
                      <code>{artifact.kind}</code>
                    </div>
                    <dl>
                      <div>
                        <dt>目标</dt>
                        <dd>{artifact.target_tag}</dd>
                      </div>
                      <div>
                        <dt>窗口</dt>
                        <dd>
                          {formatSeconds(artifact.start_s)} –{" "}
                          {formatSeconds(artifact.start_s + artifact.duration_s)}
                        </dd>
                      </div>
                      {artifact.seed !== undefined && (
                        <div>
                          <dt>注入种子</dt>
                          <dd><code>{artifact.seed}</code></dd>
                        </div>
                      )}
                    </dl>
                    {artifact.params && (
                      <div className="value-chips">
                        {Object.entries(artifact.params).map(([key, value]) => (
                          <span className="value-chip" key={key}>
                            <code>{key}</code>
                            {formatNumber(value.value, 3)} {formatUnit(value.unit)}
                          </span>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}
          </div>
          <div>
            <h4>终态 DCS 设定值</h4>
            <div className="value-chips value-chips--stacked">
              {injection.data.final_setpoints.map((item) => (
                <span className="value-chip" key={item.tag}>
                  <code>{item.tag}</code>
                  {formatNumber(item.value, 2)} {formatUnit(item.unit)}
                </span>
              ))}
            </div>
            {injection.data.stimulus_events.length > 0 && (
              <>
                <h4>操作员/外部激励</h4>
                <pre className="code-block code-block--short">
                  {JSON.stringify(injection.data.stimulus_events, null, 2)}
                </pre>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function ResponsesTab({ runId, caseId }: { runId: string; caseId: string }) {
  const responses = useAsync(() => api.responses(runId, caseId), [runId, caseId]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  useEffect(() => {
    if (responses.data && selectedIndex === null && responses.data.items.length > 0) {
      const interesting =
        responses.data.items.find((item) => item.status === "anomaly" || item.status === "degraded") ??
        responses.data.items[0];
      if (interesting) {
        setSelectedIndex(interesting.index);
      }
    }
  }, [responses.data, selectedIndex]);

  const raw = useAsync(
    () =>
      selectedIndex === null
        ? Promise.resolve(null)
        : api.response(runId, caseId, selectedIndex),
    [runId, caseId, selectedIndex],
  );

  return (
    <section className="surface">
      <SectionHeading
        title="Agent 原始响应"
        eyebrow="STRUCTURED OUTPUT"
        description="自然语言理由仅用于审计可读性，不进入结论指纹，也不作为判定依据。"
      />
      {responses.loading && <LoadingPanel label="正在读取响应记录…" />}
      {responses.error && <ErrorPanel message={responses.error} onRetry={responses.reload} />}
      {responses.data && responses.data.items.length === 0 && (
        <EmptyPanel title="没有 Agent 响应" description="该用例未产生调用记录。" />
      )}
      {responses.data && responses.data.items.length > 0 && (
        <div className="response-layout">
          <div className="response-list" role="list">
            {responses.data.items.map((item) => (
              <button
                key={item.index}
                type="button"
                className={`response-list__item${selectedIndex === item.index ? " response-list__item--active" : ""}`}
                onClick={() => setSelectedIndex(item.index)}
              >
                <div className="response-list__top">
                  <span>#{item.index} · {formatSeconds(item.observed_at_s)}</span>
                  <Badge
                    tone={
                      item.status === "anomaly"
                        ? "critical"
                        : item.status === "attention"
                          ? "warning"
                          : item.status === "degraded"
                            ? "info"
                            : "neutral"
                    }
                  >
                    {item.status ?? "unknown"}
                  </Badge>
                </div>
                <div className="response-list__body">
                  <span>
                    {item.fault_type ? faultLabels[item.fault_type] : "无故障类型"}
                    {item.target_tag ? ` · ${item.target_tag}` : ""}
                  </span>
                  <small>
                    设定值 {item.setpoint_count} · 控制请求 {item.control_request_count}
                  </small>
                </div>
              </button>
            ))}
          </div>
          <div className="response-detail">
            {raw.loading && <LoadingPanel label="正在读取响应正文…" />}
            {raw.error && <ErrorPanel message={raw.error} onRetry={raw.reload} />}
            {raw.data && (
              <ResponseDetail
                item={raw.data}
                downloadUrl={api.artifactUrl(
                  runId,
                  caseId,
                  `responses/call-${String(raw.data.index).padStart(4, "0")}.json`,
                )}
              />
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function ResponseDetail({ item, downloadUrl }: { item: ResponseItem; downloadUrl: string }) {
  const response = item.response;
  return (
    <>
      <div className="response-head">
        <div>
          <div className="response-head__title">
            <Badge
              tone={
                response.status === "anomaly"
                  ? "critical"
                  : response.status === "attention"
                    ? "warning"
                    : response.status === "degraded"
                      ? "info"
                      : "neutral"
              }
            >
              {response.status}
            </Badge>
            <code>{item.observation_id}</code>
          </div>
          <div className="response-head__meta">
            <span>t={formatSeconds(item.observed_at_s)}</span>
            <span>置信度 {formatPercent(response.confidence, 0)}</span>
            <span>耗时 {formatNumber(item.latency_ms, 2)} ms</span>
            <span>降级 {response.degraded_mode ?? "否"}</span>
          </div>
        </div>
        <a className="button button--ghost button--sm" href={downloadUrl}>
          <Download size={14} /> 原始文件
        </a>
      </div>

      <KeyValue
        items={[
          { label: "故障类型", value: response.fault_type ? faultLabels[response.fault_type] : "—" },
          { label: "目标位号", value: response.target_tag ?? "—" },
          { label: "证据位号", value: response.evidence_tags.join("、") || "—" },
          {
            label: "需人工确认",
            value: response.requires_human_confirmation ? "是" : "否",
          },
        ]}
      />

      <div className="response-section">
        <h4>结构化设定值</h4>
        {response.setpoints.length === 0 ? (
          <p className="muted">无设定值建议。</p>
        ) : (
          <div className="value-chips">
            {response.setpoints.map((itemValue) => (
              <span className="value-chip" key={`${itemValue.tag}-${itemValue.value}`}>
                <code>{itemValue.tag}</code>
                {formatNumber(itemValue.value, 2)} {formatUnit(itemValue.unit)}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="response-section">
        <h4>控制请求</h4>
        {response.control_requests.length === 0 ? (
          <p className="muted">无控制请求。</p>
        ) : (
          <div className="request-list">
            {response.control_requests.map((request: ControlRequest, index) => (
              <div className="request-item" key={`${request.kind}-${index}`}>
                <Badge tone={request.kind === "request_bypass_interlock" ? "critical" : "info"}>
                  {controlKindLabels[request.kind]}
                </Badge>
                <code>{request.tag}</code>
                {request.value !== null && (
                  <span>
                    {formatNumber(request.value, 2)} {formatUnit(request.unit)}
                  </span>
                )}
                <p>{request.reason}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="response-section">
        <h4>自然语言理由</h4>
        <blockquote>{response.rationale_text}</blockquote>
        <p className="muted">措辞与置信度不进入指纹；回归判定不会因改写理由而失败。</p>
      </div>

      <div className="fingerprint-line">
        <Fingerprint size={14} aria-hidden="true" />
        <span>响应指纹</span>
        <Hash value={item.fingerprint} length={24} />
      </div>

      <details className="raw-json">
        <summary>
          <TerminalSquare size={14} /> 查看完整请求/响应 JSON
        </summary>
        <pre className="code-block">{trimJson(item, 60000)}</pre>
      </details>
    </>
  );
}

function trimJson(value: unknown, limit: number): string {
  const text = JSON.stringify(value, null, 2);
  return text.length > limit ? `${text.slice(0, limit)}\n\n… 已截断 ${text.length - limit} 字符，请下载原始文件。` : text;
}

function GatesTab({ runId, caseId }: { runId: string; caseId: string }) {
  const gates = useAsync(() => api.gateDecisions(runId, caseId), [runId, caseId]);
  return (
    <section className="surface">
      <SectionHeading
        title="SafetyGate 门禁决策"
        eyebrow="NO DIRECT DCS WRITE"
        description="所有控制请求按 权限 → 工艺边界 → 人工确认 → SIS → DCS 顺序校验。被阻断请求不会调用 DCS 写入。"
      />
      <div className="gate-flow" aria-label="门禁顺序">
        {["权限", "工艺边界", "人工确认", "SIS", "DCS"].map((layer, index) => (
          <div className="gate-flow__step" key={layer}>
            <span>{index + 1}</span>
            <strong>{layer}</strong>
          </div>
        ))}
      </div>
      {gates.loading && <LoadingPanel label="正在读取门禁决策…" />}
      {gates.error && <ErrorPanel message={gates.error} onRetry={gates.reload} />}
      {gates.data && gates.data.length === 0 && (
        <EmptyPanel
          title="本用例无门禁决策"
          description="Agent 没有提交任何控制请求；或请求在适配器前已被拒绝。"
          icon={<ShieldCheck size={22} />}
        />
      )}
      {gates.data && gates.data.length > 0 && (
        <div className="gate-list">
          {gates.data.map((gate) => (
            <GateCard key={gate.request_id} gate={gate} />
          ))}
        </div>
      )}
    </section>
  );
}

function GateCard({ gate }: { gate: GateDecision }) {
  return (
    <article className={`gate-card gate-card--${gate.allowed ? "allowed" : "blocked"}`}>
      <div className="gate-card__head">
        <div>
          <Badge tone={gate.allowed ? "good" : "critical"}>
            {gate.allowed ? "门禁放行" : "门禁阻断"}
          </Badge>
          <Badge tone={gate.executed ? "good" : "neutral"}>
            {gate.executed ? "DCS 已写入" : "DCS 未写入"}
          </Badge>
          <span className="muted">t={formatSeconds(gate.submitted_at_s)}</span>
        </div>
        <code>{gate.request_id}</code>
      </div>
      <div className="gate-card__request">
        <div>
          <span>请求</span>
          <strong>{controlKindLabels[gate.request.kind]}</strong>
        </div>
        <div>
          <span>位号</span>
          <strong>{gate.request.tag}</strong>
        </div>
        <div>
          <span>目标值</span>
          <strong>
            {gate.request.value === null
              ? "—"
              : `${formatNumber(gate.request.value, 2)} ${formatUnit(gate.request.unit)}`}
          </strong>
        </div>
        <div>
          <span>阻断层</span>
          <strong>{gateLayerLabels[gate.blocking_layer]}</strong>
        </div>
      </div>
      <p className="gate-card__reason">{gate.reason}</p>
      <div className="gate-card__meta">
        {gate.violated_rule && <span>违反规则 <code>{gate.violated_rule}</code></span>}
        {gate.requires_confirmation && <span>需人工确认</span>}
        {gate.confirmed_by && <span>确认人 <code>{gate.confirmed_by}</code></span>}
        {gate.interlock_rule_ids.length > 0 && (
          <span>关联联锁 <code>{gate.interlock_rule_ids.join(", ")}</code></span>
        )}
      </div>
      <div className="gate-card__reason-text">
        <span>Agent 请求理由（不参与门禁判定）：</span>
        <p>{gate.request.reason}</p>
      </div>
    </article>
  );
}

function FilesTab({
  runId,
  caseId,
  files,
  artifactDir,
}: {
  runId: string;
  caseId: string;
  files: string[];
  artifactDir: string;
}) {
  const initial = files.includes("manifest.json") ? "manifest.json" : files[0] ?? "";
  const [selected, setSelected] = useState(initial);
  const content = useAsync(
    () => (selected ? api.artifactText(runId, caseId, selected) : Promise.resolve("")),
    [runId, caseId, selected],
  );

  const preview = useMemo(() => {
    const raw = content.data ?? "";
    if (selected.endsWith(".json")) {
      try {
        const text = JSON.stringify(JSON.parse(raw), null, 2);
        return text.length > 50000 ? `${text.slice(0, 50000)}\n\n… 已截断，请下载完整文件。` : text;
      } catch {
        return raw;
      }
    }
    return raw.length > 50000 ? `${raw.slice(0, 50000)}\n\n… 已截断，请下载完整文件。` : raw;
  }, [content.data, selected]);

  return (
    <section className="surface">
      <SectionHeading
        title="证据文件"
        eyebrow="EVIDENCE CHAIN"
        description="用例定义、时序、原始响应、门禁决策、动作轨迹、判定与清单均落盘。"
      />
      <p className="artifact-path"><Database size={14} aria-hidden="true" /> {artifactDir}</p>
      <div className="files-layout">
        <div className="file-list" role="list">
          {files.map((file) => (
            <button
              key={file}
              type="button"
              className={`file-list__item${selected === file ? " file-list__item--active" : ""}`}
              onClick={() => setSelected(file)}
            >
              {file.endsWith(".json") ? <FileJson size={15} /> : <Files size={15} />}
              <span>{file}</span>
            </button>
          ))}
        </div>
        <div className="file-preview">
          <div className="file-preview__head">
            <code>{selected}</code>
            <a className="button button--ghost button--sm" href={api.artifactUrl(runId, caseId, selected)}>
              <Download size={14} /> 下载
            </a>
          </div>
          {content.loading && <LoadingPanel label="正在读取证据文件…" />}
          {content.error && <ErrorPanel message={content.error} onRetry={content.reload} />}
          {content.data !== null && !content.loading && (
            <pre className="code-block code-block--file">{preview}</pre>
          )}
        </div>
      </div>
    </section>
  );
}
