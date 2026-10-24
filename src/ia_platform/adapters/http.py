"""外部 HTTP Agent 适配器。

平台只发送结构化观测；Agent 只能返回结构化建议/控制请求，不存在任何直写 DCS
的通道。响应必须通过 Pydantic 契约校验，否则视为 Agent 不可用。
"""

from __future__ import annotations

import os
import time

import httpx

from ia_platform.adapters.base import AgentInvocation, AgentInvocationError
from ia_platform.core.models import AgentDefinition, AgentObservation, AgentResponse


class HttpJsonAgentAdapter:
    def __init__(self, definition: AgentDefinition) -> None:
        self.definition = definition
        if not definition.endpoint:
            raise AgentInvocationError(f"Agent {definition.id} 缺少 endpoint")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.definition.token_env:
            token = os.environ.get(self.definition.token_env)
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def invoke(self, observation: AgentObservation, seed: int) -> AgentInvocation:
        endpoint = self.definition.endpoint
        if endpoint is None:
            raise AgentInvocationError(f"Agent {self.definition.id} 缺少 endpoint")
        request_payload: dict[str, object] = {
            "protocol": "iatp.agent.v1",
            "observation": observation.model_dump(mode="json"),
            "determinism": {
                "temperature": self.definition.temperature,
                "seed": seed,
            },
        }
        started = time.perf_counter()
        last_error: Exception | None = None
        payload: object = None
        for _ in range(self.definition.max_retries + 1):
            try:
                with httpx.Client(timeout=self.definition.timeout_s) as client:
                    response = client.post(
                        endpoint,
                        json=request_payload,
                        headers=self._headers(),
                    )
                response.raise_for_status()
                payload = response.json()
                break
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
        if payload is None:
            raise AgentInvocationError(
                f"Agent {self.definition.id} 调用失败：{last_error}"
            ) from last_error
        latency_ms = (time.perf_counter() - started) * 1000.0
        if not isinstance(payload, dict):
            raise AgentInvocationError("Agent 响应必须是 JSON 对象")
        try:
            parsed = AgentResponse.model_validate(payload)
        except Exception as exc:  # pydantic ValidationError 不向上层泄露内部细节
            raise AgentInvocationError(f"Agent 响应不符合契约：{exc}") from exc
        return AgentInvocation(
            response=parsed,
            request_payload=request_payload,
            response_payload=payload,
            latency_ms=latency_ms,
        )
