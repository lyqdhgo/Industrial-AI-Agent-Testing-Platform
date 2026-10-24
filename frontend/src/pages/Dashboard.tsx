import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Clock3,
  DatabaseZap,
  Fingerprint,
  GitCompareArrows,
  Play,
  RefreshCw,
  ShieldCheck,
  ShieldX,
  Timer,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { DatasetComposition, DigestDefectCard, StatTile } from "../components/data";
import { RunTable } from "../components/RunTable";
import {
  Badge,
  EmptyPanel,
  ErrorPanel,
  Hash,
  LoadingPanel,
  SectionHeading,
} from "../components/ui";
import {
  formatDateTime,
  formatNumber,
  formatPercent,
  formatSeconds,
  shortHash,
} from "../lib/format";
import { runP0 } from "../lib/runs";
import { useAsync } from "../lib/useAsync";

export function DashboardPage() {
  const dashboard = useAsync(api.dashboard, [], 5000);

  if (dashboard.loading) {
    return (
      <div className="page">
        <header className="page-header">
          <div>
            <div className="page-eyebrow">TOTAL OVERVIEW</div>
            <h1 className="page-title">测试总览</h1>
          </div>
        </header>
        <LoadingPanel label="正在汇总运行、缺陷与回归证据…" />
      </div>
    );
  }

  if (dashboard.error && !dashboard.data) {
    return (
      <div className="page">
        <header className="page-header">
          <div>
            <div className="page-eyebrow">TOTAL OVERVIEW</div>
            <h1 className="page-title">测试总览</h1>
          </div>
        </header>
        <ErrorPanel message={dashboard.error} onRetry={dashboard.reload} />
      </div>
    );
  }

  const data = dashboard.data;
  if (!data || !data.hero_run || !data.metrics) {
    return (
      <div className="page">
        <header className="page-header">
          <div>
            <div className="page-eyebrow">TOTAL OVERVIEW</div>
            <h1 className="page-title">测试总览</h1>
            <p className="page-description">
              漏报优先的工业 Agent 评测视图。所有数字来自落盘证据，不展示未经验证的“通过率”。
            </p>
          </div>
          <div className="page-actions">
            <button type="button" className="button button--ghost" onClick={dashboard.reload}>
              <RefreshCw size={15} /> 刷新
            </button>
          </div>
        </header>
        <EmptyPanel
          icon={<DatabaseZap size={26} className={data?.seed_running ? "spin-slow" : ""} />}
          title={data?.seed_running ? "演示数据初始化中" : "尚无运行记录"}
          description={
            data?.seed_running
              ? "正在后台生成基准、退化回归与越权门禁验证运行。本页会自动刷新；也可稍后手动刷新。"
              : "请先在运行记录页创建第一次测试运行。"
          }
          action={
            data?.seed_running ? (
              <button type="button" className="button button--ghost" onClick={dashboard.reload}>
                <RefreshCw size={15} /> 立即刷新
              </button>
            ) : (
              <Link className="button button--primary" to="/runs">
                <Play size={15} /> 前往运行记录
              </Link>
            )
          }
        />
      </div>
    );
  }

  const { hero_run: run, metrics, latest_baseline: baseline, latest_regression: regression } = data;
  const isBaselineSnapshot = baseline?.run_id === run.id;
  const missApplicable = metrics.injected_faults > 0;
  const hasMiss = metrics.missed_faults > 0;
  const otherP0Runs = data.runs.filter((item) => item.id !== run.id && runP0(item) > 0);
  const recentP0Total = otherP0Runs.reduce((total, item) => total + runP0(item), 0);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <div className="page-eyebrow">TOTAL OVERVIEW</div>
          <h1 className="page-title">测试总览</h1>
          <p className="page-description">
            漏报优先的工业 Agent 评测视图。所有数字来自落盘证据，不展示未经验证的“通过率”。
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="button button--ghost"
            onClick={dashboard.reload}
            disabled={dashboard.refreshing}
          >
            <RefreshCw size={15} className={dashboard.refreshing ? "spin" : ""} />
            {dashboard.refreshing ? "刷新中" : "刷新"}
          </button>
          <Link className="button button--primary" to="/runs">
            <Play size={15} /> 新建运行
          </Link>
        </div>
      </header>

      {dashboard.error && (
        <div className="inline-warning">
          <AlertTriangle size={15} aria-hidden="true" />
          <span>自动刷新失败，当前展示上次成功读取的数据：{dashboard.error}</span>
        </div>
      )}

      <section className="run-context" aria-label="当前数据上下文">
        <div className="run-context__lead">
          <span className="run-context__label">{isBaselineSnapshot ? "基准运行快照" : "最近完成运行"}</span>
          <Link to={`/runs/${run.id}`} className="run-context__title">
            {run.name}
            <ArrowUpRight size={14} />
          </Link>
        </div>
        <div className="run-context__item">
          <span>被测 Agent</span>
          <strong>
            {run.agent_name} · {run.agent_version}
          </strong>
        </div>
        <div className="run-context__item">
          <span>套件</span>
          <strong>{run.suite_id}</strong>
        </div>
        <div className="run-context__item">
          <span>用例 / 种子</span>
          <strong>
            {run.case_count} 例 · {run.seed_set.length} seeds
          </strong>
        </div>
        <div className="run-context__item">
          <span>完成时间</span>
          <strong>{formatDateTime(run.finished_at ?? run.created_at)}</strong>
        </div>
        <Badge tone={run.status === "completed" ? "good" : run.status === "failed" ? "critical" : "info"}>
          {run.status === "completed" ? "运行已完成" : run.status === "failed" ? "运行失败" : "运行中"}
        </Badge>
      </section>

      <section className="surface">
        <SectionHeading
          eyebrow="STEP 0 · 口径披露"
          title="数据集构成"
          description="先披露用例构成与来源，再解读任何比率。故障占比不足时，漏报率的分母本身需要被质询。"
        />
        <DatasetComposition dataset={metrics.dataset} />
        <div className="source-note">
          <Fingerprint size={14} aria-hidden="true" />
          <span>用例集指纹</span>
          <Hash value={data.catalog.case_set_hash} length={16} />
          <span className="dot-sep" aria-hidden="true" />
          <span>{data.catalog.case_count} 例 · {data.catalog.agent_count} 个 Agent · {data.catalog.suite_count} 个套件</span>
        </div>
      </section>

      <section className="overview-hero" aria-labelledby="hero-miss-rate">
        <div className="overview-hero__main">
          <div className="hero-kicker">
            <span id="hero-miss-rate">首要指标 · 漏报率</span>
            <Badge tone={hasMiss ? "critical" : "neutral"}>
              {!missApplicable ? "不适用" : hasMiss ? "存在漏报" : "未观测到漏报"}
            </Badge>
          </div>
          <div className={`hero-number${hasMiss ? " hero-number--critical" : ""}`}>
            {missApplicable ? formatPercent(metrics.miss_rate, 1) : "—"}
          </div>
          <p className="hero-sub">
            {missApplicable
              ? `${metrics.missed_faults} / ${metrics.injected_faults} 次注入故障被漏报`
              : "本运行没有注入故障，漏报率不适用"}
          </p>
          <p className="hero-note">
            漏报率是首要阻断指标，F1 与误报率只作辅助判断。
            {hasMiss
              ? " 本运行已记录漏报，应按 P0 级缺陷追溯检测逻辑与降级行为。"
              : " 0% 不代表验收通过：仍须审阅 P0/P1、数据构成、注入有效性与复现性。"}
          </p>
          <div className="hero-meta">
            <span>
              <Timer size={13} aria-hidden="true" /> 判定机会 {metrics.judgment_opportunities}
            </span>
            <span>
              <ShieldCheck size={13} aria-hidden="true" /> 联锁应触发 {metrics.interlock_expected} 次
            </span>
            <span>
              <Fingerprint size={13} aria-hidden="true" /> 复现率{" "}
              {metrics.reproducibility_verified
                ? formatPercent(metrics.reproducibility_rate)
                : "未核验"}
            </span>
          </div>
        </div>

        <div className="overview-hero__side">
          <StatTile
            label="P0 阻断缺陷"
            value={String(metrics.defects_p0)}
            note={metrics.defects_p0 > 0 ? "含漏报、越权或越安全边界" : "本次运行未记录"}
            tone={metrics.defects_p0 > 0 ? "critical" : "neutral"}
            icon={<ShieldX size={17} />}
          />
          <StatTile
            label="P1 风险缺陷"
            value={String(metrics.defects_p1)}
            note="误报、偏离推荐区间等"
            tone={metrics.defects_p1 > 0 ? "warning" : "neutral"}
            icon={<AlertTriangle size={17} />}
          />
          <StatTile
            label="高风险期误报"
            value={String(metrics.high_risk_false_alarms)}
            note="高风险窗口内误报可升为 P0"
            tone={metrics.high_risk_false_alarms > 0 ? "serious" : "neutral"}
            icon={<Clock3 size={17} />}
          />
        </div>
      </section>

      <section className="metric-grid" aria-label="辅助指标">
        <StatTile
          label="误报率"
          value={formatPercent(metrics.false_alarm_rate)}
          note={`${metrics.false_alarm_count} / ${metrics.judgment_opportunities} 个判断点 · 辅助指标`}
          icon={<AlertTriangle size={16} />}
        />
        <StatTile
          label="检测时延 P90"
          value={formatSeconds(metrics.detection_latency.p90_s)}
          note={`样本 ${metrics.detection_latency.sample_count} 次检测`}
          icon={<Timer size={16} />}
        />
        <StatTile
          label="联锁触发准确率"
          value={formatPercent(metrics.interlock_trigger_accuracy)}
          note={`${metrics.interlock_correct} / ${metrics.interlock_expected} 次应触发 · 误动作 ${metrics.interlock_false_trips}`}
          icon={<ShieldCheck size={16} />}
        />
        <StatTile
          label="设定值合规率"
          value={formatPercent(metrics.setpoint_compliance_rate)}
          note={`${metrics.compliant_setpoints} / ${metrics.valid_setpoints} 个有效设定值`}
        />
        <StatTile
          label="越权 / 越安全边界"
          value={`${metrics.unauthorized_attempts} / ${metrics.unsafe_setpoint_events}`}
          note="均应按 P0 取证，不进入普通异常分支"
          tone={metrics.unauthorized_attempts + metrics.unsafe_setpoint_events > 0 ? "critical" : "neutral"}
          icon={<ShieldX size={16} />}
        />
        <StatTile
          label="运行可复现性"
          value={metrics.reproducibility_verified ? formatPercent(metrics.reproducibility_rate) : "未核验"}
          note={
            metrics.reproducibility_verified
              ? "同条件 + 同种子已重放"
              : "未启用复现校验，不可宣称确定性"
          }
          tone={metrics.reproducibility_verified ? "neutral" : "warning"}
          icon={<Fingerprint size={16} />}
        />
      </section>

      <section className="surface" aria-labelledby="p0-section">
        <SectionHeading
          eyebrow="STEP 1 · 阻断优先"
          title="P0 阻断缺陷"
          description="漏报、越权控制、越安全边界与缺少安全降级优先展示于此，不按时间或用例编号排序。"
        />
        {data.p0_defects.length > 0 ? (
          <div className="defect-stack">
            {data.p0_defects.map((defect) => (
              <DigestDefectCard key={`${defect.case_id}-${defect.code}`} defect={defect} runId={run.id} />
            ))}
          </div>
        ) : (
          <div className="zero-state">
            <ShieldCheck size={18} aria-hidden="true" />
            <div>
              <strong>当前运行未记录 P0 阻断缺陷</strong>
              <p>该表述仅适用于本运行与本数据集，不构成验收通过结论。</p>
            </div>
          </div>
        )}

        {otherP0Runs.length > 0 && (
          <div className="cross-run-p0">
            <div className="cross-run-p0__head">
              <h3>其他近期运行的 P0 取证</h3>
              <span>{recentP0Total} 条 P0，不计入当前运行指标</span>
            </div>
            <div className="run-flag-list">
              {otherP0Runs.map((item) => (
                <Link key={item.id} className="run-flag" to={`/runs/${item.id}`}>
                  <Badge tone="critical">P0 × {runP0(item)}</Badge>
                  <div>
                    <strong>{item.agent_name}</strong>
                    <span>
                      {item.name} · {item.suite_id} · {formatDateTime(item.finished_at ?? item.created_at)}
                    </span>
                  </div>
                  <ArrowUpRight size={15} aria-hidden="true" />
                </Link>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="surface">
        <SectionHeading
          title="P1 风险缺陷"
          description="非阻断，但需纳入版本对比观察；高风险期误报可能升级为 P0。"
          action={<span className="section-count">{metrics.defects_p1} 条</span>}
        />
        {data.p1_defects.length > 0 ? (
          <div className="defect-stack defect-stack--p1">
            {data.p1_defects.map((defect) => (
              <DigestDefectCard key={`${defect.case_id}-${defect.code}`} defect={defect} runId={run.id} />
            ))}
          </div>
        ) : (
          <div className="zero-state zero-state--quiet">
            <AlertTriangle size={17} aria-hidden="true" />
            <div>
              <strong>当前运行未记录 P1 风险缺陷</strong>
              <p>不代表无风险；请检查覆盖率与漏报率的分母。</p>
            </div>
          </div>
        )}
      </section>

      <div className="two-column">
        <section className="surface">
          <SectionHeading
            title="最近回归"
            eyebrow="VERSION DELTA"
            action={
              <Link className="text-link" to="/regressions">
                全部回归 <ArrowRight size={14} />
              </Link>
            }
          />
          {regression ? (
            <div className="regression-summary">
              <div className="regression-summary__top">
                <Badge tone={regression.comparable ? "info" : "critical"}>
                  {regression.comparable ? "覆盖与哈希可比" : "不可比"}
                </Badge>
                <span className="muted">{formatDateTime(regression.created_at)}</span>
              </div>
              <div className="regression-stats">
                <div>
                  <strong className={regression.severe_regressions.length > 0 ? "numeric-critical" : ""}>
                    {regression.severe_regressions.length}
                  </strong>
                  <span>严重回归</span>
                </div>
                <div>
                  <strong>{regression.unexpected_changes.length}</strong>
                  <span>非预期变化</span>
                </div>
                <div>
                  <strong>{formatPercent(regression.fingerprint_match_rate)}</strong>
                  <span>指纹一致率</span>
                </div>
              </div>
              <p className="regression-summary__note">
                候选运行 {shortHash(regression.candidate_run_id, 20)} · 基线 {shortHash(regression.baseline_id, 20)}
              </p>
              <Link className="button button--ghost button--sm" to={`/regressions?report=${regression.id}`}>
                <GitCompareArrows size={14} /> 审阅回归
              </Link>
            </div>
          ) : (
            <EmptyPanel
              title="尚无回归报告"
              description="建立基线后，可将候选运行与基线比较指纹与 P0 变化。"
              action={
                <Link className="button button--ghost button--sm" to="/regressions">
                  前往回归对比
                </Link>
              }
            />
          )}
        </section>

        <section className="surface">
          <SectionHeading title="基线状态" eyebrow="BASELINE" />
          {baseline ? (
            <div className="baseline-summary">
              <div className="baseline-summary__name">
                <ShieldCheck size={17} aria-hidden="true" />
                <div>
                  <strong>{baseline.name}</strong>
                  <span>{baseline.agent_version} · {baseline.case_count} 例</span>
                </div>
              </div>
              <dl className="baseline-facts">
                <div>
                  <dt>P0 缺陷</dt>
                  <dd className={baseline.p0 > 0 ? "numeric-critical" : ""}>{baseline.p0}</dd>
                </div>
                <div>
                  <dt>建立时间</dt>
                  <dd>{formatDateTime(baseline.created_at)}</dd>
                </div>
                <div>
                  <dt>联锁哈希</dt>
                  <dd><Hash value={baseline.interlock_hash} length={10} copy={false} /></dd>
                </div>
                <div>
                  <dt>领域哈希</dt>
                  <dd><Hash value={baseline.domain_hash} length={10} copy={false} /></dd>
                </div>
              </dl>
              <Link className="text-link" to={`/runs/${baseline.run_id}`}>
                查看基线运行 <ArrowRight size={14} />
              </Link>
            </div>
          ) : (
            <EmptyPanel
              title="尚未建立基线"
              description="在运行详情页可将一次完成的运行固化为基线。"
            />
          )}
        </section>
      </div>

      <section className="surface">
        <SectionHeading
          title="最近运行"
          description="最近 8 次运行；指标仅在同套件、同覆盖范围内可直接比较。"
          action={
            <Link className="text-link" to="/runs">
              全部运行 <ArrowRight size={14} />
            </Link>
          }
        />
        <RunTable runs={data.runs} compact />
      </section>

      <div className="disclaimer">
        <AlertTriangle size={16} aria-hidden="true" />
        <p>
          演示域为合成机理数据，不代表真实装置工程数据；不得据此签发安全认证。数据集不均衡时，任何单一比率都不能独立支撑上线决策。
        </p>
        <span>{formatNumber(data.runs.length, 0)} 次运行 · 自动刷新 5 s</span>
      </div>
    </div>
  );
}
