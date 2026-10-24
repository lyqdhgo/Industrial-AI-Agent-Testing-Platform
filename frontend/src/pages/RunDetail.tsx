import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  ClipboardCheck,
  Download,
  FileText,
  Fingerprint,
  GitCompareArrows,
  ShieldCheck,
  ShieldX,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { DatasetComposition, DefectCard, FingerprintLine, StatTile } from "../components/data";
import {
  Badge,
  ErrorPanel,
  Hash,
  KeyValue,
  LoadingPanel,
  SectionHeading,
} from "../components/ui";
import {
  caseCategoryLabels,
  defectSort,
  formatDateTime,
  formatPercent,
  formatSeconds,
  shortHash,
} from "../lib/format";
import { useAsync } from "../lib/useAsync";
import type { CaseResult, Defect } from "../types";

function detectionLabel(result: CaseResult, shouldDetect: boolean): { text: string; tone: "good" | "critical" | "neutral" } {
  if (shouldDetect) {
    return result.detected
      ? { text: "已识别", tone: "good" }
      : { text: "漏报", tone: "critical" };
  }
  if (result.detected) {
    return { text: "误报", tone: "critical" };
  }
  return { text: "无报警", tone: "neutral" };
}

export function RunDetailPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const runState = useAsync(
    () => (runId ? api.getRun(runId) : Promise.reject(new Error("缺少运行 ID"))),
    [runId],
  );
  const baselines = useAsync(api.listBaselines, []);

  const [baselineName, setBaselineName] = useState("");
  const [baselineBusy, setBaselineBusy] = useState(false);
  const [baselineError, setBaselineError] = useState<string | null>(null);
  const [createdBaselineId, setCreatedBaselineId] = useState<string | null>(null);
  const [reportBusy, setReportBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [compareBaselineId, setCompareBaselineId] = useState("");
  const [compareBusy, setCompareBusy] = useState(false);

  const run = runState.data;

  const defects = useMemo(() => {
    if (!run) {
      return [] as Defect[];
    }
    return defectSort(run.case_results.flatMap((result) => result.defects));
  }, [run]);

  const p0 = defects.filter((defect) => defect.level === "P0");
  const p1 = defects.filter((defect) => defect.level === "P1");
  const p2 = defects.filter((defect) => defect.level === "P2");

  const sortedCases = useMemo(() => {
    if (!run) {
      return [] as CaseResult[];
    }
    return [...run.case_results].sort((a, b) => {
      const aP0 = a.defects.filter((item) => item.level === "P0").length;
      const bP0 = b.defects.filter((item) => item.level === "P0").length;
      if (aP0 !== bP0) {
        return bP0 - aP0;
      }
      const aP1 = a.defects.filter((item) => item.level === "P1").length;
      const bP1 = b.defects.filter((item) => item.level === "P1").length;
      if (aP1 !== bP1) {
        return bP1 - aP1;
      }
      return a.case_id.localeCompare(b.case_id);
    });
  }, [run]);

  if (runState.loading) {
    return (
      <div className="page">
        <LoadingPanel label="正在读取运行证据…" />
      </div>
    );
  }

  if (runState.error || !run) {
    return (
      <div className="page">
        <ErrorPanel message={runState.error ?? "运行不存在"} onRetry={runState.reload} />
        <Link className="button button--ghost" to="/runs">
          <ArrowLeft size={15} /> 返回运行记录
        </Link>
      </div>
    );
  }

  const metrics = run.metrics;
  const existingBaseline = baselines.data?.items.find((item) => item.run_id === run.id) ?? null;
  const selectionBaselineId =
    compareBaselineId || baselines.data?.items[0]?.id || "";
  const missApplicable = metrics !== null && metrics.injected_faults > 0;
  const blocking = metrics?.blocking ?? p0.length > 0;
  const verdictTone = run.status === "failed" ? "critical" : blocking ? "critical" : p1.length > 0 ? "warning" : "neutral";
  const verdictTitle =
    run.status === "failed"
      ? "运行失败，未产生可信指标"
      : p0.length > 0
        ? `发现 ${p0.length} 条 P0 阻断缺陷`
        : p1.length > 0
          ? `未记录 P0，但有 ${p1.length} 条 P1 风险`
          : "未记录 P0 / P1 缺陷";

  async function generateReport(activeRunId: string): Promise<void> {
    setReportBusy(true);
    setActionError(null);
    try {
      await api.generateReport(activeRunId);
      navigate(`/runs/${activeRunId}/report`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "报告生成失败。");
    } finally {
      setReportBusy(false);
    }
  }

  async function createBaseline(
    event: FormEvent<HTMLFormElement>,
    activeRunId: string,
    activeRunName: string,
  ): Promise<void> {
    event.preventDefault();
    setBaselineBusy(true);
    setBaselineError(null);
    try {
      const baseline = await api.createBaseline({
        run_id: activeRunId,
        name: baselineName.trim() || `${activeRunName} 基线`,
      });
      setCreatedBaselineId(baseline.id);
      setCompareBaselineId(baseline.id);
      setBaselineName("");
      baselines.reload();
    } catch (error) {
      setBaselineError(error instanceof Error ? error.message : "基线创建失败。");
    } finally {
      setBaselineBusy(false);
    }
  }

  async function compare(
    event: FormEvent<HTMLFormElement>,
    activeRunId: string,
  ): Promise<void> {
    event.preventDefault();
    if (!selectionBaselineId) {
      setActionError("尚无可用于比较的基线。");
      return;
    }
    setCompareBusy(true);
    setActionError(null);
    try {
      const report = await api.createRegression({
        candidate_run_id: activeRunId,
        baseline_id: selectionBaselineId,
      });
      navigate(`/regressions?report=${report.id}`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "回归比较失败。");
    } finally {
      setCompareBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="page-back">
        <Link className="text-link" to="/runs">
          <ArrowLeft size={14} /> 运行记录
        </Link>
      </div>
      <header className="page-header">
        <div>
          <div className="page-eyebrow">RUN EVIDENCE · {run.suite_id}</div>
          <h1 className="page-title">{run.name}</h1>
          <p className="page-description">
            <code className="inline-code">{run.id}</code>
            <span className="dot-sep" aria-hidden="true" />
            {run.agent_name} · {run.agent_version}
            <span className="dot-sep" aria-hidden="true" />
            {formatDateTime(run.finished_at ?? run.created_at)}
          </p>
        </div>
        <div className="page-actions">
          <Link className="button button--ghost" to="/runs">
            <ArrowLeft size={15} /> 返回
          </Link>
          {run.report_available ? (
            <Link className="button button--ghost" to={`/runs/${run.id}/report`}>
              <FileText size={15} /> 查看报告
            </Link>
          ) : (
            <button
              type="button"
              className="button button--ghost"
              onClick={() => void generateReport(run.id)}
              disabled={reportBusy || run.status !== "completed"}
            >
              <FileText size={15} /> {reportBusy ? "生成中…" : "生成报告"}
            </button>
          )}
        </div>
      </header>

      {actionError && (
        <div className="inline-error" role="alert">
          <AlertTriangle size={15} aria-hidden="true" />
          <span>{actionError}</span>
        </div>
      )}

      <section className={`run-verdict run-verdict--${verdictTone}`}>
        <div className="run-verdict__main">
          <Badge tone={verdictTone === "warning" ? "warning" : verdictTone === "critical" ? "critical" : "neutral"}>
            {run.status === "failed" ? "运行失败" : blocking ? "存在阻断项" : "未记录阻断项"}
          </Badge>
          <h2>{verdictTitle}</h2>
          <p>
            {run.status === "failed"
              ? run.error ?? "执行链异常，运行已诚实记录为 failed。"
              : "该结论仅针对本次运行、本次用例集与种子。未观测到 P0/P1 不等于测试通过，漏报率与覆盖率仍需联合审阅。"}
          </p>
        </div>
        <div className="run-verdict__figures">
          <div>
            <span>漏报率</span>
            <strong className={metrics && metrics.missed_faults > 0 ? "numeric-critical" : ""}>
              {metrics && missApplicable ? formatPercent(metrics.miss_rate) : "—"}
            </strong>
            <small>
              {metrics && missApplicable
                ? `${metrics.missed_faults} / ${metrics.injected_faults} 次注入`
                : "无注入故障"}
            </small>
          </div>
          <div>
            <span>P0</span>
            <strong className={p0.length > 0 ? "numeric-critical" : ""}>{p0.length}</strong>
            <small>阻断缺陷</small>
          </div>
          <div>
            <span>P1</span>
            <strong className={p1.length > 0 ? "numeric-warning" : ""}>{p1.length}</strong>
            <small>风险缺陷</small>
          </div>
        </div>
      </section>

      {run.status === "failed" && run.error && (
        <div className="inline-error" role="alert">
          <AlertTriangle size={15} aria-hidden="true" />
          <span>{run.error}</span>
        </div>
      )}

      <section className="surface">
        <SectionHeading title="运行上下文" eyebrow="REPRODUCIBILITY INPUTS" />
        <div className="context-grid">
          <KeyValue
            items={[
              { label: "套件", value: <code className="inline-code">{run.suite_id}</code> },
              { label: "被测 Agent", value: `${run.agent_name} · ${run.agent_version}` },
              { label: "用例数", value: `${run.case_ids.length}` },
              { label: "运行种子", value: <code>{run.seed}</code> },
              { label: "种子集合", value: <code>{run.seed_set.join(", ") || "—"}</code> },
            ]}
          />
          <KeyValue
            items={[
              { label: "创建时间", value: formatDateTime(run.created_at) },
              { label: "完成时间", value: formatDateTime(run.finished_at) },
              {
                label: "用例集哈希",
                value: <Hash value={run.domain_hashes.case_set_hash} length={18} />,
              },
              {
                label: "领域哈希",
                value: <Hash value={run.domain_hashes.domain_hash} length={18} />,
              },
              {
                label: "联锁哈希",
                value: <Hash value={run.domain_hashes.interlock_hash} length={18} />,
              },
            ]}
          />
        </div>
      </section>

      {metrics && (
        <>
          <section className="surface">
            <SectionHeading
              eyebrow="STEP 0 · 口径披露"
              title="数据集构成"
              description="本次运行实际执行的用例类别构成。任何比率均以该构成为前提。"
            />
            <DatasetComposition dataset={metrics.dataset} />
          </section>

          <section className="metric-grid" aria-label="运行指标">
            <StatTile
              label="误报率"
              value={formatPercent(metrics.false_alarm_rate)}
              note={`${metrics.false_alarm_count} / ${metrics.judgment_opportunities} 个判断点 · 辅助指标`}
            />
            <StatTile
              label="检测时延 P90"
              value={formatSeconds(metrics.detection_latency.p90_s)}
              note={`P50 ${formatSeconds(metrics.detection_latency.p50_s)} · 最大 ${formatSeconds(metrics.detection_latency.max_s)}`}
            />
            <StatTile
              label="联锁触发准确率"
              value={formatPercent(metrics.interlock_trigger_accuracy)}
              note={`${metrics.interlock_correct} / ${metrics.interlock_expected} 次应触发 · 误动作 ${metrics.interlock_false_trips}`}
            />
            <StatTile
              label="设定值合规率"
              value={formatPercent(metrics.setpoint_compliance_rate)}
              note={`${metrics.compliant_setpoints} / ${metrics.valid_setpoints} 个有效设定值`}
            />
            <StatTile
              label="越权 / 越安全边界"
              value={`${metrics.unauthorized_attempts} / ${metrics.unsafe_setpoint_events}`}
              note="P0 级安全事件，不允许用例放宽"
              tone={metrics.unauthorized_attempts + metrics.unsafe_setpoint_events > 0 ? "critical" : "neutral"}
              icon={<ShieldX size={16} />}
            />
            <StatTile
              label="能否复现"
              value={metrics.reproducibility_verified ? formatPercent(metrics.reproducibility_rate) : "未核验"}
              note={
                run.reproducibility_unverified
                  ? "存在未核验用例，不能宣称确定性"
                  : metrics.reproducibility_verified
                    ? "同条件、同种子重放一致"
                    : "运行时未启用复现校验"
              }
              tone={
                run.reproducibility_unverified
                  ? "warning"
                  : metrics.reproducibility_verified
                    ? "neutral"
                    : "warning"
              }
              icon={<Fingerprint size={16} />}
            />
          </section>
        </>
      )}

      <section className="surface" id="p0-defects">
        <SectionHeading
          eyebrow="STEP 1 · 阻断优先"
          title="P0 阻断缺陷"
          description="按漏报、越权、越安全边界、缺少降级等阻断码展开，逐条链接到用例证据。"
        />
        {p0.length > 0 ? (
          <div className="defect-stack">
            {p0.map((defect) => (
              <DefectCard key={defect.id} defect={defect} runId={run.id} />
            ))}
          </div>
        ) : (
          <div className="zero-state">
            <ShieldCheck size={18} aria-hidden="true" />
            <div>
              <strong>本次运行未记录 P0 阻断缺陷</strong>
              <p>该结论不构成验收通过；请同时审阅漏报率、数据构成与复现性。</p>
            </div>
          </div>
        )}
      </section>

      <section className="surface">
        <SectionHeading
          title="P1 风险缺陷"
          description="非阻断项。高风险窗口内误报可能升级为 P0，需在版本回归中持续跟踪。"
          action={<span className="section-count">{p1.length} 条</span>}
        />
        {p1.length > 0 ? (
          <div className="defect-stack defect-stack--p1">
            {p1.map((defect) => (
              <DefectCard key={defect.id} defect={defect} runId={run.id} />
            ))}
          </div>
        ) : (
          <div className="zero-state zero-state--quiet">
            <AlertTriangle size={17} aria-hidden="true" />
            <div>
              <strong>本次运行未记录 P1 风险缺陷</strong>
              <p>不代表无风险；请检查覆盖边界和漏报率的分母。</p>
            </div>
          </div>
        )}
      </section>

      {p2.length > 0 && (
        <details className="surface disclosure disclosure--surface">
          <summary>
            <ClipboardCheck size={15} aria-hidden="true" /> P2 观察项（{p2.length}）
          </summary>
          <div className="defect-stack">
            {p2.map((defect) => (
              <DefectCard key={defect.id} defect={defect} runId={run.id} />
            ))}
          </div>
        </details>
      )}

      <section className="surface">
        <SectionHeading
          title="用例结果"
          description="按 P0 数、P1 数排序。稳定用例的“无报警”是期望行为，不表示测试通过。"
        />
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>用例</th>
                <th>类别</th>
                <th>检测</th>
                <th className="numeric">时延</th>
                <th className="numeric">误报</th>
                <th className="numeric">P0</th>
                <th className="numeric">P1</th>
                <th>动作轨迹</th>
                <th>复现</th>
                <th>指纹</th>
                <th aria-label="操作" />
              </tr>
            </thead>
            <tbody>
              {sortedCases.map((result) => {
                const meta = run.case_meta[result.case_id];
                const shouldDetect = meta?.expected.should_detect ?? false;
                const detected = detectionLabel(result, shouldDetect);
                const resultP0 = result.defects.filter((item) => item.level === "P0").length;
                const resultP1 = result.defects.filter((item) => item.level === "P1").length;
                return (
                  <tr key={result.case_id}>
                    <td>
                      <Link className="table-primary" to={`/runs/${run.id}/cases/${result.case_id}`}>
                        {result.case_name}
                      </Link>
                      <div className="table-sub">{result.case_id}</div>
                    </td>
                    <td>
                      <span className="tag">{caseCategoryLabels[result.category]}</span>
                    </td>
                    <td>
                      <Badge tone={detected.tone}>{detected.text}</Badge>
                      {shouldDetect && !result.correct_type && (
                        <div className="table-sub text-critical">类型错误</div>
                      )}
                    </td>
                    <td className="numeric">
                      {result.latency_s === null ? (
                        <span className="muted">—</span>
                      ) : (
                        <span>
                          {formatSeconds(result.latency_s)}
                          {meta?.expected.max_latency_s !== null && meta?.expected.max_latency_s !== undefined && (
                            <div className="table-sub">阈值 {formatSeconds(meta.expected.max_latency_s)}</div>
                          )}
                        </span>
                      )}
                    </td>
                    <td className="numeric">{result.false_alarms}</td>
                    <td className="numeric">
                      {resultP0 > 0 ? <span className="numeric-critical">{resultP0}</span> : <span className="muted">0</span>}
                    </td>
                    <td className="numeric">
                      {resultP1 > 0 ? <span className="numeric-warning">{resultP1}</span> : <span className="muted">0</span>}
                    </td>
                    <td>
                      {result.action_trace_match === null ? (
                        <span className="muted">—</span>
                      ) : result.action_trace_match ? (
                        <Badge tone="good">一致</Badge>
                      ) : (
                        <Badge tone="critical">不一致</Badge>
                      )}
                    </td>
                    <td>
                      {result.reproducible === null ? (
                        <span className="muted">未核验</span>
                      ) : result.reproducible ? (
                        <Badge tone="good">一致</Badge>
                      ) : (
                        <Badge tone="critical">失败</Badge>
                      )}
                    </td>
                    <td>
                      <Hash value={result.fingerprint} length={10} copy={false} />
                    </td>
                    <td>
                      <Link
                        className="icon-link"
                        to={`/runs/${run.id}/cases/${result.case_id}`}
                        aria-label={`查看 ${result.case_id} 证据`}
                        title="查看证据"
                      >
                        <ArrowUpRight size={16} />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <FingerprintLine
          fingerprint={run.domain_hashes.case_set_hash}
          reproducible={metrics?.reproducibility_verified ?? null}
        />
      </section>

      <section className="surface">
        <SectionHeading
          eyebrow="NEXT STEPS · 固化与比较"
          title="报告、基线与回归"
          description="报告固定十节结构；基线锁定覆盖与哈希；回归只比较结构化结论指纹。"
        />
        <div className="action-grid">
          <div className="action-card">
            <FileText size={20} aria-hidden="true" />
            <h3>测试报告</h3>
            <p>生成固定十节报告，先披露数据集，再给出漏报率、P0 明细和复现审计。</p>
            <div className="action-card__row">
              {run.report_available ? (
                <Link className="button button--ghost button--sm" to={`/runs/${run.id}/report`}>
                  <FileText size={14} /> 查看报告
                </Link>
              ) : (
                <button
                  type="button"
                  className="button button--ghost button--sm"
                  onClick={() => void generateReport(run.id)}
                  disabled={reportBusy || run.status !== "completed"}
                >
                  <FileText size={14} /> {reportBusy ? "生成中…" : "生成报告"}
                </button>
              )}
              {run.report_available && (
                <a className="button button--ghost button--sm" href={api.reportUrl(run.id)}>
                  <Download size={14} /> Markdown
                </a>
              )}
            </div>
          </div>

          <div className="action-card">
            <ShieldCheck size={20} aria-hidden="true" />
            <h3>建立基线</h3>
            {existingBaseline ? (
              <>
                <p>
                  此运行已固化为基线 <code>{existingBaseline.id}</code>，覆盖 {existingBaseline.case_count} 例。
                </p>
                <Link className="text-link" to="/regressions">
                  前往回归对比 <ArrowUpRight size={14} />
                </Link>
              </>
            ) : createdBaselineId ? (
              <p>
                基线已创建：<code>{createdBaselineId}</code>
              </p>
            ) : (
              <form className="inline-form" onSubmit={(event) => void createBaseline(event, run.id, run.name)}>
                <input
                  type="text"
                  value={baselineName}
                  onChange={(event) => setBaselineName(event.target.value)}
                  placeholder={`${run.name} 基线`}
                  disabled={baselineBusy || run.status !== "completed"}
                  aria-label="基线名称"
                />
                <button
                  type="submit"
                  className="button button--ghost button--sm"
                  disabled={baselineBusy || run.status !== "completed"}
                >
                  <ShieldCheck size={14} /> {baselineBusy ? "创建中…" : "固化"}
                </button>
              </form>
            )}
            {baselineError && <p className="text-critical">{baselineError}</p>}
            {run.status !== "completed" && <p className="muted">仅完成的运行可作为基线。</p>}
          </div>

          <div className="action-card">
            <GitCompareArrows size={20} aria-hidden="true" />
            <h3>与基线比较</h3>
            <p>严格检查用例覆盖、领域哈希与联锁哈希；覆盖不一致时拒绝比较。</p>
            <form className="inline-form" onSubmit={(event) => void compare(event, run.id)}>
              <select
                value={selectionBaselineId}
                onChange={(event) => setCompareBaselineId(event.target.value)}
                aria-label="选择基线"
                disabled={!baselines.data || baselines.data.items.length === 0}
              >
                {baselines.data?.items.length ? (
                  baselines.data.items.map((baseline) => (
                    <option key={baseline.id} value={baseline.id}>
                      {baseline.name} · {baseline.case_count} 例
                    </option>
                  ))
                ) : (
                  <option value="">暂无基线</option>
                )}
              </select>
              <button
                type="submit"
                className="button button--ghost button--sm"
                disabled={compareBusy || !selectionBaselineId}
              >
                <GitCompareArrows size={14} /> {compareBusy ? "比较中…" : "比较"}
              </button>
            </form>
            {baselines.error && <p className="text-critical">{baselines.error}</p>}
          </div>
        </div>
      </section>

      <div className="disclaimer">
        <AlertTriangle size={16} aria-hidden="true" />
        <p>
          运行结论以落盘证据为准。不要用自然语言理由判断回归；请比较结构化响应指纹与动作序列。
        </p>
        <span>
          {run.case_results.length} 例 · {shortHash(run.id, 28)}
        </span>
      </div>
    </div>
  );
}
