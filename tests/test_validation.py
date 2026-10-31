import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator"))

from validation import Reading, TagSpec, validate  # noqa: E402

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
WELLS = {"W-01"}
TAGS = {"WHP": TagSpec(0, 400)}


def check(**overrides):
    fields = {"time": NOW, "well_id": "W-01", "tag": "WHP", "value": 95.0} | overrides
    return validate(Reading(**fields), WELLS, TAGS, now=NOW)


def test_valid_reading_passes():
    assert check() is None


def test_unknown_well_is_rejected():
    assert "unknown well" in check(well_id="W-99")


def test_unknown_tag_is_rejected():
    assert "unknown tag" in check(tag="WHP_X")


def test_nan_is_rejected():
    assert "not a number" in check(value=float("nan"))


def test_value_above_physical_range_is_rejected():
    assert "outside physical range" in check(value=4750.0)


def test_negative_pressure_is_rejected():
    assert "outside physical range" in check(value=-1.0)


def test_boundaries_are_valid():
    assert check(value=0.0) is None
    assert check(value=400.0) is None


def test_future_timestamp_is_rejected():
    assert "future" in check(time=NOW + timedelta(hours=1))


def test_small_clock_skew_is_tolerated():
    assert check(time=NOW + timedelta(minutes=2)) is None


def test_naive_timestamp_is_rejected():
    assert "timezone" in check(time=datetime(2026, 11, 1, 12, 0))
