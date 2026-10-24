import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  Download,
  FileText,
  Fingerprint,
  Loader2,
  Printer,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { ApiError, api } from "../api";
import { Badge, EmptyPanel, ErrorPanel, LoadingPanel } from "../components/ui";
import { formatDateTime, shortHash } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export function ReportPage() {
  const { runId } = useParams<{ runId: string }>();
  const runState = useAsync(
    () => (runId ? api.getRun(runId) : Promise.reject(new Error("缺少运行 ID"))),
    [runId],
  );
  const reportState = useAsync(async () => {
    if (!runId) {
      return null;
    }
    try {
      return await api.report(runId);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  }, [runId]);
  const [generating, setGenerating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const run = runState.data;
  const report = reportState.data;

  async function generate(): Promise<void> {
    if (!runId) {
      return;
    }
    setGenerating(true);
    setActionError(null);
    try {
      await api.generateReport(runId);
      reportState.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "报告生成失败。");
    } finally {
      setGenerating(false);
    }
  }

  if (runState.loading || reportState.loading) {
    return (
      <div className="page">
        <LoadingPanel label="正在读取测试报告…" />
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

  if (reportState.error) {
    return (
      <div className="page">
        <ErrorPanel message={reportState.error} onRetry={reportState.reload} />
        <Link className="button button--ghost" to={`/runs/${run.id}`}>
          <ArrowLeft size={15} /> 返回运行详情
        </Link>
      </div>
    );
  }

  return (
    <div className="page report-page">
      <div className="page-back no-print">
        <Link className="text-link" to={`/runs/${run.id}`}>
          <ArrowLeft size={14} /> 运行详情
        </Link>
      </div>

      <header className="page-header">
        <div>
          <div className="page-eyebrow">TEST REPORT · FIXED TEN SECTIONS</div>
          <h1 className="page-title">测试报告</h1>
          <p className="page-description">
            {run.name}
            <span className="dot-sep" aria-hidden="true" />
            {run.agent_name} · {run.agent_version}
            <span className="dot-sep" aria-hidden="true" />
            <code className="inline-code">{run.id}</code>
          </p>
        </div>
        <div className="page-actions no-print">
          {report && (
            <>
              <button type="button" className="button button--ghost" onClick={() => window.print()}>
                <Printer size={15} /> 打印
              </button>
              <a className="button button--ghost" href={api.reportUrl(run.id)} download>
                <Download size={15} /> Markdown
              </a>
              <button
                type="button"
                className="button button--ghost"
                onClick={() => void generate()}
                disabled={generating}
              >
                {generating ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
                {generating ? "重新生成…" : "重新生成"}
              </button>
            </>
          )}
          {!report && (
            <button
              type="button"
              className="button button--primary"
              onClick={() => void generate()}
              disabled={generating || run.status !== "completed"}
            >
              {generating ? <Loader2 size={15} className="spin" /> : <FileText size={15} />}
              {generating ? "生成中…" : "生成报告"}
            </button>
          )}
        </div>
      </header>

      {actionError && (
        <div className="inline-error no-print" role="alert">
          <AlertTriangle size={15} aria-hidden="true" />
          <span>{actionError}</span>
        </div>
      )}

      <section className="report-context">
        <div>
          <span>运行</span>
          <strong>{run.name}</strong>
          <small>{shortHash(run.id, 30)}</small>
        </div>
        <div>
          <span>数据集</span>
          <strong>{run.case_ids.length} 条用例</strong>
          <small>种子集合 {run.seed_set.join(", ") || run.seed}</small>
        </div>
        <div>
          <span>结论边界</span>
          <strong>{run.metrics?.defects_p0 ?? 0} 条 P0</strong>
          <small>报告不输出“测试通过”</small>
        </div>
        <div>
          <span>哈希</span>
          <strong>领域 {shortHash(run.domain_hashes.domain_hash, 10)}</strong>
          <small>联锁 {shortHash(run.domain_hashes.interlock_hash, 10)}</small>
        </div>
        <div>
          <span>生成时间</span>
          <strong>{report?.generated_at ? formatDateTime(report.generated_at) : "尚未生成"}</strong>
          <small>固定十节 · 可直接归档</small>
        </div>
      </section>

      {!report && (
        <EmptyPanel
          title="该运行尚未生成报告"
          description={
            run.status === "completed"
              ? "报告由平台根据落盘证据生成，固定包含十节结构。生成操作不会修改运行结果。"
              : "运行尚未完成，不能生成可信报告。"
          }
          icon={<FileText size={24} />}
          action={
            run.status === "completed" ? (
              <button
                type="button"
                className="button button--primary"
                onClick={() => void generate()}
                disabled={generating}
              >
                {generating ? <Loader2 size={15} className="spin" /> : <FileText size={15} />}
                {generating ? "生成中…" : "生成报告"}
              </button>
            ) : undefined
          }
        />
      )}

      {report && (
        <div className="report-layout">
          <article className="report-document markdown-body">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                table: ({ children }) => (
                  <div className="table-wrap report-table">
                    <table>{children}</table>
                  </div>
                ),
                a: ({ href, children }) => (
                  <a href={href} target={href?.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
                    {children}
                  </a>
                ),
              }}
            >
              {report.markdown}
            </ReactMarkdown>
          </article>

          <aside className="report-aside no-print" aria-label="报告阅读提示">
            <div className="report-aside__card">
              <div className="report-aside__title">
                <ShieldAlert size={16} aria-hidden="true" />
                <strong>阅读口径</strong>
              </div>
              <ul>
                <li>先看数据集构成，再看比率；漏报优先于误报。</li>
                <li>P0 是阻断项：漏报、越权、越安全边界、缺少降级。</li>
                <li>“未记录 P0”不等于测试通过，仍需审阅覆盖率与复现性。</li>
                <li>结论针对本次种子与本次用例集，不外推到真实装置。</li>
              </ul>
            </div>

            <div className="report-aside__card">
              <div className="report-aside__title">
                <Fingerprint size={16} aria-hidden="true" />
                <strong>证据链</strong>
              </div>
              <p className="muted">
                报告内容来自用例 YAML、时序 CSV、原始响应、门禁决策、动作轨迹与结论指纹。
              </p>
              <div className="report-aside__meta">
                <span>用例集</span>
                <code>{shortHash(run.domain_hashes.case_set_hash, 18)}</code>
                <span>领域</span>
                <code>{shortHash(run.domain_hashes.domain_hash, 18)}</code>
                <span>联锁</span>
                <code>{shortHash(run.domain_hashes.interlock_hash, 18)}</code>
              </div>
              <Link className="text-link" to={`/runs/${run.id}`}>
                返回运行取证 <ArrowUpRight size={14} />
              </Link>
            </div>

            {report.path && (
              <div className="report-aside__card">
                <div className="report-aside__title">
                  <FileText size={16} aria-hidden="true" />
                  <strong>归档路径</strong>
                </div>
                <code className="report-path">{report.path}</code>
                <Badge tone="info">只读证据</Badge>
              </div>
            )}
          </aside>
        </div>
      )}

      <div className="disclaimer">
        <AlertTriangle size={16} aria-hidden="true" />
        <p>
          报告为演示域测试结论，不构成安全认证。任何指标都必须在披露数据集构成与种子后解读。
        </p>
        <span>IATP · 固定十节报告模板</span>
      </div>
    </div>
  );
}
