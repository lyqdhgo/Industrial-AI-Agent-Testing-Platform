import type { RunSummary } from "../types";

export function runP0(run: RunSummary): number {
  if (run.metrics) {
    return run.metrics.defects_p0;
  }
  return run.cases.reduce((total, item) => total + item.p0, 0);
}

export function runP1(run: RunSummary): number {
  if (run.metrics) {
    return run.metrics.defects_p1;
  }
  return run.cases.reduce((total, item) => total + item.p1, 0);
}

export function runMissRate(run: RunSummary): number | null {
  if (!run.metrics || run.metrics.injected_faults === 0) {
    return null;
  }
  return run.metrics.miss_rate;
}

export function hasCompletedMetrics(run: RunSummary): boolean {
  return run.status === "completed" && run.metrics !== null;
}
