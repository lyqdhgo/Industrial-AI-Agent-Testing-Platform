"""结论指纹与同 seed 复现：只比较语义，不比较自然语言措辞。"""

from __future__ import annotations

from ia_platform.core.catalog import PlatformCatalog
from ia_platform.core.hashing import content_hash
from ia_platform.core.models import (
    AgentResponse,
    ControlKind,
    ControlRequest,
    DomainPack,
    FaultKind,
    RecommendationStatus,
    SetpointSuggestion,
)
from ia_platform.evaluation.checks import evaluate_case
from ia_platform.orchestration.runner import execute_case


def _normal_response(
    *,
    rationale: str,
    confidence: float,
    setpoint: float = 240.0,
) -> AgentResponse:
    return AgentResponse(
        status=RecommendationStatus.ANOMALY,
        fault_type=FaultKind.SUPER_TEMPERATURE,
        target_tag="TI-203",
        confidence=confidence,
        rationale_text=rationale,
        setpoints=[
            SetpointSuggestion(tag="TI-203", value=setpoint, unit="degC")
        ],
        control_requests=[
            ControlRequest(
                kind=ControlKind.SET_SETPOINT,
                tag="TI-203",
                value=setpoint,
                unit="degC",
                reason="降温",
            )
        ],
    )


def test_prose_and_confidence_do_not_change_conclusion_payload() -> None:
    first = _normal_response(rationale="温度持续上升，建议下调设定值。", confidence=0.91)
    second = _normal_response(
        rationale="根据趋势判断需要降温，理由措辞完全不同。",
        confidence=0.55,
    )
    assert first.normalized_fingerprint_payload() == second.normalized_fingerprint_payload()
    assert content_hash(first.normalized_fingerprint_payload()) == content_hash(
        second.normalized_fingerprint_payload()
    )


def test_setpoint_change_changes_conclusion_payload() -> None:
    first = _normal_response(rationale="same", confidence=0.8, setpoint=240.0)
    second = _normal_response(rationale="same", confidence=0.8, setpoint=245.0)
    assert first.normalized_fingerprint_payload() != second.normalized_fingerprint_payload()


def test_control_request_order_does_not_change_payload() -> None:
    first = _normal_response(rationale="same", confidence=0.8)
    second = first.model_copy(
        update={"control_requests": list(reversed(first.control_requests))}
    )
    assert first.normalized_fingerprint_payload() == second.normalized_fingerprint_payload()


def test_same_seed_produces_same_case_fingerprint(
    domain: DomainPack,
    catalog: PlatformCatalog,
) -> None:
    case = catalog.get_case("CASE-FAULT-005")
    agent = catalog.get_agent("mock-reference")
    first = execute_case(case, agent, domain, case.seed)
    second = execute_case(case, agent, domain, case.seed)
    first_result = evaluate_case(first, "artifacts/first")
    second_result = evaluate_case(second, "artifacts/second")
    assert first_result.fingerprint == second_result.fingerprint


def test_fingerprint_is_independent_of_agent_version_when_behavior_matches(
    domain: DomainPack,
    catalog: PlatformCatalog,
) -> None:
    case = catalog.get_case("CASE-STEADY-001")
    reference = catalog.get_agent("mock-reference")
    degraded = catalog.get_agent("mock-degraded")
    ref_evidence = execute_case(case, reference, domain, case.seed)
    deg_evidence = execute_case(case, degraded, domain, case.seed)
    ref_result = evaluate_case(ref_evidence, "artifacts/ref")
    deg_result = evaluate_case(deg_evidence, "artifacts/deg")
    assert ref_evidence.calls
    assert deg_evidence.calls
    assert ref_result.fingerprint == deg_result.fingerprint
