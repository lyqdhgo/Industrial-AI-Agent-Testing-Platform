import {
  Check,
  CheckCircle2,
  CircleAlert,
  Copy,
  Info,
  Minus,
  OctagonAlert,
  RefreshCw,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";

export type Tone = "critical" | "serious" | "warning" | "good" | "info" | "neutral";

const toneIcons: Record<Tone, LucideIcon> = {
  critical: OctagonAlert,
  serious: TriangleAlert,
  warning: CircleAlert,
  good: CheckCircle2,
  info: Info,
  neutral: Minus,
};

export function Badge({
  tone = "neutral",
  children,
  className = "",
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  const Icon = toneIcons[tone];
  return (
    <span className={`badge badge--${tone} ${className}`.trim()} title={title}>
      <Icon aria-hidden="true" size={13} strokeWidth={2.2} />
      <span>{children}</span>
    </span>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="tag">{children}</span>;
}

export function Hash({
  value,
  length = 12,
  copy = true,
}: {
  value: string | null | undefined;
  length?: number;
  copy?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  if (!value) {
    return <span className="muted">—</span>;
  }
  const display = value.length > length ? value.slice(0, length) : value;

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(value ?? "");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return (
    <span className="hash">
      <code title={value}>{display}</code>
      {copy && (
        <button
          type="button"
          className="icon-button icon-button--tiny"
          onClick={() => void handleCopy()}
          title="复制完整指纹"
          aria-label="复制完整指纹"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
        </button>
      )}
    </span>
  );
}

export function LoadingPanel({ label = "正在读取证据…" }: { label?: string }) {
  return (
    <div className="state-panel" role="status" aria-live="polite">
      <div className="skeleton skeleton--title" />
      <div className="skeleton skeleton--line" />
      <div className="skeleton skeleton--line skeleton--short" />
      <p className="muted">{label}</p>
    </div>
  );
}

export function ErrorPanel({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <div className="state-panel__head">
        <OctagonAlert size={20} aria-hidden="true" />
        <strong>无法读取数据</strong>
      </div>
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="button button--ghost" onClick={onRetry}>
          <RefreshCw size={14} /> 重试
        </button>
      )}
    </div>
  );
}

export function EmptyPanel({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="state-panel state-panel--empty">
      {icon && <div className="state-panel__icon">{icon}</div>}
      <strong>{title}</strong>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      {children}
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  );
}

export function KeyValue({
  items,
  compact = false,
}: {
  items: { label: string; value: ReactNode }[];
  compact?: boolean;
}) {
  return (
    <dl className={`key-value${compact ? " key-value--compact" : ""}`}>
      {items.map((item) => (
        <div className="key-value__row" key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SectionHeading({
  title,
  description,
  action,
  eyebrow,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <div className="section-heading__eyebrow">{eyebrow}</div>}
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="section-heading__action">{action}</div>}
    </div>
  );
}
