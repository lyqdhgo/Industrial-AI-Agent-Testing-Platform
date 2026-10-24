import {
  ArrowUpRight,
  CircleAlert,
  FileWarning,
  Fingerprint,
  Info,
  TerminalSquare,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type {
  DatasetComposition as DatasetCompositionType,
  Defect,
  DefectDigest,
  DefectLevel,
  TraceEventKind,
} from "../types";
import {
  caseCategoryLabels,
  defectCodeLabels,
  formatSeconds,
  traceEventLabels,
} from "../lib/format";
import { Badge, Hash, type Tone } from "./ui";

const categorySlots = [
  { key: "steady", label: caseCategoryLabels.steady, color: "var(--series-1)" },
  { key: "fault", label: caseCategoryLabels.fault, color: "var(--series-2)" },
  { key: "boundary", label: caseCategoryLabels.boundary, color: "var(--series-3)" },
  { key: "interlock", label: caseCategoryLabels.interlock, color: "var(--series-4)" },
] as const;

export function DatasetComposition({
  dataset,
  compact = false,
}: {
  dataset: DatasetCompositionType;
  compact?: boolean;
}) {
  const counts = {
    steady: dataset.steady_cases,
    fault: dataset.fault_cases,
    boundary: dataset.boundary_cases,
    interlock: dataset.interlock_cases,
  };
  const ratios = {
    steady: dataset.steady_ratio,
    fault: dataset.fault_ratio,
    boundary: dataset.boundary_ratio,
    interlock: dataset.interlock_ratio,
  };

  return (
    <div className={`composition${compact ? " composition--compact" : ""}`}>
      <div
        className="composition__bar"
        role="img"
        aria-label={`数据集构成：稳态 ${counts.steady}，故障 ${counts.fault}，边界 ${counts.boundary}，联锁闭环 ${counts.interlock}`}
      >
        {categorySlots.map((slot) => {
          const count = counts[slot.key];
          if (count === 0) {
            return null;
          }
          const ratio = ratios[slot.key];
          return (
            <div
              key={slot.key}
              className={`composition__segment composition__segment--${slot.key}`}
              style={{ flexGrow: count, background: slot.color }}
              title={`${slot.label} ${count} 例 · ${(ratio * 100).toFixed(1)}%`}
            >
              {ratio >= 0.12 && (
                <span className={`composition__inside composition__inside--${slot.key}`}>
                  {slot.label} {(ratio * 100).toFixed(0)}%
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="composition__legend">
        {categorySlots.map((slot) => (
          <div className="composition__legend-item" key={slot.key}>
            <span className="legend-swatch" style={{ background: slot.color }} aria-hidden="true" />
            <span>{slot.label}</span>
            <strong>{counts[slot.key]}</strong>
            <span className="muted">{(ratios[slot.key] * 100).toFixed(1)}%</span>
          </div>
        ))}
        <div className="composition__total">
          合计 <strong>{dataset.total_cases}</strong> 例
        </div>
      </div>
      {dataset.imbalanced && (
        <div className="inline-warning">
          <CircleAlert size={15} aria-hidden="true" />
          <span>{dataset.warning ?? "数据集类别分布不平衡，指标解释需同时披露构成。"}</span>
        </div>
      )}
    </div>
  );
}

export function StatTile({
  label,
  value,
  unit,
  note,
  tone = "neutral",
  icon,
}: {
  label: string;
  value: string;
  unit?: string;
  note?: string;
  tone?: Tone;
  icon?: ReactNode;
}) {
  return (
    <div className={`stat-tile stat-tile--${tone}`}>
      <div className="stat-tile__top">
        <span>{label}</span>
        {icon && <span className="stat-tile__icon">{icon}</span>}
      </div>
      <div className="stat-tile__value">
        <strong>{value}</strong>
        {unit && <span className="stat-tile__unit">{unit}</span>}
      </div>
      {note && <p className="stat-tile__note">{note}</p>}
    </div>
  );
}

function levelTone(level: DefectLevel): Tone {
  if (level === "P0") {
    return "critical";
  }
  if (level === "P1") {
    return "warning";
  }
  return "info";
}

export function DefectCard({ defect, runId }: { defect: Defect; runId: string }) {
  return (
    <article className={`defect-card defect-card--${defect.level}`}>
      <div className="defect-card__head">
        <Badge tone={levelTone(defect.level)}>{defect.level}</Badge>
        <div className="defect-card__title">
          <h3>{defect.title}</h3>
          <div className="defect-card__meta">
            <code>{defectCodeLabels[defect.code]}</code>
            <span className="dot-sep" aria-hidden="true" />
            <span>{defect.case_id}</span>
            {defect.occurred_at_s !== null && (
              <>
                <span className="dot-sep" aria-hidden="true" />
                <span>发生于 {formatSeconds(defect.occurred_at_s)}</span>
              </>
            )}
            {defect.risk_window && (
              <>
                <span className="dot-sep" aria-hidden="true" />
                <Badge tone="serious">高风险期</Badge>
              </>
            )}
          </div>
        </div>
        <Link
          className="icon-link"
          to={`/runs/${runId}/cases/${defect.case_id}`}
          title="查看该用例证据"
          aria-label="查看该用例证据"
        >
          <ArrowUpRight size={16} />
        </Link>
      </div>

      {defect.detail && <p className="defect-card__detail">{defect.detail}</p>}

      <div className="defect-card__compare">
        <div>
          <span>期望</span>
          <p>{defect.expected || "—"}</p>
        </div>
        <div>
          <span>实际</span>
          <p>{defect.actual || "—"}</p>
        </div>
      </div>

      <details className="disclosure">
        <summary>
          <Info size={14} aria-hidden="true" /> 取证与机制依据
        </summary>
        <div className="disclosure__body">
          {defect.mechanism_basis ? (
            <p className={defect.mechanism_basis.includes("TODO(mechanism)") ? "mechanism-note" : ""}>
              {defect.mechanism_basis}
            </p>
          ) : (
            <p className="muted">未记录机制依据。</p>
          )}
          {defect.evidence_paths.length > 0 && (
            <div className="evidence-paths">
              <FileWarning size={14} aria-hidden="true" />
              <span>证据路径：</span>
              {defect.evidence_paths.map((path) => (
                <code key={path}>{path}</code>
              ))}
            </div>
          )}
          {defect.repro_command && (
            <div className="repro-command">
              <TerminalSquare size={14} aria-hidden="true" />
              <code>{defect.repro_command}</code>
            </div>
          )}
        </div>
      </details>
    </article>
  );
}

export function DigestDefectCard({
  defect,
  runId,
}: {
  defect: DefectDigest;
  runId: string;
}) {
  return (
    <Link className="digest-defect" to={`/runs/${runId}/cases/${defect.case_id}`}>
      <div>
        <div className="digest-defect__meta">
          <code>{defect.code}</code>
          <span>{defect.case_id}</span>
          {defect.occurred_at_s !== null && <span>· {formatSeconds(defect.occurred_at_s)}</span>}
        </div>
        <strong>{defect.title}</strong>
        {defect.detail && <p>{defect.detail}</p>}
      </div>
      <ArrowUpRight size={16} aria-hidden="true" />
    </Link>
  );
}

const traceTone: Partial<Record<TraceEventKind, Tone>> = {
  GATE_BLOCKED: "critical",
  SIS_BLOCKED: "serious",
  RETRY_BLOCKED: "critical",
  DCS_WRITE: "good",
  GATE_ALLOWED: "good",
  CONFIRMATION_GRANTED: "info",
  CONFIRMATION_REQUIRED: "warning",
  SIS_TRIGGERED: "serious",
  DEGRADED_MODE: "info",
};

type TraceCount = { kind: TraceEventKind; count: number };

/** 按事件类型汇总次数，保持首次出现的顺序；完整时序放在下方折叠区。 */
function summarizeTrace(trace: TraceEventKind[]): TraceCount[] {
  const counts = new Map<TraceEventKind, number>();
  for (const kind of trace) {
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  return [...counts].map(([kind, count]) => ({ kind, count }));
}

export function TraceChips({ trace }: { trace: TraceEventKind[] }) {
  if (trace.length === 0) {
    return <span className="muted">无动作</span>;
  }
  const summary = summarizeTrace(trace);
  return (
    <div className="trace-summary">
      <div className="trace-chips">
        {summary.map(({ kind, count }) => (
          <Badge
            key={kind}
            tone={traceTone[kind] ?? "neutral"}
            title={`${traceEventLabels[kind]}：共 ${count} 次`}
          >
            {traceEventLabels[kind]}
            {count > 1 && <span className="trace-chips__count">× {count}</span>}
          </Badge>
        ))}
      </div>
      {trace.length > 6 && (
        <details className="trace-sequence">
          <summary>完整动作顺序 · {trace.length} 步</summary>
          <ol>
            {trace.map((kind, index) => (
              <li key={`${kind}-${index}`}>
                <span className="trace-sequence__index">{String(index + 1).padStart(2, "0")}</span>
                <Badge tone={traceTone[kind] ?? "neutral"}>{traceEventLabels[kind]}</Badge>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

export function FingerprintLine({
  fingerprint,
  reproducible,
}: {
  fingerprint: string;
  reproducible: boolean | null;
}) {
  let tone: Tone = "neutral";
  let text = "未执行复现校验";
  if (reproducible === true) {
    tone = "good";
    text = "复现一致";
  } else if (reproducible === false) {
    tone = "critical";
    text = "复现失败";
  }
  return (
    <div className="fingerprint-line">
      <Fingerprint size={14} aria-hidden="true" />
      <Hash value={fingerprint} length={16} />
      <Badge tone={tone}>{text}</Badge>
    </div>
  );
}
