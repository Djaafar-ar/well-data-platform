"""SCADA telemetry simulator.

Every INTERVAL_SECONDS it produces one reading per well and tag, the way an RTU
polled by SCADA would. It deliberately injects realistic data problems
(sensor spikes, NaN values, unknown tags) so the validation layer has work to do.

Valid readings go to core.readings; invalid ones go to raw.rejected with a reason.

Run:  python simulate.py              (live, forever)
      python simulate.py --backfill 6 (first write 6 hours of history, then go live)
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import random
import time
from datetime import datetime, timedelta, timezone

import psycopg

from validation import Reading, TagSpec, validate

INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", "10"))
FAULT_RATE = float(os.getenv("FAULT_RATE", "0.02"))   # 2% of readings are corrupted on purpose

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("simulator")

# Normal operating point of each well (illustrative values)
BASELINE = {
    "W-01": {"WHP": 95, "WHT": 62, "FLP": 28, "CHOKE": 45, "GL_RATE": 60000},
    "W-02": {"WHP": 130, "WHT": 70, "FLP": 35, "CHOKE": 60, "GL_RATE": 85000},
    "W-03": {"WHP": 160, "WHT": 78, "FLP": 40, "CHOKE": 50},
}
NOISE = {"WHP": 1.5, "WHT": 0.4, "FLP": 0.8, "CHOKE": 0.0, "GL_RATE": 800}

# Operational events that push a tag outside its operating limits (real alarms, not bad data)
EVENTS = [
    {"name": "pressure build-up", "tag": "WHP", "target": 195.0},
    {"name": "gas-lift supply loss", "tag": "GL_RATE", "target": 3000.0},
]
EVENT_CHANCE = float(os.getenv("EVENT_CHANCE", "0.0015"))   # per well, per cycle
EVENT_CYCLES = 30                                            # an event lasts 30 polling cycles


def connect() -> psycopg.Connection:
    dsn = os.getenv("DATABASE_URL")
    for attempt in range(30):                       # wait for the database container to be ready
        try:
            return psycopg.connect(dsn, autocommit=True)
        except psycopg.OperationalError:
            log.info("database not ready, retrying (%d/30)", attempt + 1)
            time.sleep(2)
    raise SystemExit("could not connect to the database")


def load_catalog(conn) -> tuple[set[str], dict[str, TagSpec]]:
    wells = {row[0] for row in conn.execute("SELECT well_id FROM core.wells")}
    tags = {tag: TagSpec(lo, hi) for tag, lo, hi in
            conn.execute("SELECT tag, min_valid, max_valid FROM core.tags")}
    return wells, tags


def generate(ts: datetime, state: dict) -> list[Reading]:
    """One polling cycle: a reading for every well and tag, with slow drift, a daily cycle and noise."""
    hour = ts.hour + ts.minute / 60
    readings = []
    events = state.setdefault("events", {})
    for well, tags in BASELINE.items():
        event = events.get(well)
        if event is None and random.random() < EVENT_CHANCE:
            options = [e for e in EVENTS if e["tag"] in tags]
            event = events[well] = {**random.choice(options), "left": EVENT_CYCLES}
            log.info("%s: %s starts at %s", well, event["name"], ts.isoformat(timespec="seconds"))
        for tag, base in tags.items():
            if event and event["tag"] == tag:
                readings.append(Reading(ts, well, tag, round(random.gauss(event["target"], NOISE[tag]), 2)))
                continue
            key = (well, tag)
            drift = state.get(key, 0.0) + random.gauss(0, NOISE[tag] * 0.05)
            state[key] = max(-0.15 * base, min(0.15 * base, drift))     # drift stays within ±15%
            daily = 0.03 * base * math.sin(2 * math.pi * hour / 24)     # day/night temperature effect
            value = base + state[key] + daily + random.gauss(0, NOISE[tag])
            readings.append(Reading(ts, well, tag, round(value, 2)))
        if event:
            event["left"] -= 1
            if event["left"] == 0:
                del events[well]
    return [corrupt(r) if random.random() < FAULT_RATE else r for r in readings]


def corrupt(r: Reading) -> Reading:
    """Simulate the data problems real SCADA feeds have."""
    fault = random.choice(["spike", "nan", "negative", "unknown_tag"])
    if fault == "spike":
        return Reading(r.time, r.well_id, r.tag, r.value * 50)
    if fault == "nan":
        return Reading(r.time, r.well_id, r.tag, float("nan"))
    if fault == "negative":
        return Reading(r.time, r.well_id, r.tag, -abs(r.value) - 1)
    return Reading(r.time, r.well_id, r.tag + "_X", r.value)


def store(conn, readings: list[Reading], wells, tags) -> tuple[int, int]:
    good, bad = [], []
    for r in readings:
        reason = validate(r, wells, tags)
        if reason is None:
            good.append((r.time, r.well_id, r.tag, r.value))
        else:
            value = r.value if r.value is not None and math.isfinite(r.value) else None
            bad.append((r.time, r.well_id, r.tag, value, reason))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO core.readings (time, well_id, tag, value) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING", good)
        cur.executemany(
            "INSERT INTO raw.rejected (time, well_id, tag, value, reason) VALUES (%s, %s, %s, %s, %s)", bad)
    return len(good), len(bad)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", type=float, default=0, help="hours of history to generate first")
    args = parser.parse_args()

    conn = connect()
    wells, tags = load_catalog(conn)
    state: dict = {}
    log.info("loaded %d wells and %d tags", len(wells), len(tags))

    if args.backfill:
        start = datetime.now(timezone.utc) - timedelta(hours=args.backfill)
        steps = int(args.backfill * 3600 / INTERVAL_SECONDS)
        totals = [0, 0]
        for i in range(steps):
            g, b = store(conn, generate(start + timedelta(seconds=i * INTERVAL_SECONDS), state), wells, tags)
            totals[0] += g
            totals[1] += b
        log.info("backfill done: %d stored, %d rejected", *totals)

    while True:
        g, b = store(conn, generate(datetime.now(timezone.utc), state), wells, tags)
        log.info("cycle: %d stored, %d rejected", g, b)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
