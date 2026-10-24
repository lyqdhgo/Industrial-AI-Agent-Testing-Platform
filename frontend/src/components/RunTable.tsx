import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import type { RunSummary } from "../types";
import { formatDateTime, formatPercent, runStatusLabels, shortHash } from "../lib/format";
import { runMissRate, runP0, runP1 } from "../lib/runs";
import { Badge, type Tone } from "./ui";

/** 运行 ID 很长，表格内只展示时间戳与尾哈希；完整值放在 title 中。 */
function shortRunId(id: string): string {
  const match = /^run-(\d{8}T\d{6})-.*-([0-9a-z]{6})$/i.exec(id);
  return match ? `${match[1]} · ${match[2]}` : shortHash(id, 30);
}

function statusTone(run: RunSummary): Tone {
  if (run.status === "failed") {
    return "critical";
  }
  if (run.status === "completed") {
    return "good";
  }
  return "info";
}

export function RunTable({ runs, compact = false }: { runs: RunSummary[]; compact?: boolean }) {
  return (
    <div className="table-wrap">
      <table className={`data-table${compact ? " data-table--compact" : ""}`}>
        <thead>
          <tr>
            <th>运行</th>
            <th>被测 Agent</th>
            {!compact && <th>套件</th>}
            <th className="numeric">用例</th>
            <th className="numeric">漏报率</th>
            <th className="numeric">P0</th>
            <th className="numeric">P1</th>
            <th>状态</th>
            <th>完成时间</th>
            <th aria-label="操作" />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const missRate = runMissRate(run);
            const p0 = runP0(run);
            const p1 = runP1(run);
            return (
              <tr key={run.id}>
                <td>
                  <Link className="table-primary" to={`/runs/${run.id}`}>
                    {run.name}
                  </Link>
                  <div className="table-sub table-sub--mono" title={run.id}>
                    {shortRunId(run.id)}
                  </div>
                </td>
                <td>
                  <span>{run.agent_name}</span>
                  <div className="table-sub">{run.agent_version}</div>
                </td>
                {!compact && <td><code className="inline-code">{run.suite_id}</code></td>}
                <td className="numeric">{run.case_count}</td>
                <td className="numeric">
                  {missRate === null ? <span className="muted">不适用</span> : formatPercent(missRate)}
                </td>
                <td className="numeric">
                  {p0 > 0 ? (
                    <span className="numeric-critical">{p0}</span>
                  ) : (
                    <span className="muted">0</span>
                  )}
                </td>
                <td className="numeric">
                  {p1 > 0 ? <span className="numeric-warning">{p1}</span> : <span className="muted">0</span>}
                </td>
                <td>
                  <Badge tone={statusTone(run)}>{runStatusLabels[run.status]}</Badge>
                </td>
                <td className="nowrap muted">{formatDateTime(run.finished_at ?? run.created_at)}</td>
                <td>
                  <Link
                    className="icon-link"
                    to={`/runs/${run.id}`}
                    aria-label={`查看运行 ${run.name}`}
                    title="查看运行"
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
  );
}
