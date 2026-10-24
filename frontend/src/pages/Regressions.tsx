import {
  AlertTriangle,
  ArrowUpRight,
  Ban,
  Fingerprint,
  GitCompareArrows,
  RefreshCw,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import {
  Badge,
  EmptyPanel,
  ErrorPanel,
  Hash,
  LoadingPanel,
  SectionHeading,
  type Tone,
} from "../components/ui";
import {
  defectLevelLabels,
  formatDateTime,
  formatNumber,
  formatPercent,
  regressionKindLabels,
  shortHash,
} from "../lib/format";
import { useAsync } from "../lib/useAsync";
import type { DefectLevel, RegressionKind, RegressionReport, RegressionRow } from "../types";

const metricLabels: Record<string, string> = {
  detected: "故障识别",
  missed_fault: "故障漏报",
  missed_faults: "漏报总数",
  false_alarms: "误报数",
  false_alarm_rate: "误报率",
  high_risk_false_alarms: "高风险误报",
  latency: "检测时延",
  latency_ratio: "时延比值",
  fingerprint: "结论指纹",
  degradation_missing: "安全降级缺失",
  unsafe_setpoint: "越安全边界",
  unauthorized_command: "越权控制",
  interlock_missed: "联锁漏触发",
  interlock_false_trip: "联锁误动作",
  p0: "P0 缺陷",
  p1: "P1 缺陷",
};

function kindTone(kind: RegressionKind): Tone {
  if (kind === "severe_regression") {
    return "critical";
  }
  if (kind === "unexpected_change") {
    return "warning";
  }
  if (kind === "improvement") {
    return "good";
  }
  return "neutral";
}

function levelTone(level: DefectLevel | null): Tone {
  if (level === "P0") {
    return "critical";
  }
  if (level === "P1") {
    return "warning";
  }
  if (level === "P2") {
    return "info";
  }
  return "neutral";
}

function RegressionTable({
  title,
  rows,
  report,
}: {
  title: string;
  rows: RegressionRow[];
  report: RegressionReport;
}) {
  if (rows.length === 0) {
    return (
      <section className="surface">
        <SectionHeading title={title} action={<span className="section-count">0 条</span>} />
        <p className="muted">本组无记录。</p>
      </section>
    );
  }
  return (
    <section className="surface">
      <SectionHeading title={title} action={<span className="section-count">{rows.length} 条</span>} />
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>级别</th>
              <th>用例</th>
              <th>指标</th>
              <th>基线</th>
              <th>候选</th>
              <th>说明</th>
              <th aria-label="操作" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.case_id}-${row.metric}-${index}`}>
                <td>
                  {row.level ? (
                    <Badge tone={levelTone(row.level)}>{defectLevelLabels[row.level]}</Badge>
                  ) : (
                    <Badge tone={kindTone(row.kind)}>{regressionKindLabels[row.kind]}</Badge>
                  )}
                </td>
                <td>
                  {row.case_id === "*" ? (
                    <span className="muted">全运行</span>
                  ) : (
                    <Link
                      className="table-primary"
                      to={`/runs/${report.candidate_run_id}/cases/${row.case_id}`}
                    >
                      {row.case_id}
                    </Link>
                  )}
                </td>
                <td>{metricLabels[row.metric] ?? row.metric}</td>
                <td><code className="inline-code">{row.baseline}</code></td>
                <td><code className="inline-code">{row.current}</code></td>
                <td className="table-detail">{row.detail}</td>
                <td>
                  {row.case_id !== "*" && (
                    <Link
                      className="icon-link"
                      to={`/runs/${report.candidate_run_id}/cases/${row.case_id}`}
                      aria-label="查看用例证据"
                      title="查看用例证据"
                    >
                      <ArrowUpRight size={15} />
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function RegressionsPage() {
  const regressions = useAsync(api.listRegressions, []);
  const baselines = useAsync(api.listBaselines, []);
  const runs = useAsync(() => api.listRuns({ limit: 100 }), []);
  const [params, setParams] = useSearchParams();

  const [baselineId, setBaselineId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [comparing, setComparing] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const candidateRuns = useMemo(
    () => (runs.data?.items ?? []).filter((run) => run.status === "completed"),
    [runs.data],
  );

  useEffect(() => {
    if (!baselineId && baselines.data && baselines.data.items.length > 0) {
      setBaselineId(baselines.data.items[0]?.id ?? "");
    }
  }, [baselineId, baselines.data]);

  useEffect(() => {
    if (!candidateId && candidateRuns.length > 0) {
      setCandidateId(candidateRuns[0]?.id ?? "");
    }
  }, [candidateId, candidateRuns]);

  const reports = regressions.data?.items ?? [];
  const selectedId = params.get("report") ?? reports[0]?.id ?? null;
  const selected = reports.find((item) => item.id === selectedId) ?? reports[0] ?? null;

  async function submitCompare(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!baselineId || !candidateId) {
      setFormError("请选择基线与候选运行。");
      return;
    }
    setComparing(true);
    setFormError(null);
    try {
      const report = await api.createRegression({
        candidate_run_id: candidateId,
        baseline_id: baselineId,
      });
      setParams({ report: report.id });
      regressions.reload();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "回归比较失败。");
    } finally {
      setComparing(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <div className="page-eyebrow">VERSION AUDIT</div>
          <h1 className="page-title">回归对比</h1>
          <p className="page-description">
            比较结论指纹、P0 级缺陷与关键指标。用例覆盖、领域哈希或联锁哈希不一致时，平台拒绝比较。
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="button button--ghost"
            onClick={regressions.reload}
            disabled={regressions.refreshing}
          >
            <RefreshCw size={15} className={regressions.refreshing ? "spin" : ""} /> 刷新
          </button>
        </div>
      </header>

      <section className="surface">
        <SectionHeading
          eyebrow="STRICT COMPARABILITY"
          title="创建回归比较"
          description="候选运行必须与基线具有相同用例覆盖与完全一致的领域/联锁哈希。任一条件不满足，比较将被拒绝而不是降级比较。"
        />
        <form className="compare-form" onSubmit={(event) => void submitCompare(event)}>
          <label className="field">
            <span className="field__label">基线</span>
            <select
              value={baselineId}
              onChange={(event) => setBaselineId(event.target.value)}
              disabled={comparing || baselines.loading}
              required
            >
              {baselines.data?.items.length ? (
                baselines.data.items.map((baseline) => (
                  <option key={baseline.id} value={baseline.id}>
                    {baseline.name} · {baseline.agent_version} · {baseline.case_count} 例
                  </option>
                ))
              ) : (
                <option value="">暂无基线</option>
              )}
            </select>
          </label>
          <label className="field">
            <span className="field__label">候选运行</span>
            <select
              value={candidateId}
              onChange={(event) => setCandidateId(event.target.value)}
              disabled={comparing || runs.loading}
              required
            >
              {candidateRuns.length ? (
                candidateRuns.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.name} · {run.agent_name} · {run.case_count} 例
                  </option>
                ))
              ) : (
                <option value="">暂无已完成运行</option>
              )}
            </select>
          </label>
          <button
            type="submit"
            className="button button--primary"
            disabled={comparing || !baselineId || !candidateId}
          >
            <GitCompareArrows size={15} /> {comparing ? "比较中…" : "执行比较"}
          </button>
        </form>
        {formError && (
          <div className="inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" />
            <span>{formError}</span>
          </div>
        )}
        <p className="muted compare-note">
          提示：在运行详情页也可直接将当前运行与该运行的基线比较；回归记录会持久化。
        </p>
      </section>

      {regressions.loading && <LoadingPanel label="正在读取回归记录…" />}
      {regressions.error && !regressions.data && (
        <ErrorPanel message={regressions.error} onRetry={regressions.reload} />
      )}

      {regressions.data && reports.length === 0 && (
        <EmptyPanel
          title="尚无回归报告"
          description="先在运行详情页固化基线，再选择候选运行进行比较。"
          icon={<GitCompareArrows size={24} />}
        />
      )}

      {reports.length > 0 && selected && (
        <div className="regression-layout">
          <aside className="regression-list" aria-label="回归报告列表">
            {reports.map((report) => (
              <button
                key={report.id}
                type="button"
                className={`regression-list__item${selected.id === report.id ? " regression-list__item--active" : ""}`}
                onClick={() => setParams({ report: report.id })}
              >
                <div className="regression-list__top">
                  <Badge tone={report.comparable ? (report.severe_regressions.length > 0 ? "critical" : "info") : "critical"}>
                    {report.comparable
                      ? report.severe_regressions.length > 0
                        ? `严重回归 ${report.severe_regressions.length}`
                        : "未记录严重回归"
                      : "不可比"}
                  </Badge>
                  <span>{formatDateTime(report.created_at)}</span>
                </div>
                <strong>{shortHash(report.id, 22)}</strong>
                <div className="regression-list__meta">
                  <span>指纹一致 {formatPercent(report.fingerprint_match_rate)}</span>
                  <span>非预期 {report.unexpected_changes.length}</span>
                </div>
              </button>
            ))}
          </aside>

          <div className="regression-detail">
            <section className="regression-hero">
              <div>
                <div className="hero-kicker">
                  <span>回归结论</span>
                  <Badge tone={selected.comparable ? "info" : "critical"}>
                    {selected.comparable ? "严格可比" : "不可比"}
                  </Badge>
                </div>
                <h2>
                  {selected.comparable
                    ? selected.severe_regressions.length > 0
                      ? `${selected.severe_regressions.length} 条严重回归`
                      : "未记录严重回归"
                    : "比较被拒绝"}
                </h2>
                <p>
                  {selected.comparable
                    ? "严重回归按阻断优先级展示；指纹一致率用于发现结构化结论漂移，不代表自然语言理由一致。"
                    : "候选运行与基线的覆盖或安全哈希不一致。平台不会输出降级比较结论。"}
                </p>
                <div className="regression-links">
                  <Link className="text-link" to={`/runs/${selected.baseline_run_id}`}>
                    基线运行 <ArrowUpRight size={14} />
                  </Link>
                  <Link className="text-link" to={`/runs/${selected.candidate_run_id}`}>
                    候选运行 <ArrowUpRight size={14} />
                  </Link>
                </div>
              </div>
              <div className="regression-hero__figures">
                <div>
                  <span>严重回归</span>
                  <strong className={selected.severe_regressions.length > 0 ? "numeric-critical" : ""}>
                    {selected.severe_regressions.length}
                  </strong>
                </div>
                <div>
                  <span>非预期变化</span>
                  <strong>{selected.unexpected_changes.length}</strong>
                </div>
                <div>
                  <span>改进</span>
                  <strong>{selected.improvements.length}</strong>
                </div>
                <div>
                  <span>指纹一致率</span>
                  <strong>{formatPercent(selected.fingerprint_match_rate)}</strong>
                </div>
                <div>
                  <span>时延比</span>
                  <strong>{selected.latency_ratio === null ? "—" : `×${formatNumber(selected.latency_ratio, 2)}`}</strong>
                </div>
              </div>
            </section>

            {!selected.comparable && selected.blockers.length > 0 && (
              <section className="surface surface--danger">
                <SectionHeading title="比较阻断原因" eyebrow="REFUSED" />
                <ul className="blocker-list">
                  {selected.blockers.map((blocker) => (
                    <li key={blocker}>
                      <Ban size={15} aria-hidden="true" />
                      <span>{blocker}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="surface">
              <SectionHeading
                title="覆盖与安全哈希"
                eyebrow="HASH AUDIT"
                description="三项哈希任一不一致，都不能把差异归因于 Agent 版本变化。"
              />
              <div className="hash-audit">
                {Object.entries(selected.hash_results).map(([key, value]) => {
                  const match = value.baseline === value.candidate;
                  const labels: Record<string, string> = {
                    case_set_hash: "用例集哈希",
                    domain_hash: "领域哈希",
                    interlock_hash: "联锁哈希",
                  };
                  return (
                    <div className="hash-audit__row" key={key}>
                      <span>{labels[key] ?? key}</span>
                      <Hash value={value.baseline} length={16} copy={false} />
                      <span className="hash-audit__arrow" aria-hidden="true">→</span>
                      <Hash value={value.candidate} length={16} copy={false} />
                      <Badge tone={match ? "good" : "critical"}>{match ? "一致" : "不一致"}</Badge>
                    </div>
                  );
                })}
              </div>
            </section>

            {selected.comparable && (
              <>
                <RegressionTable
                  title="严重回归"
                  rows={selected.severe_regressions}
                  report={selected}
                />
                <RegressionTable
                  title="非预期变化"
                  rows={selected.unexpected_changes}
                  report={selected}
                />
                <RegressionTable
                  title="改进"
                  rows={selected.improvements}
                  report={selected}
                />
              </>
            )}
          </div>
        </div>
      )}

      <div className="disclaimer">
        <AlertTriangle size={16} aria-hidden="true" />
        <p>
          回归只比较结构化结论指纹。改写理由、置信度微调或仅切换 Agent 标识，不应被误报为结论变化。
        </p>
        <span><Fingerprint size={13} aria-hidden="true" /> 指纹不含 Agent 标识与自然语言</span>
      </div>
    </div>
  );
}
