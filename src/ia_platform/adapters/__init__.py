"""被测 Agent 适配层：仅做协议翻译，不包含任何评测逻辑。"""

from __future__ import annotations

from ia_platform.adapters.base import AgentAdapter, AgentInvocation, AgentInvocationError
from ia_platform.adapters.http import HttpJsonAgentAdapter
from ia_platform.adapters.mock import MockAgentAdapter
from ia_platform.core.models import AdapterKind, AgentDefinition


def build_adapter(definition: AgentDefinition) -> AgentAdapter:
    if definition.adapter == AdapterKind.MOCK:
        return MockAgentAdapter(definition)
    if definition.adapter == AdapterKind.HTTP_JSON:
        return HttpJsonAgentAdapter(definition)
    raise AgentInvocationError(f"未知适配器类型 {definition.adapter}")


__all__ = [
    "AgentAdapter",
    "AgentInvocation",
    "AgentInvocationError",
    "HttpJsonAgentAdapter",
    "MockAgentAdapter",
    "build_adapter",
]
