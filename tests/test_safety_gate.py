"""SafetyGate 顺序、P0 边界与 DCS 副作用隔离。"""

from __future__ import annotations

import pytest

from ia_platform.core.models import (
    AgentPermissions,
    ControlKind,
    ControlRequest,
    DomainPack,
    GateDecision,
    GateLayer,
    OperatorProfile,
    TraceEvent,
    TraceEventKind,
)
from ia_platform.simulation.safety import ProcessGuard, SafetyGate


def _permissions(
    *,
    tags: list[str] | None = None,
    high_risk: list[str] | None = None,
    kinds: list[ControlKind] | None = None,
) -> AgentPermissions:
    return AgentPermissions(
        allowed_tags=tags or ["TI-203"],
        high_risk_tags=[] if high_risk is None else high_risk,
        allowed_control_kinds=kinds or [ControlKind.SET_SETPOINT],
    )


def _submit(
    gate: SafetyGate,
    request: ControlRequest,
    *,
    t_s: float = 15.0,
    true_values: dict[str, float] | None = None,
    active_rule_ids: list[str] | None = None,
) -> tuple[GateDecision, list[TraceEvent], list[tuple[str, float, str, float]]]:
    writes: list[tuple[str, float, str, float]] = []

    def apply(tag: str, value: float, unit: str, submitted_at_s: float) -> None:
        writes.append((tag, value, unit, submitted_at_s))

    decision, events = gate.submit(
        request,
        t_s,
        true_values or {"TI-203": 240.0, "PI-203": 1.6},
        active_rule_ids or [],
        apply,
    )
    return decision, events, writes


def test_recommended_setpoint_is_allowed_and_written_once(domain: DomainPack) -> None:
    gate = SafetyGate(domain, _permissions(), OperatorProfile())
    decision, events, writes = _submit(
        gate,
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag="TI-203",
            value=240.0,
            unit="°C",
            reason="降温至推荐区间",
        ),
    )
    assert decision.allowed is True
    assert decision.executed is True
    assert decision.blocking_layer == GateLayer.NONE
    assert writes == [("TI-203", 240.0, "degC", 15.0)]
    assert [event.kind for event in events] == [
        TraceEventKind.GATE_ALLOWED,
        TraceEventKind.DCS_WRITE,
    ]


def test_outside_recommended_but_inside_safe_is_allowed_with_p1_reason(
    domain: DomainPack,
) -> None:
    gate = SafetyGate(domain, _permissions(), OperatorProfile())
    decision, _, writes = _submit(
        gate,
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag="TI-203",
            value=200.0,
            unit="degC",
            reason="降负荷",
        ),
    )
    assert decision.allowed is True
    assert decision.executed is True
    assert "推荐区间" in decision.reason
    assert len(writes) == 1


def test_safe_limit_violation_is_blocked_before_confirmation(
    domain: DomainPack,
) -> None:
    gate = SafetyGate(
        domain,
        _permissions(high_risk=["TI-203"]),
        OperatorProfile(available=False, confirm_high_risk=False),
    )
    decision, events, writes = _submit(
        gate,
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag="TI-203",
            value=405.0,
            unit="degC",
            reason="错误建议",
        ),
    )
    assert decision.allowed is False
    assert decision.executed is False
    # 即便人工确认也缺失，必须先报工艺边界，而不是拿“未确认”掩盖越界。
    assert decision.blocking_layer == GateLayer.PROCESS_GUARD
    assert decision.violated_rule == "safe_limits"
    assert writes == []
    assert [event.kind for event in events] == [TraceEventKind.GATE_BLOCKED]


def test_high_risk_setpoint_without_confirmation_is_suspended(
    domain: DomainPack,
) -> None:
    gate = SafetyGate(
        domain,
        _permissions(high_risk=["TI-203"]),
        OperatorProfile(available=False),
    )
    decision, events, writes = _submit(
        gate,
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag="TI-203",
            value=240.0,
            unit="degC",
            reason="调整温度",
        ),
    )
    assert decision.allowed is False
    assert decision.blocking_layer == GateLayer.CONFIRMATION
    assert decision.requires_confirmation is True
    assert writes == []
    assert [event.kind for event in events] == [
        TraceEventKind.CONFIRMATION_REQUIRED,
        TraceEventKind.GATE_BLOCKED,
    ]


def test_high_risk_setpoint_with_operator_confirmation_is_allowed(
    domain: DomainPack,
) -> None:
    gate = SafetyGate(
        domain,
        _permissions(high_risk=["TI-203"]),
        OperatorProfile(
            available=True,
            operator_id="op-42",
            role="operator",
            confirm_high_risk=True,
        ),
    )
    decision, events, writes = _submit(
        gate,
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag="TI-203",
            value=240.0,
            unit="degC",
            reason="人工确认后的调整",
        ),
    )
    assert decision.allowed is True
    assert decision.executed is True
    assert decision.confirmed_by == "op-42"
    assert writes == [("TI-203", 240.0, "degC", 15.0)]
    assert [event.kind for event in events] == [
        TraceEventKind.CONFIRMATION_REQUIRED,
        TraceEventKind.CONFIRMATION_GRANTED,
        TraceEventKind.GATE_ALLOWED,
        TraceEventKind.DCS_WRITE,
    ]


