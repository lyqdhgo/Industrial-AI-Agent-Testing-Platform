"""确定性用例执行器。

执行顺序：过程步进 → 独立 SIS 评估/动作 → Agent 观测与推理 → SafetyGate → DCS。
Agent 适配器拿不到仿真器或 DCS 对象；它唯一的输出是受限的 AgentResponse。
"""

from __future__ import annotations

import math

from ia_platform.adapters import AgentInvocationError, build_adapter
from ia_platform.core.hashing import content_hash
from ia_platform.core.models import (
    AgentDefinition,
    AgentResponse,
    ControlKind,
    ControlRequest,
    DomainPack,
    InterlockEvent,
    RecommendationStatus,
    TestCase,
    TraceEvent,
    TraceEventKind,
)
from ia_platform.evaluation.evidence import (
    AgentCallEvidence,
    CaseRunEvidence,
    GateEvidence,
)
from ia_platform.simulation.interlocks import InterlockEngine
from ia_platform.simulation.process import ProcessSimulator
from ia_platform.simulation.rng import derive_seed
from ia_platform.simulation.safety import SafetyGate


class CaseExecutionError(RuntimeError):
    """用例执行失败；不得用 0 结果冒充 Agent 未告警。"""


def _request_signature(
    kind: ControlKind, tag: str, value: float | None, unit: str | None
) -> tuple[str, str, float, str]:
    return (
        kind.value,
        tag,
        round(value, 6) if value is not None else 0.0,
        unit or "",
    )


def _response_fingerprint(response: AgentResponse) -> str:
    return content_hash(response.normalized_fingerprint_payload())


def _requests_for_response(response: AgentResponse) -> list[ControlRequest]:
    requests = [
        ControlRequest(
            kind=ControlKind.SET_SETPOINT,
            tag=suggestion.tag,
            value=suggestion.value,
            unit=suggestion.unit,
            reason="Agent 设定值建议",
        )
        for suggestion in response.setpoints
    ]
    requests.extend(response.control_requests)
    return requests


def _decision_times(case: TestCase) -> list[float]:
    interval = case.decision_interval_s
    count = math.floor(case.duration_s / interval + 1e-9)
    return [round(interval * index, 6) for index in range(1, count + 1)]


def execute_case(
    case: TestCase,
    agent: AgentDefinition,
    domain: DomainPack,
    seed: int,
) -> CaseRunEvidence:
    try:
        adapter = build_adapter(agent)
    except Exception as exc:
        raise CaseExecutionError(f"无法构建 Agent {agent.id} 适配器：{exc}") from exc

    simulator = ProcessSimulator(case, domain, seed)
    interlocks = InterlockEngine(domain)
    gate = SafetyGate(domain, agent.permissions, case.operator)

    calls: list[AgentCallEvidence] = []
    gates: list[GateEvidence] = []
    traces: list[TraceEvent] = []
    interlock_events: list[InterlockEvent] = []
    decisions = _decision_times(case)
    decision_index = 0
    step_s = domain.timebase.simulation_step_s
    total_steps = math.floor(case.duration_s / step_s + 1e-9)
    last_executed: dict[str, tuple[str, str, float, str]] = {}

    for step in range(1, total_steps + 1):
        t_s = round(step * step_s, 9)
        simulator.step(t_s, step_s)

        for event in interlocks.check(t_s, simulator.true_values):
            interlock_events.append(event)
            rule = domain.interlock_by_id(event.rule_id)
            traces.append(
                TraceEvent(
                    t_s=t_s,
                    kind=TraceEventKind.SIS_TRIGGERED,
                    tag=rule.tag,
                    value=event.measured_value,
                    unit=event.unit,
                    detail=f"{event.rule_id} 按独立联锁表动作：{event.action.value}",
                    source="sis",
                    rule_id=event.rule_id,
                )
            )
            simulator.apply_sis_action(event.action, t_s)

        if decision_index >= len(decisions):
            continue
        if t_s + 1e-9 < decisions[decision_index]:
            continue

        decision_t = decisions[decision_index]
        decision_index += 1
        observation = simulator.observation(decision_t, case.history_window_s)
        invocation_seed = derive_seed(seed, case.id, "agent-call", f"{decision_t:.6f}")
        try:
            invocation = adapter.invoke(observation, invocation_seed)
        except AgentInvocationError as exc:
            raise CaseExecutionError(
                f"{case.id} 在 {decision_t:.1f}s 调用 Agent 失败：{exc}"
            ) from exc
        except Exception as exc:
            raise CaseExecutionError(
                f"{case.id} 在 {decision_t:.1f}s 调用 Agent 异常：{exc}"
            ) from exc

        call = AgentCallEvidence(
            index=len(calls) + 1,
            observed_at_s=decision_t,
            observation=observation,
            response=invocation.response,
            latency_ms=invocation.latency_ms,
            request_payload=invocation.request_payload,
            response_payload=invocation.response_payload,
            fingerprint=_response_fingerprint(invocation.response),
        )
        calls.append(call)
        traces.append(
            TraceEvent(
                t_s=decision_t,
                kind=TraceEventKind.AGENT_SUGGESTION,
                tag=invocation.response.target_tag,
                detail=invocation.response.rationale_text,
                source="agent",
            )
        )
        if invocation.response.status == RecommendationStatus.DEGRADED:
            traces.append(
                TraceEvent(
                    t_s=decision_t,
                    kind=TraceEventKind.DEGRADED_MODE,
                    tag=invocation.response.target_tag,
                    detail=invocation.response.degraded_mode or "",
                    source="agent",
                )
            )

        for request in _requests_for_response(invocation.response):
            signature = _request_signature(
                request.kind, request.tag, request.value, request.unit
            )
            if (
                request.kind == ControlKind.SET_SETPOINT
                and last_executed.get(request.tag) == signature
            ):
                # 已成功写入的同一设定值视为幂等重复建议，不再制造 DCS 写副作用。
                continue
            decision, events = gate.submit(
                request,
                decision_t,
                simulator.true_values,
                interlocks.active_rule_ids(),
                simulator.apply_dcs_setpoint,
            )
            gates.append(GateEvidence(decision=decision, trace_events=events))
            traces.extend(events)
            if decision.executed and request.kind == ControlKind.SET_SETPOINT:
                last_executed[request.tag] = signature

    if not interlocks.hash_unchanged():
        raise CaseExecutionError("联锁表哈希在运行期间发生变化，结果不可信")

    return CaseRunEvidence(
        case=case,
        agent=agent,
        domain=domain,
        seed=seed,
        records=list(simulator.records),
        calls=calls,
        gates=gates,
        traces=traces,
        interlock_events=interlock_events,
        interlock_evaluations=interlocks.evaluations(),
        interlock_hash_unchanged=interlocks.hash_unchanged(),
        stimulus_events=list(simulator.stimulus_events),
        injection_artifacts=simulator.faults.artifacts(),
        final_setpoints=[item.model_dump(mode="json") for item in simulator.dcs_setpoints()],
    )
