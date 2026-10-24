import {
  AlertTriangle,
  Database,
  Filter,
  FlaskConical,
  Play,
  RefreshCw,
  Search,
  Timer,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Badge, EmptyPanel, ErrorPanel, LoadingPanel, Tag } from "../components/ui";
import {
  caseCategoryLabels,
  dataSourceLabels,
  faultLabels,
  formatSeconds,
} from "../lib/format";
import { useAsync } from "../lib/useAsync";
import type { CaseCategory, CaseMeta, DataSource } from "../types";

export function CasesPage() {
  const navigate = useNavigate();
  const meta = useAsync(api.meta, []);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<CaseCategory | "">("");
  const [source, setSource] = useState<DataSource | "">("");
  const [agentId, setAgentId] = useState("mock-reference");
  const [busyCase, setBusyCase] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const cases = meta.data?.cases ?? [];
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return cases.filter((item) => {
      if (category && item.category !== category) {
        return false;
      }
      if (source && item.source !== source) {
        return false;
      }
      if (
        needle &&
        !`${item.id} ${item.name} ${item.description} ${item.tags.join(" ")}`
          .toLowerCase()
          .includes(needle)
      ) {
        return false;
      }
      return true;
    });
  }, [cases, category, source, search]);

  async function runCase(testCase: CaseMeta): Promise<void> {
    setBusyCase(testCase.id);
    setRunError(null);
    try {
      const run = await api.runCase(testCase.id, {
        agent_id: agentId,
        reproducibility_check: true,
      });
      navigate(`/runs/${run.id}`);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "用例执行失败。");
    } finally {
      setBusyCase(null);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <div className="page-eyebrow">SCENARIO CATALOG</div>
          <h1 className="page-title">测试用例</h1>
          <p className="page-description">
            每条用例显式标注数据来源与 provenance。单独执行用于调试，不自动建立基线。
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="button button--ghost" onClick={meta.reload} disabled={meta.refreshing}>
            <RefreshCw size={15} className={meta.refreshing ? "spin" : ""} /> 刷新
          </button>
        </div>
      </header>

      <section className="surface">
        <div className="case-toolbar">
          <div className="filter-row">
            <label className="search-field">
              <Search size={15} aria-hidden="true" />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索用例 ID、名称或标签"
                aria-label="搜索用例"
              />
            </label>
            <label className="select-field">
              <Filter size={14} aria-hidden="true" />
              <select
                value={category}
                onChange={(event) => setCategory(event.target.value as CaseCategory | "")}
                aria-label="按类别筛选"
              >
                <option value="">全部类别</option>
                <option value="steady">稳态</option>
                <option value="fault">故障</option>
                <option value="boundary">边界</option>
                <option value="interlock">联锁闭环</option>
              </select>
            </label>
            <label className="select-field">
              <select
                value={source}
                onChange={(event) => setSource(event.target.value as DataSource | "")}
                aria-label="按数据来源筛选"
              >
                <option value="">全部来源</option>
                <option value="real_history">真实历史</option>
                <option value="simulation">仿真</option>
                <option value="mechanistic">机理构造</option>
              </select>
            </label>
          </div>
          <div className="case-toolbar__agent">
            <label className="select-field">
              <span className="select-field__label">执行 Agent</span>
              <select
                value={agentId}
                onChange={(event) => setAgentId(event.target.value)}
                aria-label="选择执行 Agent"
              >
                {meta.data?.agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name} · {agent.version}
                  </option>
                ))}
              </select>
            </label>
            <span className="table-count">{filtered.length} / {cases.length} 条用例</span>
          </div>
        </div>

        {runError && (
          <div className="inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" />
            <span>{runError}</span>
          </div>
        )}

        {meta.loading && <LoadingPanel label="正在读取用例目录…" />}
        {meta.error && !meta.data && <ErrorPanel message={meta.error} onRetry={meta.reload} />}
        {meta.data && filtered.length === 0 && (
          <EmptyPanel
            title="没有匹配的用例"
            description="调整搜索词或筛选条件。"
            icon={<FlaskConical size={22} />}
          />
        )}

        {filtered.length > 0 && (
          <div className="case-grid">
            {filtered.map((testCase) => {
              const expected = testCase.expected;
              return (
                <article
                  key={testCase.id}
                  className={`case-card case-card--${testCase.category}`}
                >
                  <div className="case-card__head">
                    <span className="case-card__id">{testCase.id}</span>
                    <Tag>{caseCategoryLabels[testCase.category]}</Tag>
                    <span className="source-badge">
                      <Database size={12} aria-hidden="true" />
                      {dataSourceLabels[testCase.source]}
                    </span>
                  </div>
                  <h2>{testCase.name}</h2>
                  <p className="case-card__description">{testCase.description}</p>

                  <div className="case-card__facts">
                    <div>
                      <span>时长</span>
                      <strong>{formatSeconds(testCase.duration_s)}</strong>
                    </div>
                    <div>
                      <span>判定间隔</span>
                      <strong>{formatSeconds(testCase.decision_interval_s)}</strong>
                    </div>
                    <div>
                      <span>Seed</span>
                      <strong><code>{testCase.seed}</code></strong>
                    </div>
                    <div>
                      <span>注入</span>
                      <strong>{testCase.faults.length} 项</strong>
                    </div>
                  </div>

                  <div className="case-card__expected">
                    {expected.should_detect ? (
                      <Badge tone="warning">
                        应识别 · {expected.fault_type ? faultLabels[expected.fault_type] : "未声明类型"}
                      </Badge>
                    ) : (
                      <Badge tone="neutral">不要求故障识别</Badge>
                    )}
                    {expected.expect_attention && <Badge tone="info">边界关注</Badge>}
                    {expected.require_degraded_response && <Badge tone="serious">要求安全降级</Badge>}
                    {expected.max_latency_s !== null && (
                      <span className="case-card__latency">
                        <Timer size={13} aria-hidden="true" />
                        时延 ≤ {formatSeconds(expected.max_latency_s)}
                      </span>
                    )}
                  </div>

                  {testCase.faults.length > 0 && (
                    <div className="value-chips">
                      {testCase.faults.map((fault, index) => (
                        <span className="value-chip" key={`${fault.kind}-${index}`}>
                          <code>{fault.kind}</code>
                          {fault.target_tag} · {formatSeconds(fault.start_s)}
                        </span>
                      ))}
                    </div>
                  )}

                  <p className="case-card__provenance" title={testCase.provenance}>
                    <Database size={13} aria-hidden="true" />
                    {testCase.provenance}
                  </p>

                  <div className="case-card__foot">
                    <div className="case-tags">
                      {testCase.tags.map((tag) => (
                        <Tag key={tag}>{tag}</Tag>
                      ))}
                    </div>
                    <button
                      type="button"
                      className="button button--ghost button--sm"
                      onClick={() => void runCase(testCase)}
                      disabled={busyCase !== null}
                      title={`使用 ${agentId} 单独执行`}
                    >
                      <Play size={14} /> {busyCase === testCase.id ? "执行中…" : "单独执行"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <div className="disclaimer">
        <AlertTriangle size={16} aria-hidden="true" />
        <p>
          用例 provenance 属于证据链的一部分。仿真/机理构造数据不能冒充真实历史数据；缺失机理依据时以 TODO(mechanism) 显式披露。
        </p>
      </div>
    </div>
  );
}
