"""Data validation rules for incoming telemetry.

Pure functions with no database access, so they are easy to unit test.
A reading that fails any rule is rejected with a reason; it is never silently dropped.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

MAX_CLOCK_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class Reading:
    time: datetime
    well_id: str
    tag: str
    value: float


@dataclass(frozen=True)
class TagSpec:
    min_valid: float
    max_valid: float


def validate(reading: Reading, wells: set[str], tags: dict[str, TagSpec],
             now: datetime | None = None) -> str | None:
    """Return None if the reading is valid, otherwise a short rejection reason."""
    now = now or datetime.now(timezone.utc)

    if reading.well_id not in wells:
        return f"unknown well '{reading.well_id}'"
    if reading.tag not in tags:
        return f"unknown tag '{reading.tag}'"
    if reading.value is None or not math.isfinite(reading.value):
        return "value is missing or not a number"
    if reading.time.tzinfo is None:
        return "timestamp has no timezone"
    if reading.time > now + MAX_CLOCK_SKEW:
        return "timestamp is in the future"

    spec = tags[reading.tag]
    if not spec.min_valid <= reading.value <= spec.max_valid:
        return (f"value {reading.value:g} outside physical range "
                f"[{spec.min_valid:g}, {spec.max_valid:g}]")
    return None
