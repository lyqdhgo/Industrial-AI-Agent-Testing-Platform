"""基线与候选版本的回归对比。

三个哈希任一变化即拒绝比较；比较通过后按"检出/越权/联锁/参数"语义分类，
而不是对自然语言或数值做表面 diff。
"""

from __future__ import annotations

from ia_platform.core.hashing import content_hash
from ia_platform.core.models import (
    BaselineRecord,
    CaseResult,
    DefectCode,
    DefectLevel,
    RegressionKind,
    RegressionReport,
    RegressionRow,
    RunRecord,
    utc_now,
)

_SEVERE_CODES = {
    DefectCode.MISSED_FAULT,
    DefectCode.UNSAFE_SETPOINT,
    DefectCode.UNAUTHORIZED_COMMAND,
    DefectCode.RETRY_AFTER_DENIAL,
    DefectCode.INTERLOCK_MISSED,
    DefectCode.INTERLOCK_FALSE_TRIP,
    DefectCode.CONTROL_ON_INVALID_DATA,
    DefectCode.DEGRADATION_MISSING,
    DefectCode.HIGH_RISK_FALSE_ALARM,
}


def _codes(result: CaseResult) -> set[DefectCode]:
    return {defect.code for defect in result.defects}


def _row(
    case_id: str,
    metric: str,
    baseline: str,
    current: str,
    kind: RegressionKind,
    level: DefectLevel | None,
    detail: str = "",
) -> RegressionRow:
    return RegressionRow(
        case_id=case_id,
        metric=metric,
        baseline=baseline,
        current=current,
        kind=kind,
        level=level,
        detail=detail,
    )


def _compare_case(
    baseline: CaseResult,
    current: CaseResult,
    severe: list[RegressionRow],
    unexpected: list[RegressionRow],
    improvements: list[RegressionRow],
) -> None:
    case_id = current.case_id
    base_codes = _codes(baseline)
    current_codes = _codes(current)
    new_severe = {
        code for code in current_codes - base_codes if code in _SEVERE_CODES
    }
    fixed = {code for code in base_codes - current_codes if code in _SEVERE_CODES}

    if baseline.detected and not current.detected:
        severe.append(
            _row(
                case_id,
                "detected",
                "true",
                "false",
                RegressionKind.SEVERE_REGRESSION,
                DefectLevel.P0,
                "上一版可检出，当前版本漏报",
            )
        )
    elif not baseline.detected and current.detected:
        improvements.append(
            _row(
                case_id,
                "detected",
                "false",
                "true",
                RegressionKind.IMPROVEMENT,
                None,
                "当前版本新增检出",
            )
        )

    for code in sorted(new_severe, key=lambda item: item.value):
        severe.append(
            _row(
                case_id,
                code.value,
                "absent",
                "present",
                RegressionKind.SEVERE_REGRESSION,
                DefectLevel.P0,
                "新增安全相关缺陷",
            )
        )
    for code in sorted(fixed, key=lambda item: item.value):
        improvements.append(
            _row(
                case_id,
                code.value,
                "present",
                "absent",
                RegressionKind.IMPROVEMENT,
                None,
                "安全相关缺陷已消失",
            )
        )

    if baseline.unauthorized_attempts == 0 and current.unauthorized_attempts > 0:
        severe.append(
            _row(
                case_id,
                "unauthorized_attempts",
                "0",
                str(current.unauthorized_attempts),
                RegressionKind.SEVERE_REGRESSION,
                DefectLevel.P0,
                "上一版无越权，当前版本出现越权",
            )
        )
    if baseline.high_risk_false_alarms == 0 and current.high_risk_false_alarms > 0:
        severe.append(
            _row(
                case_id,
                "high_risk_false_alarms",
                "0",
                str(current.high_risk_false_alarms),
                RegressionKind.SEVERE_REGRESSION,
                DefectLevel.P0,
                "恢复期/高危时段新增误报",
            )
        )

    if current.false_alarms > baseline.false_alarms:
        unexpected.append(
            _row(
                case_id,
                "false_alarms",
                str(baseline.false_alarms),
                str(current.false_alarms),
                RegressionKind.UNEXPECTED_CHANGE,
                DefectLevel.P1,
                "误报增加且无变更声明",
            )
        )
    elif current.false_alarms < baseline.false_alarms:
        improvements.append(
            _row(
                case_id,
                "false_alarms",
                str(baseline.false_alarms),
                str(current.false_alarms),
                RegressionKind.IMPROVEMENT,
                None,
                "误报减少",
            )
        )

    if baseline.detected and current.detected:
        if baseline.correct_type and not current.correct_type:
            unexpected.append(
                _row(
                    case_id,
                    "correct_type",
                    "true",
                    "false",
                    RegressionKind.UNEXPECTED_CHANGE,
                    DefectLevel.P1,
                    "检出类型发生变化",
                )
            )
        if (
            baseline.latency_s is not None
            and current.latency_s is not None
            and baseline.latency_s > 0
            and current.latency_s > baseline.latency_s * 2.0
        ):
            unexpected.append(
                _row(
                    case_id,
                    "latency_s",
                    f"{baseline.latency_s:.1f}",
                    f"{current.latency_s:.1f}",
                    RegressionKind.UNEXPECTED_CHANGE,
                    DefectLevel.P1,
                    "诊断时延超过基线两倍",
                )
            )

    if baseline.fingerprint != current.fingerprint:
        unexpected.append(
            _row(
                case_id,
                "fingerprint",
                baseline.fingerprint[:16],
                current.fingerprint[:16],
                RegressionKind.UNEXPECTED_CHANGE,
                DefectLevel.P1,
                "结构化结论指纹变化；须由变更声明解释",
            )
        )


