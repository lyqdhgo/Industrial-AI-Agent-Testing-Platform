import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Ban,
  Bot,
  Database,
  Fingerprint,
  Lock,
  Server,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Badge, EmptyPanel, ErrorPanel, Hash, LoadingPanel, SectionHeading } from "../components/ui";
import {
  actionLabels,
  dataSourceLabels,
  formatDateTime,
  formatNumber,
  formatUnit,
} from "../lib/format";
import { runP0 } from "../lib/runs";
import { useAsync } from "../lib/useAsync";

export function SafetyPage() {
  const meta = useAsync(api.meta, []);
  const safetyRuns = useAsync(
    () => api.listRuns({ suite_id: "suite-safety-guard", limit: 1 }),
    [],
  );

  if (meta.loading) {
    return (
      <div className="page">
        <LoadingPanel label="正在读取联锁与工艺边界定义…" />
      </div>
    );
  }
  if (meta.error || !meta.data) {
    return (
      <div className="page">
        <ErrorPanel message={meta.error ?? "域定义不可用"} onRetry={meta.reload} />
      </div>
    );
  }

  const domain = meta.data.domain;
  const safetyRun = safetyRuns.data?.items[0] ?? null;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <div className="page-eyebrow">SAFETY BOUNDARY · READ ONLY</div>
          <h1 className="page-title">安全与联锁</h1>
          <p className="page-description">
            Agent 输出只是建议。权限、工艺边界、人工确认与 SIS 联锁共同构成不可绕过的控制边界。
          </p>
        </div>
        <div className="page-actions">
          <Badge tone="info">配置只读</Badge>
        </div>
      </header>

      <section className="surface">
        <SectionHeading
          eyebrow="PERMISSION FLOW"
          title="控制链路：Agent 永远不能直写 DCS"
          description="所有控制请求由 SafetyGate 顺序校验；联锁引擎独立读取真实过程值，不接受 Agent 配置或测试用例旁路。"
        />
        <div className="safety-architecture">
          <div className="arch-node arch-node--agent">
            <Bot size={22} aria-hidden="true" />
            <strong>被测 Agent</strong>
            <span>不可信建议源</span>
            <small>结构化建议 + 自然语言理由</small>
          </div>
          <div className="arch-connector" aria-hidden="true">
            <span>建议</span>
            <ArrowRight size={18} />
          </div>
          <div className="arch-gate">
            <div className="arch-gate__head">
              <Lock size={18} aria-hidden="true" />
              <strong>SafetyGate</strong>
            </div>
            <ol>
              <li><span>01</span> 权限与可写位号</li>
              <li><span>02</span> 仪表量程 → 工艺安全边界</li>
              <li><span>03</span> 高风险操作人工确认</li>
              <li><span>04</span> SIS 已动作则阻断</li>
            </ol>
            <small>任何一层拒绝：记录 GATE_BLOCKED，不调用 DCS 回调。</small>
          </div>
          <div className="arch-connector" aria-hidden="true">
            <span>放行</span>
            <ArrowRight size={18} />
          </div>
          <div className="arch-node arch-node--dcs">
            <Server size={22} aria-hidden="true" />
            <strong>DCS / PLC 执行层</strong>
            <span>仿真写入桩</span>
            <small>仅在门禁放行后调用</small>
          </div>
        </div>

        <div className="sis-band">
          <div className="sis-band__title">
            <ShieldAlert size={18} aria-hidden="true" />
            <strong>SIS 独立联锁引擎</strong>
            <Badge tone="info">不受 Agent 控制</Badge>
          </div>
          <p>
            联锁基于仿真真实值独立判断，与 Agent 输出解耦。联锁动作不依赖 DCS 设定值，也不会因为测试用例声明而被禁用、旁路或放宽。
          </p>
          <div className="sis-actions">
            {meta.data.interlocks.map((rule) => (
              <span key={rule.id}>
                <code>{rule.id}</code>
                {actionLabels[rule.action]}
              </span>
            ))}
          </div>
        </div>

        <div className="safety-nonnegotiables">
          <div>
            <Ban size={17} aria-hidden="true" />
            <strong>不提供</strong>
            <span>联锁配置、旁路申请批准、DCS 直写 API</span>
          </div>
          <div>
            <ShieldCheck size={17} aria-hidden="true" />
            <strong>不变量</strong>
            <span>联锁哈希进入基线；覆盖或哈希不一致时拒绝回归比较</span>
          </div>
          <div>
            <Fingerprint size={17} aria-hidden="true" />
            <strong>取证</strong>
            <span>每个门禁决策、动作轨迹与 SIS 触发均落入证据目录</span>
          </div>
        </div>
      </section>

      <div className="two-column two-column--wide-left">
        <section className="surface">
          <SectionHeading
            eyebrow="INTERLOCK TABLE"
            title="联锁规则"
            description="高高限联锁基于测量值触发；两条规则均为不可旁路硬约束。"
            action={<span className="section-count">{meta.data.interlocks.length} 条</span>}
          />
          <div className="interlock-list">
            {meta.data.interlocks.map((rule) => {
              const high = rule.trip_limit.high;
              const low = rule.trip_limit.low;
              const threshold =
                high !== null
                  ? `测量值 ≥ ${formatNumber(high, 1)} ${formatUnit(rule.trip_limit.unit)}`
                  : `测量值 ≤ ${formatNumber(low, 1)} ${formatUnit(rule.trip_limit.unit)}`;
              return (
                <article className="interlock-card" key={rule.id}>
                  <div className="interlock-card__head">
                    <div>
                      <code className="interlock-card__id">{rule.id}</code>
                      <h3>{rule.name}</h3>
                    </div>
                    <Badge tone="info">硬联锁 · 不可旁路</Badge>
                  </div>
                  <div className="interlock-card__grid">
                    <div>
                      <span>触发位号</span>
                      <strong>{rule.tag}</strong>
                    </div>
                    <div>
                      <span>触发条件</span>
                      <strong>{threshold}</strong>
                    </div>
                    <div>
                      <span>执行动作</span>
                      <strong>{actionLabels[rule.action]}</strong>
                    </div>
                    <div>
                      <span>执行层</span>
                      <strong>{rule.layer.toUpperCase()}</strong>
                    </div>
                  </div>
                  <p className="interlock-card__note">{rule.note || "未附补充说明。"}</p>
                  <code className="interlock-card__condition">{rule.condition}</code>
                </article>
              );
            })}
          </div>
        </section>

        <aside className="aside-stack">
          <section className="surface">
            <SectionHeading eyebrow="SAFETY EVIDENCE" title="越权门禁取证" />
            {safetyRuns.loading && <LoadingPanel label="正在读取安全套件运行…" />}
            {safetyRuns.error && <ErrorPanel message={safetyRuns.error} onRetry={safetyRuns.reload} />}
            {safetyRuns.data && !safetyRun && (
              <EmptyPanel title="尚无安全门禁运行" description="执行 suite-safety-guard 以生成越权与门禁证据。" />
            )}
            {safetyRun && (
              <div className="safety-run-card">
                <div className="safety-run-card__top">
                  <Badge tone={runP0(safetyRun) > 0 ? "critical" : "neutral"}>
                    P0 × {runP0(safetyRun)}
                  </Badge>
                  <span className="muted">{formatDateTime(safetyRun.finished_at ?? safetyRun.created_at)}</span>
                </div>
                <strong>{safetyRun.agent_name}</strong>
                <p>
                  {safetyRun.name} · {safetyRun.case_count} 例
                </p>
                <p className="muted">
                  这些 P0 证明平台成功识别并阻断了越权建议，不表示被测 Agent 可上线。
                </p>
                <Link className="button button--ghost button--sm" to={`/runs/${safetyRun.id}`}>
                  查看取证 <ArrowUpRight size={14} />
                </Link>
              </div>
            )}
          </section>

          <section className="surface">
            <SectionHeading eyebrow="DOMAIN HASHES" title="安全基线指纹" />
            <div className="hash-stack">
              <div>
                <span>联锁哈希</span>
                <Hash value={domain.hashes.interlock_hash} length={22} />
              </div>
              <div>
                <span>领域哈希</span>
                <Hash value={domain.hashes.domain_hash} length={22} />
              </div>
              <div>
                <span>用例集哈希</span>
                <Hash value={domain.hashes.case_set_hash} length={22} />
              </div>
            </div>
            <p className="muted hash-stack__note">
              任何联锁表改动都会改变哈希，使旧基线与候选运行拒绝比较。
            </p>
          </section>
        </aside>
      </div>

      <section className="surface">
        <SectionHeading
          eyebrow="PROCESS BOUNDS"
          title="仪表量程与工艺边界"
          description="所有阈值来自域定义文件，不在评测代码中硬编码。推荐区间必须完整位于安全边界内。"
        />
        <div className="table-wrap">
          <table className="data-table bounds-table">
            <thead>
              <tr>
                <th>测点</th>
                <th>仪表量程</th>
                <th>安全边界</th>
                <th>推荐区间</th>
                <th>联锁阈值</th>
                <th className="numeric">采样</th>
              </tr>
            </thead>
            <tbody>
              {meta.data.sensors.map((sensor) => (
                <tr key={sensor.tag}>
                  <td>
                    <div className="table-primary">{sensor.tag}</div>
                    <div className="table-sub">{sensor.name}</div>
                    <div className={`mechanism-basis${sensor.mechanism_basis.includes("TODO(mechanism)") ? " mechanism-basis--todo" : ""}`}>
                      {sensor.mechanism_basis}
                    </div>
                  </td>
                  <td>
                    {formatNumber(sensor.range.low, 1)} – {formatNumber(sensor.range.high, 1)}{" "}
                    {formatUnit(sensor.unit)}
                  </td>
                  <td>
                    {formatNumber(sensor.safe_limits.low, 1)} – {formatNumber(sensor.safe_limits.high, 1)}{" "}
                    {formatUnit(sensor.unit)}
                  </td>
                  <td>
                    {formatNumber(sensor.recommended_band.low, 1)} –{" "}
                    {formatNumber(sensor.recommended_band.high, 1)} {formatUnit(sensor.unit)}
                  </td>
                  <td>
                    {sensor.trip_limits.high !== null
                      ? `≥ ${formatNumber(sensor.trip_limits.high, 1)} ${formatUnit(sensor.trip_limits.unit)}`
                      : sensor.trip_limits.low !== null
                        ? `≤ ${formatNumber(sensor.trip_limits.low, 1)} ${formatUnit(sensor.trip_limits.unit)}`
                        : "—"}
                  </td>
                  <td className="numeric">{formatNumber(sensor.sample_interval_s, 0)} s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="surface">
        <SectionHeading eyebrow="ASSUMPTIONS & DISCLOSURE" title="域假设与数据声明" />
        <div className="assumption-grid">
          <div className="assumption-card">
            <Database size={18} aria-hidden="true" />
            <h3>数据来源</h3>
            <p>{domain.disclaimer}</p>
            <Badge tone="info">Provenance · {dataSourceLabels[domain.provenance]}</Badge>
          </div>
          <div className="assumption-card">
            <AlertTriangle size={18} aria-hidden="true" />
            <h3>已知假设与缺口</h3>
            {domain.assumptions.length > 0 ? (
              <ul>
                {domain.assumptions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">域包未声明额外假设。</p>
            )}
          </div>
        </div>
      </section>

      <div className="disclaimer">
        <AlertTriangle size={16} aria-hidden="true" />
        <p>
          本页面为只读安全配置视图，不提供联锁修改、旁路审批或 DCS 写入入口。演示域不是真实装置，不得据此签发安全认证。
        </p>
      </div>
    </div>
  );
}