def test_engineer_role_cannot_confirm_high_risk(domain: DomainPack) -> None:
    gate = SafetyGate(
        domain,
        _permissions(high_risk=["TI-203"]),
        OperatorProfile(
            available=True,
            role="engineer",
            confirm_high_risk=True,
        ),
    )
    decision, _, writes = _submit(
        gate,
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag="TI-203",
            value=240.0,
            unit="degC",
            reason="工程师自行确认",
        ),
    )
    assert decision.allowed is False
    assert decision.blocking_layer == GateLayer.CONFIRMATION
    assert writes == []


def test_active_sis_blocks_agent_command(domain: DomainPack) -> None:
    gate = SafetyGate(domain, _permissions(), OperatorProfile())
    decision, events, writes = _submit(
        gate,
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag="TI-203",
            value=240.0,
            unit="degC",
            reason="超温后仍尝试写温度",
        ),
        true_values={"TI-203": 421.0},
    )
    assert decision.allowed is False
    assert decision.blocking_layer == GateLayer.SIS
    assert decision.interlock_rule_ids == ["IL-TI203-HIHI"]
    assert writes == []
    assert [event.kind for event in events] == [
        TraceEventKind.SIS_BLOCKED,
        TraceEventKind.GATE_BLOCKED,
    ]


def test_unauthorized_tag_is_blocked_at_permission_layer(domain: DomainPack) -> None:
    gate = SafetyGate(
        domain,
        _permissions(tags=["FI-201"]),
        OperatorProfile(),
    )
    decision, _, writes = _submit(
        gate,
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag="TI-203",
            value=240.0,
            unit="degC",
            reason="越权位号",
        ),
    )
    assert decision.allowed is False
    assert decision.blocking_layer == GateLayer.PERMISSION
    assert decision.violated_rule == "permission.tag"
    assert writes == []


def test_interlock_bypass_request_is_always_rejected(domain: DomainPack) -> None:
    gate = SafetyGate(
        domain,
        _permissions(kinds=[ControlKind.REQUEST_BYPASS_INTERLOCK]),
        OperatorProfile(),
    )
    decision, _, writes = _submit(
        gate,
        ControlRequest(
            kind=ControlKind.REQUEST_BYPASS_INTERLOCK,
            tag="TI-203",
            reason="申请旁路高高限联锁",
        ),
    )
    assert decision.allowed is False
    assert decision.blocking_layer == GateLayer.PERMISSION
    assert decision.violated_rule == "sis.bypass"
    assert writes == []


@pytest.mark.parametrize(
    ("value", "unit", "rule"),
    [
        (9999.0, "degC", "range"),
        (float("nan"), "degC", "invalid"),
    ],
)
def test_invalid_input_never_reaches_dcs(
    domain: DomainPack,
    value: float,
    unit: str,
    rule: str,
) -> None:
    gate = SafetyGate(domain, _permissions(), OperatorProfile())
    decision, _, writes = _submit(
        gate,
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag="TI-203",
            value=value,
            unit=unit,
            reason="非法输入",
        ),
    )
    assert decision.allowed is False
    assert decision.blocking_layer == GateLayer.PROCESS_GUARD
    assert decision.violated_rule == rule
    assert writes == []


def test_process_guard_reads_domain_bounds(domain: DomainPack) -> None:
    guard = ProcessGuard(domain)
    assert guard.check_setpoint("TI-203", 240.0, "degC").severity is None
    outside = guard.check_setpoint("TI-203", 200.0, "degC")
    assert outside.allowed is True
    assert outside.severity is not None
    assert outside.severity.value == "P1"
    unknown = guard.check_setpoint("XX-999", 1.0, "MPa")
    assert unknown.allowed is False
    assert unknown.violated_bound == "unknown_tag"
    unknown_unit = guard.check_setpoint("TI-203", 240.0, "bar")
    assert unknown_unit.allowed is False
    assert unknown_unit.violated_bound == "unit"


def test_dcs_callback_is_not_called_for_blocked_commands(domain: DomainPack) -> None:
    calls: list[str] = []

    def apply(tag: str, value: float, unit: str, t_s: float) -> None:
        calls.append(tag)

    gate = SafetyGate(domain, _permissions(), OperatorProfile())
    gate.submit(
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag="TI-203",
            value=500.0,
            unit="degC",
            reason="越界",
        ),
        15.0,
        {"TI-203": 240.0},
        [],
        apply,
    )
    assert calls == []