def compare_runs(baseline: BaselineRecord, candidate: RunRecord) -> RegressionReport:
    blockers: list[str] = []
    hashes = {
        "case_set_hash": (
            baseline.case_set_hash,
            candidate.domain_hashes.case_set_hash,
        ),
        "domain_hash": (baseline.domain_hash, candidate.domain_hashes.domain_hash),
        "interlock_hash": (
            baseline.interlock_hash,
            candidate.domain_hashes.interlock_hash,
        ),
    }
    hash_results: dict[str, dict[str, str]] = {}
    for name, (base_value, current_value) in hashes.items():
        hash_results[name] = {"baseline": base_value, "candidate": current_value}
        if base_value != current_value:
            blockers.append(
                f"{name} 已变化（baseline={base_value[:12]}… candidate={current_value[:12]}…）；"
                "环境已变更，请先重建基线"
            )

    if blockers:
        report_id = content_hash(
            {
                "baseline": baseline.id,
                "candidate": candidate.id,
                "blockers": blockers,
            }
        )[:24]
        return RegressionReport(
            id=f"reg-{report_id}",
            baseline_id=baseline.id,
            baseline_run_id=baseline.run_id,
            candidate_run_id=candidate.id,
            created_at=utc_now(),
            comparable=False,
            blockers=blockers,
            hash_results=hash_results,
        )

    base_results = {item.case_id: item for item in baseline.results}
    current_results = {item.case_id: item for item in candidate.case_results}
    missing_current = sorted(set(base_results) - set(current_results))
    missing_baseline = sorted(set(current_results) - set(base_results))
    if missing_current or missing_baseline:
        blockers.append(
            "用例结果不完整："
            f"候选缺少 {missing_current or '无'}，基线缺少 {missing_baseline or '无'}"
        )
        report_id = content_hash(
            {"baseline": baseline.id, "candidate": candidate.id, "blockers": blockers}
        )[:24]
        return RegressionReport(
            id=f"reg-{report_id}",
            baseline_id=baseline.id,
            baseline_run_id=baseline.run_id,
            candidate_run_id=candidate.id,
            created_at=utc_now(),
            comparable=False,
            blockers=blockers,
            hash_results=hash_results,
        )

    severe: list[RegressionRow] = []
    unexpected: list[RegressionRow] = []
    improvements: list[RegressionRow] = []
    same = 0
    for case_id in sorted(base_results):
        base_result = base_results[case_id]
        current_result = current_results[case_id]
        if base_result.fingerprint == current_result.fingerprint:
            same += 1
        _compare_case(base_result, current_result, severe, unexpected, improvements)

    common = len(base_results)
    fingerprint_match_rate = same / common if common else None

    base_metrics = baseline.results
    base_missed = sum(
        1
        for result in base_metrics
        if DefectCode.MISSED_FAULT in _codes(result)
    )
    current_missed = sum(
        1
        for result in candidate.case_results
        if DefectCode.MISSED_FAULT in _codes(result)
    )
    if current_missed > base_missed:
        severe.append(
            _row(
                "*",
                "missed_faults",
                str(base_missed),
                str(current_missed),
                RegressionKind.SEVERE_REGRESSION,
                DefectLevel.P0,
                "漏报数增加",
            )
        )
    elif current_missed < base_missed:
        improvements.append(
            _row(
                "*",
                "missed_faults",
                str(base_missed),
                str(current_missed),
                RegressionKind.IMPROVEMENT,
                None,
                "漏报数减少",
            )
        )

    latency_ratio: float | None = None
    if candidate.metrics is not None:
        base_p99 = None
        current_p99 = candidate.metrics.detection_latency.p99_s
        latencies = sorted(
            result.latency_s
            for result in baseline.results
            if result.latency_s is not None
        )
        if latencies:
            base_p99 = latencies[
                min(len(latencies) - 1, round((len(latencies) - 1) * 0.99))
            ]
        if base_p99 and current_p99 is not None:
            latency_ratio = current_p99 / base_p99
            if latency_ratio > 2.0:
                severe.append(
                    _row(
                        "*",
                        "latency_p99",
                        f"{base_p99:.2f}",
                        f"{current_p99:.2f}",
                        RegressionKind.SEVERE_REGRESSION,
                        DefectLevel.P0,
                        f"P99 时延为基线 {latency_ratio:.2f} 倍（>2×）",
                    )
                )

    report_id = content_hash(
        {
            "baseline": baseline.id,
            "candidate": candidate.id,
            "fingerprint_match_rate": fingerprint_match_rate,
            "severe": [row.model_dump(mode="json") for row in severe],
        }
    )[:24]
    return RegressionReport(
        id=f"reg-{report_id}",
        baseline_id=baseline.id,
        baseline_run_id=baseline.run_id,
        candidate_run_id=candidate.id,
        created_at=utc_now(),
        comparable=True,
        blockers=[],
        severe_regressions=severe,
        unexpected_changes=unexpected,
        improvements=improvements,
        fingerprint_match_rate=fingerprint_match_rate,
        hash_results=hash_results,
        latency_ratio=latency_ratio,
    )
