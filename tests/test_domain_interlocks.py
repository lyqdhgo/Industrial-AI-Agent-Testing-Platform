"""领域包完整性与独立 SIS 联锁引擎。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ia_platform.core.catalog import PlatformCatalog
from ia_platform.core.models import (
    DomainPack,
    InterlockRule,
)
from ia_platform.simulation.interlocks import InterlockEngine


def test_domain_pack_is_complete_and_deterministic(domain: DomainPack) -> None:
    assert sorted(domain.sensors) == ["FI-201", "LV-201", "PI-203", "TI-203"]
    assert {rule.id for rule in domain.interlocks} == {
        "IL-PI203-HIHI",
        "IL-TI203-HIHI",
    }
    assert all(rule.bypassable is False for rule in domain.interlocks)
    assert domain.hashes.domain_hash
    assert domain.hashes.interlock_hash


def test_every_case_declares_source_and_provenance(catalog: PlatformCatalog) -> None:
    cases = catalog.cases
    assert cases
    for case in cases.values():
        assert case.provenance.strip()
        assert case.source.value in {"real_history", "simulation", "mechanistic"}


def test_interlock_rule_cannot_be_bypassable() -> None:
    with pytest.raises(ValidationError, match="不允许 bypassable=true"):
        InterlockRule.model_validate(
            {
                "id": "IL-BAD",
                "tag": "TI-203",
                "name": "非法旁路",
                "trip_limit": {"high": 420.0, "unit": "degC"},
                "action": "trip_reactor_feed",
                "layer": "sis",
                "bypassable": True,
            }
        )


def test_high_high_interlock_latches_first_trigger(domain: DomainPack) -> None:
    engine = InterlockEngine(domain)
    assert engine.check(10.0, {"TI-203": 419.0, "PI-203": 1.6}) == []

    events = engine.check(20.0, {"TI-203": 420.0, "PI-203": 1.6})
    assert len(events) == 1
    assert events[0].rule_id == "IL-TI203-HIHI"
    assert events[0].t_s == 20.0
    assert events[0].measured_value == 420.0
    assert events[0].threshold_value == 420.0

    # 联锁已经动作后必须保持；真实温度回落不改变“曾触发”的事实。
    assert engine.check(30.0, {"TI-203": 300.0, "PI-203": 1.6}) == []
    evaluation = next(
        item for item in engine.evaluations() if item.rule_id == "IL-TI203-HIHI"
    )
    assert evaluation.should_trigger is True
    assert evaluation.triggered is True
    assert evaluation.trigger_t_s == 20.0


def test_pressure_interlock_uses_true_value_not_agent_claim(domain: DomainPack) -> None:
    engine = InterlockEngine(domain)
    events = engine.check(40.0, {"TI-203": 240.0, "PI-203": 3.2})
    assert [event.rule_id for event in events] == ["IL-PI203-HIHI"]
    assert events[0].measured_value == 3.2


def test_interlock_table_hash_detects_tampering(domain: DomainPack) -> None:
    engine = InterlockEngine(domain)
    assert engine.hash_unchanged() is True
    engine.rules.clear()
    assert engine.hash_unchanged() is False


def test_rules_are_not_bypassable_and_engine_has_no_mutation_api(
    domain: DomainPack,
) -> None:
    engine = InterlockEngine(domain)
    assert engine.is_bypassable("IL-TI203-HIHI") is False
    assert not hasattr(engine, "bypass")
    assert not hasattr(engine, "disable")
    assert not hasattr(engine, "remove_rule")
