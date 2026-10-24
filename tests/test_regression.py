"""回归对比：三个哈希、覆盖率、严重回归与非预期变化。"""

from __future__ import annotations

from collections.abc import Sequence

from ia_platform.core.models import (
    BaselineRecord,
    CaseCategory,
    CaseResult,
    Defect,
    DefectCode,
    DefectLevel,
    DomainHashes,
    RegressionKind,
    RunRecord,
    RunStatus,
    utc_now,
)
from ia_platform.evaluation.regression import compare_runs


def _defect(case_id: str, code: DefectCode, level: DefectLevel) -> Defect:
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
    *,
    fingerprint: str,
    detected: bool = False,
    false_alarms: int = 0,
    defects: Sequence[Defect] = (),
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        case_name=case_id,
        category=CaseCategory.FAULT,
        seed=7,
        detected=detected,
        correct_type=detected,
        target_correct=detected,
        false_alarms=false_alarms,
        fingerprint=fingerprint,
        defects=list(defects),
        artifact_dir=f"artifacts/{case_id}",
        duration_s=300.0,
    )


def _baseline(
    results: list[CaseResult],
    *,
    domain_hash: str = "domain-1",
    interlock_hash: str = "interlock-1",
    case_set_hash: str = "cases-1",
) -> BaselineRecord:
    return BaselineRecord(
        id="baseline-1",
        name="baseline",
        run_id="run-baseline",
        agent_version="1.0.0",
        created_at=utc_now(),
        seed_set=[7],
        case_set_hash=case_set_hash,
        domain_hash=domain_hash,
        interlock_hash=interlock_hash,
        results=results,
    )


def _candidate(
    results: list[CaseResult],
    *,
    domain_hash: str = "domain-1",
    interlock_hash: str = "interlock-1",
    case_set_hash: str = "cases-1",
) -> RunRecord:
    return RunRecord(
        id="run-candidate",
        name="candidate",
        suite_id="suite-test",
        agent_id="agent-candidate",
        agent_name="candidate",
        agent_version="2.0.0",
        seed=7,
        status=RunStatus.COMPLETED,
        created_at=utc_now(),
        case_ids=[item.case_id for item in results],
        case_results=results,
        domain_hashes=DomainHashes(
            domain_hash=domain_hash,
            interlock_hash=interlock_hash,
            case_set_hash=case_set_hash,
        ),
    )


def test_identical_conclusions_are_comparable_without_changes() -> None:
    base = _result("CASE-A", fingerprint="fp-a", detected=True, false_alarms=1)
    candidate = _result("CASE-A", fingerprint="fp-a", detected=True, false_alarms=1)
    report = compare_runs(_baseline([base]), _candidate([candidate]))
    assert report.comparable is True
    assert report.blockers == []
    assert report.severe_regressions == []
    assert report.unexpected_changes == []
    assert report.improvements == []
    assert report.fingerprint_match_rate == 1.0


def test_detection_loss_is_p0_and_fingerprint_change_is_unexpected() -> None:
    baseline_results = [
        _result("CASE-A", fingerprint="fp-a", detected=True),
        _result("CASE-B", fingerprint="fp-b", detected=True),
    ]
    candidate_results = [
        _result("CASE-A", fingerprint="fp-a", detected=True),
        _result(
            "CASE-B",
            fingerprint="fp-b2",
            detected=False,
            false_alarms=2,
            defects=[
                _defect("CASE-B", DefectCode.MISSED_FAULT, DefectLevel.P0)
            ],
        ),
    ]
    report = compare_runs(
        _baseline(baseline_results), _candidate(candidate_results)
    )
    assert report.comparable is True
    assert report.fingerprint_match_rate == 0.5
    severe = {(row.case_id, row.metric, row.kind) for row in report.severe_regressions}
    assert ("CASE-B", "detected", RegressionKind.SEVERE_REGRESSION) in severe
    assert (
        "CASE-B",
        DefectCode.MISSED_FAULT.value,
        RegressionKind.SEVERE_REGRESSION,
    ) in severe
    assert all(
        row.level == DefectLevel.P0
        for row in report.severe_regressions
        if row.case_id == "CASE-B"
    )
    unexpected = {(row.metric, row.level) for row in report.unexpected_changes}
    assert ("fingerprint", DefectLevel.P1) in unexpected
    assert ("false_alarms", DefectLevel.P1) in unexpected


def test_hash_mismatch_refuses_comparison() -> None:
    base = _base_result()
    candidate = _base_result()
    report = compare_runs(
        _baseline([base]),
        _candidate([candidate], domain_hash="domain-2"),
    )
    assert report.comparable is False
    assert any("domain_hash" in blocker for blocker in report.blockers)
    assert report.severe_regressions == []
    assert report.fingerprint_match_rate is None


def test_missing_case_in_candidate_refuses_partial_comparison() -> None:
    base = _base_result()
    report = compare_runs(
        _baseline([base, _result("CASE-B", fingerprint="fp-b")]),
        _candidate([_result("CASE-A", fingerprint="fp-a")]),
    )
    assert report.comparable is False
    assert any("CASE-B" in blocker for blocker in report.blockers)


def test_extra_case_in_candidate_also_refuses_comparison() -> None:
    report = compare_runs(
        _baseline([_base_result()]),
        _candidate(
            [
                _result("CASE-A", fingerprint="fp-a"),
                _result("CASE-EXTRA", fingerprint="fp-e"),
            ]
        ),
    )
    assert report.comparable is False
    assert any("CASE-EXTRA" in blocker for blocker in report.blockers)


def test_new_detection_is_classified_as_improvement() -> None:
    report = compare_runs(
        _baseline([_result("CASE-A", fingerprint="old", detected=False)]),
        _candidate([_result("CASE-A", fingerprint="new", detected=True)]),
    )
    assert report.comparable is True
    assert any(row.metric == "detected" for row in report.improvements)
    assert not report.severe_regressions


def test_same_behavior_across_agent_versions_keeps_fingerprint_match() -> None:
    base = _result("CASE-A", fingerprint="same", detected=True)
    candidate = _result("CASE-A", fingerprint="same", detected=True)
    report = compare_runs(_baseline([base]), _candidate([candidate]))
    assert report.fingerprint_match_rate == 1.0
    assert report.unexpected_changes == []


def _base_result() -> CaseResult:
    return _result("CASE-A", fingerprint="fp-a", detected=True)
