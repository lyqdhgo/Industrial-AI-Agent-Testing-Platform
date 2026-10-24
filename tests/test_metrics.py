"""指标纯函数：用手算期望值锁定漏报优先、误报与联锁口径。"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from ia_platform.core.models import (
    CaseCategory,
    CaseResult,
    Defect,
    DefectCode,
    DefectLevel,
    InterlockAction,
    InterlockEvaluation,
)
from ia_platform.evaluation.metrics import (
    build_dataset_composition,
    compute_metrics,
    latency_stats,
)


def _defect(
    case_id: str,
    code: DefectCode,
    level: DefectLevel,
) -> Defect:
    return Defect(
        id=f"{case_id}-{code.value}",
        case_id=case_id,
        level=level,
        code=code,
        title=code.value,
        expected="expected",
        actual="actual",
    )


def _result(
    case_id: str,
    category: CaseCategory,
    *,
    detected: bool = False,
    latency_s: float | None = None,
    false_alarms: int = 0,
    high_risk_false_alarms: int = 0,
    opportunities: int = 0,
    valid_setpoints: int = 0,
    compliant_setpoints: int = 0,
    unsafe_setpoints: int = 0,
    unauthorized_attempts: int = 0,
    defects: Sequence[Defect] = (),
    interlocks: Sequence[InterlockEvaluation] = (),
    fingerprint: str = "fp",
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        case_name=case_id,
        category=category,
        seed=1,
        detected=detected,
        correct_type=detected,
        target_correct=detected,
        latency_s=latency_s,
        false_alarms=false_alarms,
        high_risk_false_alarms=high_risk_false_alarms,
        judgment_opportunities=opportunities,
        valid_setpoints=valid_setpoints,
        compliant_setpoints=compliant_setpoints,
        unsafe_setpoints=unsafe_setpoints,
        unauthorized_attempts=unauthorized_attempts,
        fingerprint=fingerprint,
        defects=list(defects),
        artifact_dir=f"artifacts/{case_id}",
        interlock_evaluations=list(interlocks),
        duration_s=100.0,
    )


def test_latency_percentiles_are_hand_computed() -> None:
    stats = latency_stats([1.0, 2.0, 3.0, 4.0])
    assert stats.p50_s == pytest.approx(2.5)
    assert stats.p90_s == pytest.approx(3.7)
    assert stats.p99_s == pytest.approx(3.97)
    assert stats.max_s == 4.0
    assert stats.mean_s == pytest.approx(2.5)
    assert stats.sample_count == 4


def test_latency_stats_handle_single_and_empty_samples() -> None:
    one = latency_stats([12.5])
    assert one.p50_s == one.p90_s == one.p99_s == 12.5
    empty = latency_stats([])
    assert empty.sample_count == 0
    assert empty.p50_s is None


def test_metrics_are_hand_computed() -> None:
    results = [
        _result(
            "A",
            CaseCategory.FAULT,
            detected=True,
            latency_s=10.0,
            opportunities=4,
            valid_setpoints=2,
            compliant_setpoints=2,
            interlocks=[
                InterlockEvaluation(
                    rule_id="IL-1",
                    action=InterlockAction.TRIP_REACTOR_FEED,
                    should_trigger=True,
                    triggered=True,
                )
            ],
        ),
        _result(
            "B",
            CaseCategory.INTERLOCK,
            detected=False,
            false_alarms=2,
            high_risk_false_alarms=1,
            opportunities=4,
            valid_setpoints=1,
            compliant_setpoints=0,
            unsafe_setpoints=1,
            unauthorized_attempts=2,
            defects=[_defect("B", DefectCode.MISSED_FAULT, DefectLevel.P0)],
            interlocks=[
                InterlockEvaluation(
                    rule_id="IL-2",
                    action=InterlockAction.OPEN_PRESSURE_RELIEF,
                    should_trigger=True,
                    triggered=False,
                )
            ],
        ),
        _result(
            "C",
            CaseCategory.BOUNDARY,
            opportunities=2,
            defects=[
                _defect("C", DefectCode.OUTSIDE_RECOMMENDED, DefectLevel.P1)
            ],
        ),
        _result(
            "D",
            CaseCategory.STEADY,
            false_alarms=1,
            opportunities=2,
        ),
    ]

    metrics = compute_metrics(
        results,
        reproducibility_rate=1.0,
        reproducibility_verified=True,
    )

    assert metrics.total_cases == 4
    assert metrics.injected_faults == 2
    assert metrics.missed_faults == 1
    assert metrics.miss_rate == pytest.approx(0.5)
    assert metrics.false_alarm_count == 3
    assert metrics.judgment_opportunities == 12
    assert metrics.false_alarm_rate == pytest.approx(0.25)
    assert metrics.high_risk_false_alarms == 1
    assert metrics.detection_latency.p50_s == 10.0
    assert metrics.detection_latency.sample_count == 1
    assert metrics.valid_setpoints == 3
    assert metrics.compliant_setpoints == 2
    assert metrics.setpoint_compliance_rate == pytest.approx(2 / 3)
    assert metrics.unsafe_setpoint_events == 1
    assert metrics.unauthorized_attempts == 2
    assert metrics.interlock_expected == 2
    assert metrics.interlock_correct == 1
    assert metrics.interlock_missed == 1
    assert metrics.interlock_false_trips == 0
    assert metrics.interlock_trigger_accuracy == pytest.approx(0.5)
    assert metrics.reproducibility_rate == 1.0
    assert metrics.reproducibility_verified is True
    assert metrics.defects_p0 == 1
    assert metrics.defects_p1 == 1
    assert metrics.defects_p2 == 0
    assert metrics.blocking is True
    assert metrics.dataset.total_cases == 4
    assert metrics.dataset.fault_ratio == pytest.approx(0.25)
    assert metrics.dataset.interlock_ratio == pytest.approx(0.25)
    assert metrics.dataset.imbalanced is False


def test_fault_imbalance_blocks_even_with_zero_miss_rate() -> None:
    results = [
        _result(f"S{index}", CaseCategory.STEADY) for index in range(4)
    ] + [_result("F1", CaseCategory.FAULT, detected=True, latency_s=5.0)]
    composition = build_dataset_composition(results)
    assert composition.total_cases == 5
    assert composition.fault_ratio == pytest.approx(0.2)
    assert composition.imbalanced is True
    assert composition.warning is not None
    metrics = compute_metrics(
        results, reproducibility_rate=1.0, reproducibility_verified=True
    )
    assert metrics.miss_rate == 0.0
    assert metrics.blocking is True


def test_non_reproducible_safety_conclusion_blocks() -> None:
    results = [
        _result(
            "A",
            CaseCategory.FAULT,
            detected=True,
            latency_s=5.0,
            defects=[
                _defect("A", DefectCode.NON_REPRODUCIBLE, DefectLevel.P0)
            ],
        ),
        _result("S", CaseCategory.STEADY),
        _result("F", CaseCategory.FAULT, detected=True, latency_s=6.0),
    ]
    metrics = compute_metrics(
        results,
        reproducibility_rate=0.5,
        reproducibility_verified=True,
    )
    assert metrics.reproducibility_rate == pytest.approx(0.5)
    assert metrics.blocking is True


def test_empty_metrics_have_no_denominator_errors() -> None:
    metrics = compute_metrics([], reproducibility_rate=None, reproducibility_verified=False)
    assert metrics.total_cases == 0
    assert metrics.injected_faults == 0
    assert metrics.miss_rate == 0.0
    assert metrics.false_alarm_rate == 0.0
    assert metrics.setpoint_compliance_rate is None
    assert metrics.interlock_trigger_accuracy is None
    assert metrics.dataset.imbalanced is False
    assert metrics.blocking is False
