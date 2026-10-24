"""六类故障注入的物理/测量通道隔离与确定性。"""

from __future__ import annotations

import pytest

from ia_platform.core.catalog import PlatformCatalog
from ia_platform.core.models import (
    DomainPack,
    SampleQuality,
)
from ia_platform.core.models import (
    TestCase as ProcessCase,
)
from ia_platform.orchestration.runner import execute_case


def _fault_window(case: ProcessCase) -> tuple[float, float]:
    fault = case.faults[0]
    return fault.start_s, fault.end_s


def test_super_temperature_changes_true_process_not_measurement_only(
    domain: DomainPack, catalog: PlatformCatalog
) -> None:
    case = catalog.get_case("CASE-FAULT-001")
    agent = catalog.get_agent("mock-reference")
    evidence = execute_case(case, agent, domain, case.seed)
    start, end = _fault_window(case)
    records = evidence.records_for("TI-203", start, end)
    assert records
    assert records[-1].true_value > records[0].true_value + 20.0
    assert all(record.measured_value is not None for record in records)


def test_over_pressure_changes_true_pressure(
    domain: DomainPack, catalog: PlatformCatalog
) -> None:
    case = catalog.get_case("CASE-FAULT-002")
    agent = catalog.get_agent("mock-reference")
    evidence = execute_case(case, agent, domain, case.seed)
    start, end = _fault_window(case)
    records = evidence.records_for("PI-203", start, end)
    assert records[-1].true_value > records[0].true_value + 0.3


def test_sensor_drift_is_measurement_only(
    domain: DomainPack, catalog: PlatformCatalog
) -> None:
    case = catalog.get_case("CASE-FAULT-003")
    agent = catalog.get_agent("mock-reference")
    evidence = execute_case(case, agent, domain, case.seed)
    start, end = _fault_window(case)
    records = evidence.records_for("TI-203", start, end)
    true_span = max(item.true_value for item in records) - min(
        item.true_value for item in records
    )
    assert true_span < 8.0
    first = records[1]
    late = records[-10]
    assert first.measured_value is not None
    assert late.measured_value is not None
    drift = (late.measured_value - late.true_value) - (
        first.measured_value - first.true_value
    )
    assert drift >= 8.0
    assert all(item.quality == SampleQuality.GOOD for item in records)


def test_valve_sticking_freezes_valve_while_command_moves(
    domain: DomainPack, catalog: PlatformCatalog
) -> None:
    case = catalog.get_case("CASE-FAULT-004")
    agent = catalog.get_agent("mock-reference")
    evidence = execute_case(case, agent, domain, case.seed)
    start, end = _fault_window(case)
    valve = evidence.records_for("LV-201", start + 5, end)
    assert valve
    valve_span = max(item.true_value for item in valve) - min(
        item.true_value for item in valve
    )
    assert valve_span < 1.0
    artifacts = [
        item
        for item in evidence.injection_artifacts
        if item.get("kind") == "valve_sticking"
    ]
    assert artifacts and artifacts[0].get("locked_valve_pct") is not None
    flow = evidence.records_for("FI-201", start + 5, end)
    residuals = [
        abs((item.command_value or 0.0) - (item.measured_value or 0.0))
        for item in flow
    ]
    assert max(residuals) > 8.0


def test_disconnect_freezes_its_own_tag_not_last_emitted_tag(
    domain: DomainPack, catalog: PlatformCatalog
) -> None:
    case = catalog.get_case("CASE-FAULT-005")
    agent = catalog.get_agent("mock-reference")
    evidence = execute_case(case, agent, domain, case.seed)
    start, end = _fault_window(case)
    affected = evidence.records_for("TI-203", start, end)
    assert affected
    assert all(item.quality == SampleQuality.BAD for item in affected)
    frozen = [item.measured_value for item in affected if item.measured_value is not None]
    assert len(frozen) == len(affected)
    # 断线时冻结的必须是 TI-203 自身末值，而不是最后发射的 LV-201 阀位。
    assert all(200.0 < value < 300.0 for value in frozen)
    assert max(frozen) - min(frozen) < 1e-6
    valve = evidence.records_for("LV-201", start, end)
    assert valve and all(item.quality == SampleQuality.GOOD for item in valve)
    recovery = evidence.records_for("TI-203", end, case.duration_s)
    assert recovery and any(item.quality == SampleQuality.GOOD for item in recovery)


def test_network_jitter_delivers_late_or_drops_without_moving_process(
    domain: DomainPack, catalog: PlatformCatalog
) -> None:
    case = catalog.get_case("CASE-FAULT-006")
    agent = catalog.get_agent("mock-reference")
    evidence = execute_case(case, agent, domain, case.seed)
    start, end = _fault_window(case)
    records = evidence.records_for("TI-203", start, end)
    assert any(
        (not item.delivered) or item.received_s > item.t_s + 1e-9 for item in records
    )
    true_values = [item.true_value for item in records]
    assert max(true_values) - min(true_values) < 10.0


@pytest.mark.parametrize(
    ("case_id", "agent_id", "expected_kind"),
    [
        ("CASE-FAULT-001", "mock-reference", "super_temperature"),
        ("CASE-FAULT-002", "mock-reference", "over_pressure"),
        ("CASE-FAULT-003", "mock-reference", "sensor_drift"),
        ("CASE-FAULT-004", "mock-reference", "valve_sticking"),
        ("CASE-FAULT-005", "mock-reference", "sensor_disconnect"),
        ("CASE-FAULT-006", "mock-reference", "network_jitter"),
    ],
)
def test_injection_artifact_is_recorded_per_fault(
    domain: DomainPack,
    catalog: PlatformCatalog,
    case_id: str,
    agent_id: str,
    expected_kind: str,
) -> None:
    case = catalog.get_case(case_id)
    agent = catalog.get_agent(agent_id)
    evidence = execute_case(case, agent, domain, case.seed)
    kinds = [item.get("kind") for item in evidence.injection_artifacts]
    assert expected_kind in kinds
    assert evidence.interlock_hash_unchanged is True
