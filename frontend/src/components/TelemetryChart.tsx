import { useMemo, useRef, useState, type PointerEvent } from "react";
import { Activity, AlertTriangle } from "lucide-react";
import { api } from "../api";
import type { FaultPlan, SensorMeta, SeriesPoint } from "../types";
import { formatNumber, formatUnit, qualityLabels } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { ErrorPanel, LoadingPanel } from "./ui";

const W = 760;
const H = 250;
const MARGIN = { top: 22, right: 104, bottom: 36, left: 58 };
const PLOT_W = W - MARGIN.left - MARGIN.right;
const PLOT_H = H - MARGIN.top - MARGIN.bottom;

const series = {
  truth: "var(--series-1)",
  measured: "var(--series-2)",
  command: "var(--series-3)",
  critical: "var(--status-critical)",
};

interface ChartSeries {
  key: string;
  label: string;
  color: string;
  last: SeriesPoint | null;
  value: number | null;
}

function lastWith(points: SeriesPoint[], getter: (point: SeriesPoint) => number | null): SeriesPoint | null {
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const point = points[index];
    if (point && getter(point) !== null) {
      return point;
    }
  }
  return null;
}

function medianStep(points: SeriesPoint[]): number {
  if (points.length < 2) {
    return 1;
  }
  const diffs: number[] = [];
  for (let index = 1; index < points.length; index += 1) {
    const current = points[index];
    const previous = points[index - 1];
    if (current && previous) {
      diffs.push(current.t_s - previous.t_s);
    }
  }
  diffs.sort((a, b) => a - b);
  return diffs[Math.floor(diffs.length / 2)] ?? 1;
}

function buildPath(
  points: SeriesPoint[],
  getter: (point: SeriesPoint) => number | null,
  valid: (point: SeriesPoint) => boolean,
  xScale: (t: number) => number,
  yScale: (value: number) => number,
  gapLimit: number,
): string {
  let path = "";
  let penDown = false;
  let previousT = 0;
  for (const point of points) {
    const value = getter(point);
    if (value === null || !valid(point)) {
      penDown = false;
      continue;
    }
    const x = xScale(point.t_s);
    const y = yScale(value);
    if (!penDown || Math.abs(point.t_s - previousT) > gapLimit) {
      path += `M${x.toFixed(2)},${y.toFixed(2)}`;
    } else {
      path += `L${x.toFixed(2)},${y.toFixed(2)}`;
    }
    penDown = true;
    previousT = point.t_s;
  }
  return path;
}

function niceTicks(min: number, max: number, count = 4): { ticks: number[]; min: number; max: number } {
  const rawSpan = max - min;
  if (!Number.isFinite(rawSpan) || rawSpan <= 0) {
    return { ticks: [min - 1, min, min + 1], min: min - 1, max: min + 1 };
  }
  const rough = rawSpan / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / magnitude;
  const step =
    (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10) *
    magnitude;
  const niceMin = Math.floor(min / step) * step;
  const niceMax = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let value = niceMin; value <= niceMax + step * 0.001; value += step) {
    ticks.push(Number(value.toFixed(8)));
  }
  return { ticks, min: niceMin, max: niceMax };
}

function axisValue(value: number, span: number): string {
  if (span < 2) {
    return value.toFixed(2);
  }
  if (span < 20) {
    return value.toFixed(1);
  }
  return value.toFixed(0);
}

function nearestIndex(points: SeriesPoint[], t: number): number {
  if (points.length === 0) {
    return 0;
  }
  let low = 0;
  let high = points.length - 1;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    const current = points[mid];
    const next = points[mid + 1];
    if (!current) {
      break;
    }
    if (t < current.t_s) {
      high = mid;
    } else if (next && t > next.t_s) {
      low = mid + 1;
    } else {
      return next && Math.abs(next.t_s - t) < Math.abs(t - current.t_s) ? mid + 1 : mid;
    }
  }
  return low;
}

function sampleRows(points: SeriesPoint[], limit = 18): SeriesPoint[] {
  if (points.length <= limit) {
    return points;
  }
  const step = (points.length - 1) / (limit - 1);
  return Array.from({ length: limit }, (_, index) => points[Math.round(index * step)]).filter(
    (point): point is SeriesPoint => point !== undefined,
  );
}

function LegendKey({ color, label, shape = "line", wash = false }: { color: string; label: string; shape?: "line" | "dot" | "x"; wash?: boolean }) {
  return (
    <span className="legend-item">
      <span
        className={`legend-key legend-key--${shape}${wash ? " legend-key--wash" : ""}`}
        style={{ background: color, borderColor: color }}
        aria-hidden="true"
      />
      <span>{label}</span>
    </span>
  );
}

