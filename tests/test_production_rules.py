import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "loader"))

from production_rules import check_row  # noqa: E402

TODAY = date(2026, 11, 1)


def row(**overrides):
    base = {"wellbore": "DEMO-A1", "prod_date": date(2015, 6, 1), "on_stream_hrs": 24.0,
            "oil_sm3": 1500.0, "gas_sm3": 220000.0, "water_sm3": 300.0, "water_inj_sm3": 0.0,
            "avg_whp": 45.0, "avg_choke_pct": 40.0}
    return base | overrides


def test_clean_row():
    assert check_row(row(), TODAY) == (None, None)


def test_missing_wellbore_rejected():
    reason, _ = check_row(row(wellbore=""), TODAY)
    assert reason == "missing wellbore name"


def test_unreadable_date_rejected():
    reason, _ = check_row(row(prod_date=None), TODAY)
    assert "date" in reason


def test_future_date_rejected():
    reason, _ = check_row(row(prod_date=date(2030, 1, 1)), TODAY)
    assert "out of range" in reason


def test_negative_volume_rejected():
    reason, _ = check_row(row(water_sm3=-5.0), TODAY)
    assert "negative volume in water_sm3" in reason


def test_choke_above_100_rejected():
    reason, _ = check_row(row(avg_choke_pct=150.0), TODAY)
    assert "avg_choke_pct" in reason


def test_25_hours_allowed_for_daylight_saving_day():
    assert check_row(row(on_stream_hrs=25.0), TODAY) == (None, None)


def test_26_hours_rejected():
    reason, _ = check_row(row(on_stream_hrs=26.0), TODAY)
    assert "on_stream_hrs" in reason


def test_missing_optional_values_are_fine():
    assert check_row(row(avg_whp=float("nan"), avg_choke_pct=None), TODAY) == (None, None)


def test_volumes_with_zero_hours_flagged_not_rejected():
    reason, flag = check_row(row(on_stream_hrs=0.0), TODAY)
    assert reason is None
    assert flag == "volumes reported with 0 hours on stream"


def test_shut_in_day_with_no_volumes_is_clean():
    shut_in = row(on_stream_hrs=0.0, oil_sm3=0.0, gas_sm3=0.0, water_sm3=0.0)
    assert check_row(shut_in, TODAY) == (None, None)
