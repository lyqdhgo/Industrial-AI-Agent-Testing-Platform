"""被测 Agent 适配器协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ia_platform.core.models import AgentDefinition, AgentObservation, AgentResponse


class AgentInvocationError(RuntimeError):
    """Agent 不可用、响应不符合契约或超时。"""


@dataclass(frozen=True)
class AgentInvocation:
    response: AgentResponse
    request_payload: dict[str, object]
    response_payload: dict[str, object]
    latency_ms: float


@runtime_checkable
class AgentAdapter(Protocol):
    definition: AgentDefinition

    def invoke(self, observation: AgentObservation, seed: int) -> AgentInvocation: ...