function ChartTooltip({
  point,
  xPercent,
  unit,
  showCommand,
}: {
  point: SeriesPoint;
  xPercent: number;
  unit: string;
  showCommand: boolean;
}) {
  const clamped = Math.min(88, Math.max(12, xPercent));
  return (
    <div className="chart-tooltip" style={{ left: `${clamped}%` }} role="status">
      <div className="chart-tooltip__time">
        t = {formatNumber(point.t_s, 0)} s
        <span className={`quality-dot quality-dot--${point.quality}`}>
          {qualityLabels[point.quality]}
        </span>
      </div>
      <dl>
        <div>
          <dt>
            <span className="legend-key legend-key--line" style={{ background: series.truth }} />
            真实值
          </dt>
          <dd>
            {formatNumber(point.true_value, 2)} {formatUnit(unit)}
          </dd>
        </div>
        <div>
          <dt>
            <span className="legend-key legend-key--line" style={{ background: series.measured }} />
            测量值
          </dt>
          <dd>
            {point.measured_value === null
              ? "未交付"
              : `${formatNumber(point.measured_value, 2)} ${formatUnit(unit)}`}
          </dd>
        </div>
        {showCommand && (
          <div>
            <dt>
              <span className="legend-key legend-key--line" style={{ background: series.command }} />
              阀位指令
            </dt>
            <dd>
              {point.command_value === null
                ? "—"
                : `${formatNumber(point.command_value, 2)} ${formatUnit(unit)}`}
            </dd>
          </div>
        )}
      </dl>
      {!point.delivered && <div className="chart-tooltip__note">该样本未按时刻交付（网络延迟/丢包）</div>}
    </div>
  );
}

