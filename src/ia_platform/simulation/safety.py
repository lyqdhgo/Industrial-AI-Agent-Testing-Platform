"""ProcessGuard 与 SafetyGate。

唯一控制入口，判定顺序不可调换：
权限 → 工艺边界 → 人工确认 → SIS 联锁 → DCS 执行。
任何一步拒绝都不会产生 DCS 副作用；SIS 不可被 Agent 配置或旁路。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from ia_platform.core.models import (
    AgentPermissions,
    ControlKind,
    ControlRequest,
    DefectLevel,
    DomainPack,
    GateDecision,
    GateLayer,
    InterlockRule,
    OperatorProfile,
    TraceEvent,
    TraceEventKind,
)
from ia_platform.core.units import canonical_unit, ensure_unit, is_sentinel_value


@dataclass(frozen=True)
class GuardVerdict:
    allowed: bool
    severity: DefectLevel | None
    violated_bound: str | None
    reason: str
    within_recommended: bool


class ProcessGuard:
    """独立工艺约束闸门。只读 domain 边界，不接受 Agent 自证。"""

    def __init__(self, domain: DomainPack) -> None:
        self.domain = domain

    def check_setpoint(self, tag: str, value: float, unit: str) -> GuardVerdict:
        if tag not in self.domain.sensors:
            return GuardVerdict(False, DefectLevel.P0, "unknown_tag", f"未知测点 {tag}", False)
        sensor = self.domain.sensor(tag)
        try:
            expected_unit = canonical_unit(unit)
        except ValueError:
            return GuardVerdict(False, DefectLevel.P0, "unit", f"未知单位 {unit}", False)
        try:
            ensure_unit(expected_unit, sensor.unit, f"设定值 {tag}")
        except ValueError as exc:
            return GuardVerdict(False, DefectLevel.P0, "unit", str(exc), False)
        if not math.isfinite(value):
            return GuardVerdict(False, DefectLevel.P0, "invalid", "设定值不是有限数", False)

        measurement_range = sensor.instrument_range
        if is_sentinel_value(value, measurement_range.low, measurement_range.high):
            return GuardVerdict(
                False,
                DefectLevel.P0,
                "range",
                f"{tag}={value}{unit} 超出仪表量程 "
                f"[{measurement_range.low}, {measurement_range.high}]，数据无效",
                False,
            )

        bound = self.domain.bounds_for(tag)
        if not bound.safe_limits.contains(value, unit):
            return GuardVerdict(
                False,
                DefectLevel.P0,
                "safe_limits",
                f"{tag}={value}{unit} 越安全边界 "
                f"[{bound.safe_limits.low}, {bound.safe_limits.high}]",
                False,
            )
        if not bound.recommended_band.contains(value, unit):
            return GuardVerdict(
                True,
                DefectLevel.P1,
                "recommended_band",
                f"{tag}={value}{unit} 位于安全边界内但超出推荐区间 "
                f"[{bound.recommended_band.low}, {bound.recommended_band.high}]",
                False,
            )
        return GuardVerdict(True, None, None, f"{tag}={value}{unit} 通过工艺边界校验", True)

    def check_command(self, request: ControlRequest) -> GuardVerdict:
        if request.kind != ControlKind.SET_SETPOINT:
            return GuardVerdict(True, None, None, "非 DCS 设定值请求，不执行工艺边界校验", False)
        assert request.value is not None and request.unit is not None
        return self.check_setpoint(request.tag, request.value, request.unit)


class SafetyGate:
    def __init__(
        self,
        domain: DomainPack,
        permissions: AgentPermissions,
        operator: OperatorProfile,
    ) -> None:
        self.domain = domain
        self.permissions = permissions
        self.operator = operator
        self.guard = ProcessGuard(domain)
        self.sequence = 0
        self.confirmation_role_valid = {"operator", "supervisor"}

    def submit(
        self,
        request: ControlRequest,
        t_s: float,
        true_values: dict[str, float],
        active_rule_ids: list[str],
        dcs_apply: Callable[[str, float, str, float], None],
    ) -> tuple[GateDecision, list[TraceEvent]]:
        self.sequence += 1
        request_id = f"REQ-{self.sequence:04d}"
        events: list[TraceEvent] = []
        high_risk = False

        # 1. 权限校验
        if request.kind not in self.permissions.allowed_control_kinds:
            return self._block(
                request_id,
                t_s,
                request,
                GateLayer.PERMISSION,
                "permission.control_kind",
                f"Agent 无 {request.kind.value} 权限",
                events,
            )
        if not self.permissions.tag_allowed(request.tag):
            return self._block(
                request_id,
                t_s,
                request,
                GateLayer.PERMISSION,
                "permission.tag",
                f"Agent 无测点 {request.tag} 的控制权限",
                events,
            )
        if request.kind == ControlKind.REQUEST_BYPASS_INTERLOCK:
            return self._block(
                request_id,
                t_s,
                request,
                GateLayer.PERMISSION,
                "sis.bypass",
                "联锁旁路请求一律拒绝；SIS 联锁不可被 Agent 配置或旁路",
                events,
            )

        # 2. 工艺边界
        verdict = self.guard.check_command(request)
        if not verdict.allowed:
            return self._block(
                request_id,
                t_s,
                request,
                GateLayer.PROCESS_GUARD,
                verdict.violated_bound,
                verdict.reason,
                events,
            )

        # 3. 人工确认闸门（高危参数）
        if request.kind == ControlKind.SET_SETPOINT:
            high_risk = self.permissions.is_high_risk(request.tag)
        if high_risk:
            events.append(
                TraceEvent(
                    t_s=t_s,
                    kind=TraceEventKind.CONFIRMATION_REQUIRED,
                    tag=request.tag,
                    value=request.value,
                    unit=request.unit,
                    detail="高危参数写入需要独立操作员确认",
                    source="safety_gate",
                )
            )
            confirmed = (
                self.operator.available
                and self.operator.confirm_high_risk
                and self.operator.role in self.confirmation_role_valid
            )
            if not confirmed:
                return self._block(
                    request_id,
                    t_s,
                    request,
                    GateLayer.CONFIRMATION,
                    "confirmation.missing",
                    "高危参数缺少独立操作员确认；平台默认挂起，不得自动放行",
                    events,
                    requires_confirmation=True,
                )
            events.append(
                TraceEvent(
                    t_s=t_s,
                    kind=TraceEventKind.CONFIRMATION_GRANTED,
                    tag=request.tag,
                    value=request.value,
                    unit=request.unit,
                    detail=f"操作员 {self.operator.operator_id}（{self.operator.role}）确认",
                    source="manual_confirmation",
                )
            )

        # 4. SIS 联锁校验
        interlock_id = self._active_interlock(request.tag, true_values, active_rule_ids)
        if interlock_id is not None:
            events.append(
                TraceEvent(
                    t_s=t_s,
                    kind=TraceEventKind.SIS_BLOCKED,
                    tag=request.tag,
                    value=request.value,
                    unit=request.unit,
                    detail=f"SIS 联锁 {interlock_id} 已动作，指令被物理层阻断",
                    source="sis",
                    rule_id=interlock_id,
                )
            )
            return self._block(
                request_id,
                t_s,
                request,
                GateLayer.SIS,
                interlock_id,
                f"SIS 联锁 {interlock_id} 动作，Agent 指令不得下发",
                events,
                requires_confirmation=high_risk,
            )

        # 5. 放行：先记录 Gate 放行，再产生 DCS 副作用。
        executed = False
        events.append(
            TraceEvent(
                t_s=t_s,
                kind=TraceEventKind.GATE_ALLOWED,
                tag=request.tag,
                value=request.value,
                unit=request.unit,
                detail="全部安全校验通过",
                source="safety_gate",
            )
        )
        if request.kind == ControlKind.SET_SETPOINT:
            assert request.value is not None and request.unit is not None
            dcs_apply(request.tag, request.value, request.unit, t_s)
            executed = True
            events.append(
                TraceEvent(
                    t_s=t_s,
                    kind=TraceEventKind.DCS_WRITE,
                    tag=request.tag,
                    value=request.value,
                    unit=request.unit,
                    detail=verdict.reason,
                    source="dcs",
                )
            )
        return (
            GateDecision(
                request_id=request_id,
                submitted_at_s=t_s,
                request=request,
                allowed=True,
                executed=executed,
                blocking_layer=GateLayer.NONE,
                reason=verdict.reason,
                requires_confirmation=high_risk,
                confirmed_by=self.operator.operator_id if high_risk else None,
            ),
            events,
        )

    def _active_interlock(
        self,
        tag: str,
        true_values: dict[str, float],
        active_rule_ids: list[str],
    ) -> str | None:
        if active_rule_ids:
            return active_rule_ids[0]
        for rule in self.domain.interlocks:
            value = true_values.get(rule.tag)
            if value is None:
                continue
            threshold, _, direction = rule.threshold()
            reached = value >= threshold if direction == "high" else value <= threshold
            if reached:
                return rule.id
        return None

    def _block(
        self,
        request_id: str,
        t_s: float,
        request: ControlRequest,
        layer: GateLayer,
        violated_rule: str | None,
        reason: str,
        events: list[TraceEvent],
        requires_confirmation: bool = False,
    ) -> tuple[GateDecision, list[TraceEvent]]:
        if not any(event.kind == TraceEventKind.GATE_BLOCKED for event in events):
            events.append(
                TraceEvent(
                    t_s=t_s,
                    kind=TraceEventKind.GATE_BLOCKED,
                    tag=request.tag,
                    value=request.value,
                    unit=request.unit,
                    detail=reason,
                    source="safety_gate",
                    rule_id=violated_rule,
                )
            )
        return (
            GateDecision(
                request_id=request_id,
                submitted_at_s=t_s,
                request=request,
                allowed=False,
                executed=False,
                blocking_layer=layer,
                reason=reason,
                violated_rule=violated_rule,
                requires_confirmation=requires_confirmation,
                interlock_rule_ids=(
                    [violated_rule]
                    if layer == GateLayer.SIS and violated_rule
                    else []
                ),
            ),
            events,
        )

    def interlock_rule(self, rule_id: str) -> InterlockRule:
        return self.domain.interlock_by_id(rule_id)


def gate_layer_label(layer: GateLayer) -> str:
    labels: dict[GateLayer, str] = {
        GateLayer.NONE: "放行",
        GateLayer.PERMISSION: "权限拦截",
        GateLayer.PROCESS_GUARD: "工艺边界拦截",
        GateLayer.CONFIRMATION: "人工确认挂起",
        GateLayer.INTERLOCK: "联锁拦截",
        GateLayer.SIS: "SIS 阻断",
    }
    return labels[layer]


def is_dcs_writable(kind: ControlKind) -> bool:
    return kind == ControlKind.SET_SETPOINT

