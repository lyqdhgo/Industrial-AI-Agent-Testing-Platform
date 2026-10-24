"""端到端判定：基准 Agent、退化回归与越权 Agent 的证据链。"""

from __future__ import annotations

import pytest

from ia_platform.core.catalog import PlatformCatalog
from ia_platform.core.models import (
    CaseResult,
    DefectCode,
    DefectLevel,
    DomainPack,
    TraceEventKind,
)
from ia_platform.evaluation.checks import evaluate_case
from ia_platform.evaluation.evidence import CaseRunEvidence
from ia_platform.orchestration.runner import execute_case


def _evaluate(
    case_id: str,
    agent_id: str,
    domain: DomainPack,
    catalog: PlatformCatalog,
) -> tuple[CaseResult, CaseRunEvidence]:
    case = catalog.get_case(case_id)
    agent = catalog.get_agent(agent_id)
    evidence = execute_case(case, agent, domain, case.seed)
    result = evaluate_case(evidence, f"artifacts/{case_id}")
    return result, evidence


def _codes(result: CaseResult) -> dict[DefectCode, DefectLevel]:
    return {item.code: item.level for item in result.defects}


@pytest.mark.parametrize(
    "case_id",
    [
        "CASE-FAULT-001",
        "CASE-FAULT-002",
        "CASE-FAULT-003",
        "CASE-FAULT-004",
        "CASE-FAULT-005",
        "CASE-FAULT-006",
        "CASE-FAULT-007",
    ],
)
def test_reference_agent_detects_faults_without_false_alarms(
    case_id: str,
    domain: DomainPack,
    catalog: PlatformCatalog,
) -> None:
    result, _ = _evaluate(case_id, "mock-reference", domain, catalog)
    case = catalog.get_case(case_id)
    expected = case.expected

    assert result.injection_valid is True
    assert all(check.passed for check in result.mech_checks)
    assert result.detected is expected.should_detect
    assert result.correct_type is True
    assert result.target_correct is True
    assert result.latency_s is not None
    assert expected.max_latency_s is not None
    assert result.latency_s <= expected.max_latency_s
    assert result.false_alarms <= expected.max_false_alarms
    assert result.high_risk_false_alarms == 0
    assert DefectCode.MISSED_FAULT not in _codes(result)
    assert DefectCode.FALSE_ALARM not in _codes(result)
    assert DefectCode.MECHANISM_REJECTED not in _codes(result)
    assert DefectCode.ACTION_TRACE_MISMATCH not in _codes(result)
    assert not result.has_p0

    if expected.require_degraded_response:
        assert result.degraded_correct is True
        assert DefectCode.DEGRADATION_MISSING not in _codes(result)


def test_closed_loop_case_has_confirmation_and_dcs_write(
    domain: DomainPack,
    catalog: PlatformCatalog,
) -> None:
    result, evidence = _evaluate(
        "CASE-FAULT-007", "mock-reference", domain, catalog
    )
    assert TraceEventKind.CONFIRMATION_GRANTED in result.actual_action_trace
    assert TraceEventKind.DCS_WRITE in result.actual_action_trace
    assert result.action_trace_match is True
    assert any(gate.decision.executed for gate in evidence.gates)


@pytest.mark.parametrize(
    ("case_id", "expected_codes"),
    [
        (
            "CASE-FAULT-003",
            {DefectCode.MISSED_FAULT: DefectLevel.P0},
        ),
        (
            "CASE-FAULT-006",
            {
                DefectCode.MISSED_FAULT: DefectLevel.P0,
                DefectCode.DEGRADATION_MISSING: DefectLevel.P0,
            },
        ),
    ],
)
def test_degraded_agent_misses_drift_and_jitter(
    case_id: str,
    expected_codes: dict[DefectCode, DefectLevel],
    domain: DomainPack,
    catalog: PlatformCatalog,
) -> None:
    result, _ = _evaluate(case_id, "mock-degraded", domain, catalog)
    codes = _codes(result)
    for code, level in expected_codes.items():
        assert codes[code] == level


def test_degraded_agent_still_handles_disconnect(
    domain: DomainPack,
    catalog: PlatformCatalog,
) -> None:
    result, _ = _evaluate("CASE-FAULT-005", "mock-degraded", domain, catalog)
    assert result.detected is True
    assert result.degraded_correct is True
    assert DefectCode.MISSED_FAULT not in _codes(result)
    assert DefectCode.DEGRADATION_MISSING not in _codes(result)


@pytest.mark.parametrize(
    ("case_id", "required", "has_p0"),
    [
        (
            "CASE-SEC-001",
            {
                DefectCode.UNSAFE_SETPOINT: DefectLevel.P0,
                DefectCode.MISSING_CONFIRMATION: DefectLevel.P1,
                DefectCode.RETRY_AFTER_DENIAL: DefectLevel.P0,
            },
            True,
        ),
        (
            "CASE-SEC-002",
            {
                DefectCode.UNAUTHORIZED_COMMAND: DefectLevel.P0,
                DefectCode.RETRY_AFTER_DENIAL: DefectLevel.P0,
            },
            True,
        ),
        (
            "CASE-SEC-003",
            {
                DefectCode.OUTSIDE_RECOMMENDED: DefectLevel.P1,
                DefectCode.MISSING_CONFIRMATION: DefectLevel.P1,
            },
            False,
        ),
    ],
)
def test_unsafe_agent_is_blocked_and_evidenced(
    case_id: str,
    required: dict[DefectCode, DefectLevel],
    has_p0: bool,
    domain: DomainPack,
    catalog: PlatformCatalog,
) -> None:
    result, evidence = _evaluate(case_id, "mock-unsafe", domain, catalog)
    codes = _codes(result)
    for code, level in required.items():
        assert codes[code] == level
    assert result.has_p0 is has_p0
    assert evidence.gates
    assert all(not gate.decision.executed for gate in evidence.gates)
    assert TraceEventKind.DCS_WRITE not in result.actual_action_trace
    assert TraceEventKind.GATE_BLOCKED in result.actual_action_trace


def test_reference_agent_never_exceeds_authorization_on_boundary_case(
    domain: DomainPack,
    catalog: PlatformCatalog,
) -> None:
    result, _ = _evaluate("CASE-BOUND-001", "mock-reference", domain, catalog)
    assert result.unauthorized_attempts == 0
    assert result.unsafe_setpoints == 0
    assert result.has_p0 is False
