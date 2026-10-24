"""SIS 联锁引擎。

联锁表是平台自有资产，Agent 无权读取后修改、无权旁路。引擎只读取独立真实状态，
不读取被漂移的显示值。每次运行前后核对表哈希。
"""

from __future__ import annotations

from ia_platform.core.hashing import content_hash
from ia_platform.core.models import (
    DomainPack,
    InterlockEvaluation,
    InterlockEvent,
    InterlockRule,
)


class InterlockEngine:
    def __init__(self, domain: DomainPack) -> None:
        self.domain = domain
        self.rules: list[InterlockRule] = list(domain.interlocks)
        self.triggered: dict[str, InterlockEvent] = {}
        self.should_trigger: dict[str, bool] = {rule.id: False for rule in self.rules}
        self.start_hash = self.table_hash()
        if self.start_hash != domain.hashes.interlock_hash:
            raise RuntimeError("联锁表启动哈希与 domain pack 不一致")

    def table_hash(self) -> str:
        return content_hash([rule.model_dump(mode="json") for rule in self.rules])

    def hash_unchanged(self) -> bool:
        return self.table_hash() == self.start_hash

    def check(self, t_s: float, true_values: dict[str, float]) -> list[InterlockEvent]:
        events: list[InterlockEvent] = []
        for rule in self.rules:
            measured = true_values.get(rule.tag)
            if measured is None:
                continue
            threshold, unit, direction = rule.threshold()
            reached = measured >= threshold if direction == "high" else measured <= threshold
            if reached:
                self.should_trigger[rule.id] = True
            if reached and rule.id not in self.triggered:
                event = InterlockEvent(
                    rule_id=rule.id,
                    action=rule.action,
                    t_s=t_s,
                    measured_value=measured,
                    unit=unit,
                    threshold_value=threshold,
                )
                self.triggered[rule.id] = event
                events.append(event)
        return events

    def active_rule_ids(self) -> list[str]:
        return sorted(self.triggered)

    def evaluations(self) -> list[InterlockEvaluation]:
        result: list[InterlockEvaluation] = []
        for rule in self.rules:
            event = self.triggered.get(rule.id)
            result.append(
                InterlockEvaluation(
                    rule_id=rule.id,
                    action=rule.action,
                    should_trigger=self.should_trigger[rule.id],
                    triggered=event is not None,
                    trigger_t_s=event.t_s if event else None,
                )
            )
        return result

    def is_bypassable(self, rule_id: str) -> bool:
        rule = self.domain.interlock_by_id(rule_id)
        return rule.bypassable
