"""Validation rules for daily production rows (Volve 'Daily Production Data' format).

Pure functions, no database: easy to unit test.

Each row ends up in one of three states:
  - rejected : impossible or unusable (bad date, negative volume...) -> raw.production_rejected
  - flagged  : stored, but suspicious (oil produced with 0 hours on stream...) -> quality_flag
  - clean    : stored as is
"""
from __future__ import annotations

import math
from datetime import date

# Source column -> our column. Matching ignores case and surrounding spaces.
COLUMN_MAP = {
    "DATEPRD": "prod_date",
    "NPD_WELL_BORE_NAME": "wellbore",
    "ON_STREAM_HRS": "on_stream_hrs",
    "AVG_DOWNHOLE_PRESSURE": "avg_downhole_press",
    "AVG_DOWNHOLE_TEMPERATURE": "avg_downhole_temp",
    "AVG_WHP_P": "avg_whp",
    "AVG_WHT_P": "avg_wht",
    "AVG_CHOKE_SIZE_P": "avg_choke_pct",
    "BORE_OIL_VOL": "oil_sm3",
    "BORE_GAS_VOL": "gas_sm3",
    "BORE_WAT_VOL": "water_sm3",
    "BORE_WI_VOL": "water_inj_sm3",
    "FLOW_KIND": "flow_kind",
    "WELL_TYPE": "well_type",
}
REQUIRED = {"prod_date", "wellbore"}

VOLUMES = ("oil_sm3", "gas_sm3", "water_sm3", "water_inj_sm3")
# Physical limits: outside these, the value is bad data, not an operating condition
LIMITS = {
    "on_stream_hrs": (0, 25),          # 25, not 24: daylight-saving days have 25 hours
    "avg_downhole_press": (0, 1000),
    "avg_downhole_temp": (-10, 200),
    "avg_whp": (0, 1000),
    "avg_wht": (-10, 200),
    "avg_choke_pct": (0, 100),
}
EARLIEST_DATE = date(1960, 1, 1)


def is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def check_row(row: dict, today: date) -> tuple[str | None, str | None]:
    """Return (reject_reason, quality_flag). At most one of them is set."""
    if is_missing(row.get("wellbore")) or not str(row["wellbore"]).strip():
        return "missing wellbore name", None
    d = row.get("prod_date")
    if not isinstance(d, date) or d != d:      # d != d catches pandas' NaT "not-a-time"
        return "missing or unreadable date", None
    if not EARLIEST_DATE <= d <= today:
        return f"date {d.isoformat()} out of range", None

    for col in VOLUMES:
        v = row.get(col)
        if not is_missing(v) and v < 0:
            return f"negative volume in {col} ({v:g})", None

    for col, (lo, hi) in LIMITS.items():
        v = row.get(col)
        if not is_missing(v) and not lo <= v <= hi:
            return f"{col} {v:g} outside physical range [{lo}, {hi}]", None

    # Suspicious but possible: keep the row, flag it for a human to look at
    hours = row.get("on_stream_hrs")
    produced = any(not is_missing(row.get(c)) and row.get(c) > 0 for c in VOLUMES)
    if produced and not is_missing(hours) and hours == 0:
        return None, "volumes reported with 0 hours on stream"
    return None, None
