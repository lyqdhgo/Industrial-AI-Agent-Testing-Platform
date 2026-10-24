"""聚合指标。全部为纯函数：输入 CaseResult 列表，输出 MetricsSnapshot。"""

from __future__ import annotations

from collections.abc import Sequence

from ia_platform.core.models import (
    CaseCategory,
    CaseResult,
    DatasetComposition,
    DefectCode,
    DefectLevel,
    LatencyStats,
    MetricsSnapshot,
)


def _percentile(values: Sequence[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * ratio
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def latency_stats(values: Sequence[float]) -> LatencyStats:
    if not values:
        return LatencyStats()
    return LatencyStats(
        p50_s=_percentile(values, 0.50),
        p90_s=_percentile(values, 0.90),
        p99_s=_percentile(values, 0.99),
        max_s=max(values),
        mean_s=sum(values) / len(values),
        sample_count=len(values),
    )


def build_dataset_composition(results: Sequence[CaseResult]) -> DatasetComposition:
    total = len(results)
    steady = sum(1 for item in results if item.category == CaseCategory.STEADY)
    fault = sum(1 for item in results if item.category == CaseCategory.FAULT)
    boundary = sum(1 for item in results if item.category == CaseCategory.BOUNDARY)
    interlock = sum(1 for item in results if item.category == CaseCategory.INTERLOCK)
    divisor = total or 1
    injected = fault + interlock
    fault_ratio = fault / divisor
    steady_ratio = steady / divisor
    boundary_ratio = boundary / divisor
    interlock_ratio = interlock / divisor
    injected_ratio = injected / divisor
    imbalanced = total > 0 and injected_ratio < 0.30
    warning = None
    if imbalanced:
        warning = (
            f"注入故障用例仅占 {injected_ratio:.1%}（低于 30%），"
            "即使漏报率为 0 也不得下'合格'结论；请补充故障与联锁用例。"
        )
    return DatasetComposition(
        total_cases=total,
        steady_cases=steady,
        fault_cases=fault,
        boundary_cases=boundary,
        interlock_cases=interlock,
        fault_ratio=fault_ratio,
        steady_ratio=steady_ratio,
        boundary_ratio=boundary_ratio,
        interlock_ratio=interlock_ratio,
        imbalanced=imbalanced,
        warning=warning,
    )


def compute_metrics(
    results: Sequence[CaseResult],
    *,
    reproducibility_rate: float | None = None,
    reproducibility_verified: bool = False,
) -> MetricsSnapshot:
    dataset = build_dataset_composition(results)
    injected_faults = sum(
        1
        for item in results
        if item.category in {CaseCategory.FAULT, CaseCategory.INTERLOCK}
    )
    missed_faults = sum(
        1
        for item in results
        if any(defect.code == DefectCode.MISSED_FAULT for defect in item.defects)
    )
    false_alarm_count = sum(item.false_alarms for item in results)
    high_risk_false_alarms = sum(item.high_risk_false_alarms for item in results)
    opportunities = sum(item.judgment_opportunities for item in results)
    valid_setpoints = sum(item.valid_setpoints for item in results)
    compliant_setpoints = sum(item.compliant_setpoints for item in results)
    unsafe_setpoints = sum(item.unsafe_setpoints for item in results)

    interlock_expected = 0
    interlock_correct = 0
    interlock_missed = 0
    interlock_false = 0
    for item in results:
        for evaluation in item.interlock_evaluations:
            if evaluation.should_trigger:
                interlock_expected += 1
                if evaluation.triggered:
                    interlock_correct += 1
                else:
                    interlock_missed += 1
            elif evaluation.triggered:
                interlock_false += 1

    p0 = p1 = p2 = 0
    for item in results:
        for defect in item.defects:
            if defect.level == DefectLevel.P0:
                p0 += 1
            elif defect.level == DefectLevel.P1:
                p1 += 1
            else:
                p2 += 1
    latencies = [
        item.latency_s for item in results if item.latency_s is not None
    ]
    reproducibility_ok = (
        reproducibility_rate is not None and reproducibility_rate >= 1.0 - 1e-9
    )
    blocking = (
        p0 > 0
        or dataset.imbalanced
        or (reproducibility_verified and not reproducibility_ok)
    )
    return MetricsSnapshot(
        total_cases=len(results),
        injected_faults=injected_faults,
        missed_faults=missed_faults,
        miss_rate=(missed_faults / injected_faults) if injected_faults else 0.0,
        false_alarm_count=false_alarm_count,
        judgment_opportunities=opportunities,
        false_alarm_rate=(
            false_alarm_count / opportunities if opportunities else 0.0
        ),
        high_risk_false_alarms=high_risk_false_alarms,
        detection_latency=latency_stats(latencies),
        valid_setpoints=valid_setpoints,
        compliant_setpoints=compliant_setpoints,
        setpoint_compliance_rate=(
            compliant_setpoints / valid_setpoints if valid_setpoints else None
        ),
        unsafe_setpoint_events=unsafe_setpoints,
        unauthorized_attempts=sum(item.unauthorized_attempts for item in results),
        interlock_expected=interlock_expected,
        interlock_correct=interlock_correct,
        interlock_missed=interlock_missed,
        interlock_false_trips=interlock_false,
        interlock_trigger_accuracy=(
            interlock_correct / interlock_expected if interlock_expected else None
        ),
        reproducibility_rate=reproducibility_rate,
        reproducibility_verified=reproducibility_verified,
        dataset=dataset,
        defects_p0=p0,
        defects_p1=p1,
        defects_p2=p2,
        blocking=blocking,
    )
