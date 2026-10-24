"""单位、边界与哨兵值：手算期望值，禁止裸数字比较。"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from ia_platform.core.models import LimitBand, PhysicalValue
from ia_platform.core.units import canonical_unit, ensure_unit, is_sentinel_value


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("°C", "degC"),
        ("degc", "degC"),
        ("C", "degC"),
        ("mpa", "MPa"),
        ("KPA", "kPa"),
        ("tph", "t/h"),
        ("percent", "%"),
        ("seconds", "s"),
        ("degC/s", "degC/s"),
    ],
)
def test_canonical_unit_aliases(raw: str, expected: str) -> None:
    assert canonical_unit(raw) == expected


def test_unknown_unit_is_rejected() -> None:
    with pytest.raises(ValueError, match="未知单位"):
        canonical_unit("bar")


def test_ensure_unit_rejects_mismatch() -> None:
    ensure_unit("degC", "°C", "TI-203")
    with pytest.raises(ValueError, match="单位不一致"):
        ensure_unit("MPa", "degC", "PI-203")


def test_physical_value_normalizes_unit_and_forbids_extra_fields() -> None:
    value = PhysicalValue(value=240.0, unit="°C")
    assert value.unit == "degC"
    with pytest.raises(ValidationError):
        PhysicalValue.model_validate(
            {"value": 240.0, "unit": "degC", "unknown": True}
        )


def test_limit_band_contains_and_width() -> None:
    band = LimitBand(low=220.0, high=260.0, unit="degC")
    assert band.contains(220.0, "°C") is True
    assert band.contains(260.0, "degC") is True
    assert band.contains(219.999, "degC") is False
    assert band.width == pytest.approx(40.0)
    with pytest.raises(ValueError, match="单位不一致"):
        band.contains(240.0, "MPa")


def test_limit_band_rejects_reversed_bounds() -> None:
    with pytest.raises(ValidationError, match="low 必须小于 high"):
        LimitBand(low=10.0, high=10.0, unit="MPa")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (math.nan, True),
        (-9999.0, True),
        (9999.0, True),
        (-32768.0, True),
        (32767.0, True),
        (-20.0001, True),
        (500.0001, True),
        (-20.0, False),
        (500.0, False),
        (240.0, False),
    ],
)
def test_sentinel_and_out_of_range_detection(value: float, expected: bool) -> None:
    assert is_sentinel_value(value, -20.0, 500.0) is expected
