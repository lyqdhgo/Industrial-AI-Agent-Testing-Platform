"""评测输入证据。

这些 DTO 是仿真/适配层与纯评测层之间唯一的耦合面。它们不暴露仿真器内部状态，
只包含 Agent 实际看到/返回的内容、门禁动作、真实时序与注入记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ia_platform.core.models import (
    AgentDefinition,
    AgentObservation,
    AgentResponse,
    DomainPack,
    GateDecision,
    InterlockEvaluation,
    InterlockEvent,
    TelemetryRecord,
    TestCase,
    TraceEvent,
)


@dataclass(frozen=True)
class AgentCallEvidence:
    index: int
    observed_at_s: float
    observation: AgentObservation
    response: AgentResponse
    latency_ms: float
    request_payload: dict[str, object]
    response_payload: dict[str, object]
    fingerprint: str


@dataclass(frozen=True)
class GateEvidence:
    decision: GateDecision
    trace_events: list[TraceEvent]


@dataclass
class CaseRunEvidence:
    case: TestCase
    agent: AgentDefinition
    domain: DomainPack
    seed: int
    records: list[TelemetryRecord]
    calls: list[AgentCallEvidence]
    gates: list[GateEvidence]
    traces: list[TraceEvent]
    interlock_events: list[InterlockEvent]
    interlock_evaluations: list[InterlockEvaluation]
    interlock_hash_unchanged: bool
    stimulus_events: list[dict[str, object]]
    injection_artifacts: list[dict[str, object]]
    final_setpoints: list[dict[str, object]] = field(default_factory=list)

    def calls_between(self, start_s: float, end_s: float) -> list[AgentCallEvidence]:
        return [
            call
            for call in self.calls
            if start_s - 1e-9 <= call.observed_at_s <= end_s + 1e-9
        ]

    def records_for(
        self,
        tag: str,
        start_s: float | None = None,
        end_s: float | None = None,
    ) -> list[TelemetryRecord]:
        result = []
        for record in self.records:
            if record.tag != tag:
                continue
            if start_s is not None and record.t_s < start_s - 1e-9:
                continue
            if end_s is not None and record.t_s >= end_s - 1e-9:
                continue
            result.append(record)
        return result
