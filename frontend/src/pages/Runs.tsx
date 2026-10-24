import { AlertTriangle, Filter, Play, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { RunTable } from "../components/RunTable";
import { EmptyPanel, ErrorPanel, Field, LoadingPanel } from "../components/ui";
import { useAsync } from "../lib/useAsync";

export function RunsPage() {
  const navigate = useNavigate();
  const runs = useAsync(api.listRuns, [], 10000);
  const suites = useAsync(api.suites, []);
  const agents = useAsync(api.agents, []);

  const [suiteId, setSuiteId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [seed, setSeed] = useState("");
  const [reproducibility, setReproducibility] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [suiteFilter, setSuiteFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");

  useEffect(() => {
    if (!suiteId && suites.data && suites.data.length > 0) {
      setSuiteId(suites.data[0]?.id ?? "");
    }
  }, [suiteId, suites.data]);

  const selectedSuite = suites.data?.find((suite) => suite.id === suiteId) ?? null;

  const filteredRuns = useMemo(() => {
    const items = runs.data?.items ?? [];
    const needle = search.trim().toLowerCase();
    return items.filter((run) => {
      if (suiteFilter && run.suite_id !== suiteFilter) {
        return false;
      }
      if (agentFilter && run.agent_id !== agentFilter) {
        return false;
      }
      if (
        needle &&
        !`${run.name} ${run.id} ${run.agent_name} ${run.suite_id}`
          .toLowerCase()
          .includes(needle)
      ) {
        return false;
      }
      return true;
    });
  }, [runs.data, search, suiteFilter, agentFilter]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!suiteId) {
      setFormError("请选择要执行的测试套件。");
      return;
    }
    const parsedSeed = seed.trim() === "" ? null : Number(seed);
    if (parsedSeed !== null && (!Number.isInteger(parsedSeed) || parsedSeed < 0)) {
      setFormError("种子必须是非负整数。");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const result = await api.runSuite({
        suite_id: suiteId,
        agent_ids: agentId ? [agentId] : null,
        seed: parsedSeed,
        reproducibility_check: reproducibility,
      });
      const first = result.items[0];
      if (first) {
        navigate(`/runs/${first.id}`);
      } else {
        runs.reload();
      }
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "运行发起失败。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <div className="page-eyebrow">DETERMINISTIC RUNS</div>
          <h1 className="page-title">运行记录</h1>
          <p className="page-description">
            每次运行固定用例集、种子、领域哈希与联锁哈希。回归比较结论指纹，不比较自然语言措辞。
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="button button--ghost"
            onClick={runs.reload}
            disabled={runs.refreshing}
          >
            <RefreshCw size={15} className={runs.refreshing ? "spin" : ""} /> 刷新
          </button>
        </div>
      </header>

      <section className="surface">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">NEW RUN · DETERMINISTIC INPUTS</div>
            <h2>发起运行</h2>
          </div>
          <p className="panel-heading__note">
            执行复现校验时，平台会用同条件与同种子重放一次并比对结论指纹。
          </p>
        </div>
        <form className="new-run-form" onSubmit={(event) => void handleSubmit(event)}>
          <Field label="测试套件" hint={selectedSuite?.description}>
            <select
              value={suiteId}
              onChange={(event) => setSuiteId(event.target.value)}
              disabled={suites.loading || submitting}
              required
            >
              <option value="">选择套件</option>
              {suites.data?.map((suite) => (
                <option key={suite.id} value={suite.id}>
                  {suite.name}（{suite.case_ids.length} 例）
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="被测 Agent"
            hint={
              selectedSuite
                ? `套件默认：${selectedSuite.agent_ids.join("、") || "未指定"}`
                : "留空时使用套件默认 Agent"
            }
          >
            <select
              value={agentId}
              onChange={(event) => setAgentId(event.target.value)}
              disabled={submitting}
            >
              <option value="">套件默认配置</option>
              {agents.data?.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name} · {agent.version}
                </option>
              ))}
            </select>
          </Field>

          <Field label="覆盖种子（可选）" hint="留空则使用每个用例自带种子">
            <input
              type="number"
              min={0}
              step={1}
              value={seed}
              onChange={(event) => setSeed(event.target.value)}
              placeholder="例如 20260101"
              disabled={submitting}
            />
          </Field>

          <label className="checkbox-field new-run-form__check">
            <input
              type="checkbox"
              checked={reproducibility}
              onChange={(event) => setReproducibility(event.target.checked)}
              disabled={submitting}
            />
            <span>
              执行复现校验
              <small>同条件 + 同种子重放一次，比对结论指纹</small>
            </span>
          </label>

          <div className="new-run-form__action">
            <button type="submit" className="button button--primary button--block" disabled={submitting}>
              <Play size={15} /> {submitting ? "运行中…" : "执行套件"}
            </button>
          </div>

          {formError && (
            <div className="inline-error new-run-form__error" role="alert">
              <AlertTriangle size={15} aria-hidden="true" />
              <span>{formError}</span>
            </div>
          )}
        </form>
      </section>

      <section className="surface surface--flush">
        <div className="surface__toolbar">
          <div className="filter-row">
            <label className="search-field">
              <Search size={15} aria-hidden="true" />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索运行名称、ID 或 Agent"
                aria-label="搜索运行"
              />
            </label>
            <label className="select-field">
              <Filter size={14} aria-hidden="true" />
              <select
                value={suiteFilter}
                onChange={(event) => setSuiteFilter(event.target.value)}
                aria-label="按套件筛选"
              >
                <option value="">全部套件</option>
                {suites.data?.map((suite) => (
                  <option key={suite.id} value={suite.id}>
                    {suite.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="select-field">
              <select
                value={agentFilter}
                onChange={(event) => setAgentFilter(event.target.value)}
                aria-label="按 Agent 筛选"
              >
                <option value="">全部 Agent</option>
                {agents.data?.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <span className="table-count">
            {filteredRuns.length} / {runs.data?.total ?? 0} 次运行
          </span>
        </div>

        {runs.loading && <LoadingPanel label="正在读取运行记录…" />}
        {runs.error && !runs.data && <ErrorPanel message={runs.error} onRetry={runs.reload} />}
        {runs.error && runs.data && (
          <div className="inline-warning inline-warning--inset">
            <AlertTriangle size={15} aria-hidden="true" />
            <span>{runs.error}</span>
          </div>
        )}
        {runs.data && filteredRuns.length === 0 && (
          <EmptyPanel
            title="没有匹配的运行"
            description="调整筛选条件，或在上方发起一次新运行。"
            icon={<Play size={22} />}
          />
        )}
        {runs.data && filteredRuns.length > 0 && <RunTable runs={filteredRuns} />}
      </section>

      <section className="surface surface--muted">
        <div className="rule-card rule-card--wide">
          <ShieldCheck size={18} aria-hidden="true" />
          <div>
            <strong>运行约束不可由测试用例放宽</strong>
            <ul>
              <li>Agent 建议必须经 SafetyGate 顺序校验，不能直写 DCS/PLC。</li>
              <li>SIS 联锁独立于 Agent，联锁哈希进入每次运行证据。</li>
              <li>所有随机性显式播种，并写入 run manifest。</li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}