export function TelemetryChart({
  sensor,
  points,
  faults,
}: {
  sensor: SensorMeta;
  points: SeriesPoint[];
  faults: FaultPlan[];
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hover, setHover] = useState<{ index: number; xPercent: number } | null>(null);
  const showCommand = sensor.tag === "LV-201";

  const geometry = useMemo(() => {
    const allValues: number[] = [];
    for (const point of points) {
      allValues.push(point.true_value);
      if (point.measured_value !== null) {
        allValues.push(point.measured_value);
      }
      if (showCommand && point.command_value !== null) {
        allValues.push(point.command_value);
      }
    }
    allValues.push(sensor.safe_limits.low, sensor.safe_limits.high);
    if (sensor.trip_limits.high !== null) {
      allValues.push(sensor.trip_limits.high);
    }
    if (sensor.trip_limits.low !== null) {
      allValues.push(sensor.trip_limits.low);
    }
    const dataMin = allValues.length > 0 ? Math.min(...allValues) : 0;
    const dataMax = allValues.length > 0 ? Math.max(...allValues) : 1;
    const pad = Math.max((dataMax - dataMin) * 0.08, 0.5);
    const ticks = niceTicks(dataMin - pad, dataMax + pad, 4);
    const maxT = Math.max(points[points.length - 1]?.t_s ?? 1, 1);
    const xScale = (t: number): number => MARGIN.left + (t / maxT) * PLOT_W;
    const yScale = (value: number): number =>
      MARGIN.top + PLOT_H - ((value - ticks.min) / (ticks.max - ticks.min)) * PLOT_H;
    return { min: ticks.min, max: ticks.max, ticks: ticks.ticks, maxT, xScale, yScale };
  }, [points, sensor, showCommand]);

  const paths = useMemo(() => {
    const gapLimit = Math.max(medianStep(points) * 3, 4);
    return {
      truth: buildPath(
        points,
        (point) => point.true_value,
        () => true,
        geometry.xScale,
        geometry.yScale,
        gapLimit,
      ),
      measured: buildPath(
        points,
        (point) => point.measured_value,
        (point) => point.quality === "good",
        geometry.xScale,
        geometry.yScale,
        gapLimit,
      ),
      command: showCommand
        ? buildPath(
            points,
            (point) => point.command_value,
            () => true,
            geometry.xScale,
            geometry.yScale,
            gapLimit,
          )
        : "",
    };
  }, [points, geometry, showCommand]);

  const badPoints = useMemo(
    () =>
      points.filter(
        (point) => point.quality !== "good" && point.measured_value !== null,
      ),
    [points],
  );

  const labels = useMemo((): ChartSeries[] => {
    const truthLast = lastWith(points, (point) => point.true_value);
    const measuredLast = lastWith(points, (point) => point.measured_value);
    const commandLast = lastWith(points, (point) => point.command_value);
    return [
      {
        key: "truth",
        label: "真实",
        color: series.truth,
        last: truthLast,
        value: truthLast?.true_value ?? null,
      },
      {
        key: "measured",
        label: "测量",
        color: series.measured,
        last: measuredLast,
        value: measuredLast?.measured_value ?? null,
      },
      ...(showCommand
        ? [
            {
              key: "command",
              label: "指令",
              color: series.command,
              last: commandLast,
              value: commandLast?.command_value ?? null,
            },
          ]
        : []),
    ].filter((item) => item.value !== null);
  }, [points, showCommand]);

  const labelLayout = useMemo(() => {
    const span = geometry.max - geometry.min;
    const items = labels
      .map((item) => {
        const value = item.value ?? 0;
        return {
          ...item,
          value,
          originalY: geometry.yScale(value),
          y: geometry.yScale(value),
          text: `${item.label} ${axisValue(value, span)}`,
        };
      })
      .sort((a, b) => a.y - b.y);
    const minGap = 17;
    for (let index = 1; index < items.length; index += 1) {
      const previous = items[index - 1];
      const current = items[index];
      if (previous && current && current.y - previous.y < minGap) {
        current.y = previous.y + minGap;
      }
    }
    const last = items[items.length - 1];
    if (last && last.y > MARGIN.top + PLOT_H) {
      const overflow = last.y - (MARGIN.top + PLOT_H);
      for (const item of items) {
        item.y -= overflow;
      }
    }
    const first = items[0];
    if (first && first.y < MARGIN.top) {
      const underflow = MARGIN.top - first.y;
      for (const item of items) {
        item.y += underflow;
      }
    }
    return items;
  }, [labels, geometry]);

  const hovered = hover ? points[hover.index] : undefined;
  const xTicks = Array.from({ length: 5 }, (_, index) => (geometry.maxT * index) / 4);
  const ySpan = geometry.max - geometry.min;

  function onPointerMove(event: PointerEvent<SVGRectElement>): void {
    const svg = svgRef.current;
    if (!svg || points.length === 0) {
      return;
    }
    const rect = svg.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * W;
    if (x < MARGIN.left || x > MARGIN.left + PLOT_W) {
      setHover(null);
      return;
    }
    const t = ((x - MARGIN.left) / PLOT_W) * geometry.maxT;
    const index = nearestIndex(points, t);
    const point = points[index];
    if (!point) {
      return;
    }
    const pointX = geometry.xScale(point.t_s);
    setHover({ index, xPercent: (pointX / W) * 100 });
  }

  const faultWindows = faults.map((fault) => ({
    start: fault.start_s,
    end: fault.start_s + fault.duration_s,
    target: fault.target_tag,
  }));

  return (
    <div className="chart-shell">
      <div className="chart-legend" aria-label="图例">
        <LegendKey color={series.truth} label="真实值" />
        <LegendKey color={series.measured} label="测量值" />
        {showCommand && <LegendKey color={series.command} label="阀位指令" />}
        {badPoints.length > 0 && <LegendKey color={series.critical} label="坏质量（不采信）" shape="x" />}
        <LegendKey color="rgba(255,255,255,0.12)" label="安全区间" wash />
        <LegendKey color="rgba(57,135,229,0.28)" label="推荐区间" wash />
        {faultWindows.length > 0 && <LegendKey color="rgba(208,59,59,0.35)" label="故障窗口" wash />}
      </div>

      <div className="chart-canvas">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="telemetry-svg"
          role="img"
          aria-label={`${sensor.tag} ${sensor.name} 真实值与测量值时序图`}
        >
          <title>{`${sensor.tag} ${sensor.name}：真实值与测量值`}</title>
          <defs>
            <clipPath id={`clip-${sensor.tag}`}>
              <rect x={MARGIN.left} y={MARGIN.top} width={PLOT_W} height={PLOT_H} />
            </clipPath>
          </defs>

          {geometry.ticks.map((tick) => {
            const y = geometry.yScale(tick);
            return (
              <g key={tick}>
                <line
                  x1={MARGIN.left}
                  x2={MARGIN.left + PLOT_W}
                  y1={y}
                  y2={y}
                  stroke="var(--chart-grid)"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
                <text x={MARGIN.left - 9} y={y + 3.5} textAnchor="end" className="axis-text">
                  {axisValue(tick, ySpan)}
                </text>
              </g>
            );
          })}

          <rect
            x={MARGIN.left}
            y={geometry.yScale(sensor.safe_limits.high)}
            width={PLOT_W}
            height={Math.max(
              geometry.yScale(sensor.safe_limits.low) - geometry.yScale(sensor.safe_limits.high),
              0,
            )}
            fill="rgba(255,255,255,0.035)"
          />
          <rect
            x={MARGIN.left}
            y={geometry.yScale(sensor.recommended_band.high)}
            width={PLOT_W}
            height={Math.max(
              geometry.yScale(sensor.recommended_band.low) -
                geometry.yScale(sensor.recommended_band.high),
              0,
            )}
            fill="rgba(57,135,229,0.10)"
          />

          {faultWindows.map((window, index) => {
            const x1 = geometry.xScale(Math.max(0, window.start));
            const x2 = geometry.xScale(Math.min(geometry.maxT, window.end));
            return (
              <g key={`${window.start}-${index}`}>
                <rect
                  x={x1}
                  y={MARGIN.top}
                  width={Math.max(x2 - x1, 1)}
                  height={PLOT_H}
                  fill="rgba(208,59,59,0.07)"
                />
                <line
                  x1={x1}
                  x2={x2}
                  y1={MARGIN.top + 1}
                  y2={MARGIN.top + 1}
                  stroke="rgba(208,59,59,0.65)"
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                />
                {x2 - x1 > 64 && (
                  <text x={(x1 + x2) / 2} y={MARGIN.top + 14} textAnchor="middle" className="fault-label">
                    故障窗口 · {window.target}
                  </text>
                )}
              </g>
            );
          })}

          <g clipPath={`url(#clip-${sensor.tag})`}>
            {paths.truth && (
              <path
                d={paths.truth}
                fill="none"
                stroke={series.truth}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            )}
            {paths.measured && (
              <path
                d={paths.measured}
                fill="none"
                stroke={series.measured}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            )}
            {paths.command && (
              <path
                d={paths.command}
                fill="none"
                stroke={series.command}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            )}
            {badPoints.map((point) => {
              if (point.measured_value === null) {
                return null;
              }
              const x = geometry.xScale(point.t_s);
              const y = geometry.yScale(point.measured_value);
              return (
                <g key={`bad-${point.t_s}`} stroke={series.critical} strokeWidth={1.8} vectorEffect="non-scaling-stroke">
                  <line x1={x - 3} x2={x + 3} y1={y - 3} y2={y + 3} />
                  <line x1={x - 3} x2={x + 3} y1={y + 3} y2={y - 3} />
                </g>
              );
            })}
          </g>

          {xTicks.map((tick) => (
            <text
              key={tick}
              x={geometry.xScale(tick)}
              y={H - 12}
              textAnchor={tick === 0 ? "start" : tick === geometry.maxT ? "end" : "middle"}
              className="axis-text"
            >
              {Math.round(tick)}
            </text>
          ))}
          <text x={MARGIN.left + PLOT_W} y={H - 1} textAnchor="end" className="axis-caption">
            相对时间 / s
          </text>

          {labelLayout.map((item) => (
            <g key={item.key}>
              {Math.abs(item.y - item.originalY) > 1 && (
                <line
                  x1={MARGIN.left + PLOT_W}
                  x2={MARGIN.left + PLOT_W + 8}
                  y1={item.originalY}
                  y2={item.y}
                  stroke="var(--text-muted)"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
              )}
              <line
                x1={MARGIN.left + PLOT_W + 10}
                x2={MARGIN.left + PLOT_W + 17}
                y1={item.y}
                y2={item.y}
                stroke={item.color}
                strokeWidth={2}
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
              <text x={MARGIN.left + PLOT_W + 21} y={item.y + 3.5} className="end-label">
                {item.text}
              </text>
            </g>
          ))}

          {hovered && (
            <g>
              <line
                x1={geometry.xScale(hovered.t_s)}
                x2={geometry.xScale(hovered.t_s)}
                y1={MARGIN.top}
                y2={MARGIN.top + PLOT_H}
                stroke="var(--text-muted)"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx={geometry.xScale(hovered.t_s)}
                cy={geometry.yScale(hovered.true_value)}
                r={4}
                fill={series.truth}
                stroke="var(--surface-1)"
                strokeWidth={2}
              />
              {hovered.measured_value !== null && (
                <circle
                  cx={geometry.xScale(hovered.t_s)}
                  cy={geometry.yScale(hovered.measured_value)}
                  r={4}
                  fill={series.measured}
                  stroke="var(--surface-1)"
                  strokeWidth={2}
                />
              )}
              {showCommand && hovered.command_value !== null && (
                <circle
                  cx={geometry.xScale(hovered.t_s)}
                  cy={geometry.yScale(hovered.command_value)}
                  r={4}
                  fill={series.command}
                  stroke="var(--surface-1)"
                  strokeWidth={2}
                />
              )}
            </g>
          )}

          <rect
            x={MARGIN.left}
            y={MARGIN.top}
            width={PLOT_W}
            height={PLOT_H}
            fill="transparent"
            onPointerMove={onPointerMove}
            onPointerLeave={() => setHover(null)}
            aria-label="悬浮查看采样点"
          />
        </svg>

        {hovered && (
          <ChartTooltip
            point={hovered}
            xPercent={hover ? hover.xPercent : 50}
            unit={sensor.unit}
            showCommand={showCommand}
          />
        )}
      </div>

      <details className="chart-table">
        <summary>查看数据表（原始 {points.length} 点，展示抽样）</summary>
        <div className="table-wrap table-wrap--compact">
          <table className="data-table data-table--compact">
            <thead>
              <tr>
                <th>t / s</th>
                <th>真实值</th>
                <th>测量值</th>
                {showCommand && <th>阀位指令</th>}
                <th>质量</th>
                <th>交付</th>
              </tr>
            </thead>
            <tbody>
              {sampleRows(points).map((point) => (
                <tr key={point.t_s}>
                  <td>{formatNumber(point.t_s, 0)}</td>
                  <td>{formatNumber(point.true_value, 2)}</td>
                  <td>{point.measured_value === null ? "—" : formatNumber(point.measured_value, 2)}</td>
                  {showCommand && (
                    <td>{point.command_value === null ? "—" : formatNumber(point.command_value, 2)}</td>
                  )}
                  <td>
                    <span className={`quality-dot quality-dot--${point.quality}`}>
                      {qualityLabels[point.quality]}
                    </span>
                  </td>
                  <td>{point.delivered ? "是" : "否"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function ChartCard({
  runId,
  caseId,
  sensor,
  faults,
}: {
  runId: string;
  caseId: string;
  sensor: SensorMeta;
  faults: FaultPlan[];
}) {
  const seriesResult = useAsync(
    () => api.series(runId, caseId, sensor.tag, 900),
    [runId, caseId, sensor.tag],
  );

  const tripHigh = sensor.trip_limits.high;
  return (
    <section className="chart-card" aria-labelledby={`chart-title-${sensor.tag}`}>
      <div className="chart-card__head">
        <div>
          <div className="chart-card__kicker">
            <Activity size={14} aria-hidden="true" />
            {sensor.tag}
            <span className="muted">· {sensor.kind}</span>
          </div>
          <h3 id={`chart-title-${sensor.tag}`}>{sensor.name}</h3>
        </div>
        <div className="chart-card__meta">
          <span>
            推荐 {formatNumber(sensor.recommended_band.low, 1)}–{formatNumber(sensor.recommended_band.high, 1)}{" "}
            {formatUnit(sensor.unit)}
          </span>
          <span>
            安全 {formatNumber(sensor.safe_limits.low, 1)}–{formatNumber(sensor.safe_limits.high, 1)}{" "}
            {formatUnit(sensor.unit)}
          </span>
          {tripHigh !== null && (
            <span className="chart-card__trip">
              <AlertTriangle size={12} aria-hidden="true" />
              联锁高高限 {formatNumber(tripHigh, 1)} {formatUnit(sensor.unit)}
            </span>
          )}
        </div>
      </div>
      {seriesResult.loading && <LoadingPanel label={`正在读取 ${sensor.tag} 时序…`} />}
      {seriesResult.error && (
        <ErrorPanel message={seriesResult.error} onRetry={seriesResult.reload} />
      )}
      {seriesResult.data && (
        <TelemetryChart sensor={sensor} points={seriesResult.data.points} faults={faults} />
      )}
    </section>
  );
}

export function TelemetrySection({
  runId,
  caseId,
  sensors,
  faults,
}: {
  runId: string;
  caseId: string;
  sensors: SensorMeta[];
  faults: FaultPlan[];
}) {
  return (
    <div className="chart-grid">
      {sensors.map((sensor) => (
        <ChartCard
          key={sensor.tag}
          runId={runId}
          caseId={caseId}
          sensor={sensor}
          faults={faults}
        />
      ))}
    </div>
  );
}
