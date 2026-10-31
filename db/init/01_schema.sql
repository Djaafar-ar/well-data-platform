-- Well Data Platform: database schema (milestone 1)
-- Runs automatically the first time the Postgres container starts.
--
-- Layout:
--   core.wells       one row per well (the "master data")
--   core.tags        sensor catalog: what each tag measures, its unit and its valid range
--   core.readings    validated telemetry (time series)
--   raw.rejected     readings that failed validation, kept with the reason (never silently dropped)

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE core.wells (
    well_id     TEXT PRIMARY KEY,                 -- e.g. 'W-01'
    field       TEXT NOT NULL,
    lift_type   TEXT NOT NULL CHECK (lift_type IN ('natural', 'gas_lift')),
    status      TEXT NOT NULL DEFAULT 'producing' CHECK (status IN ('producing', 'shut_in', 'abandoned')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE core.tags (
    tag         TEXT PRIMARY KEY,                 -- e.g. 'WHP'
    description TEXT NOT NULL,
    unit        TEXT NOT NULL,
    min_valid   DOUBLE PRECISION NOT NULL,        -- physical limits: outside = bad data, not an alarm
    max_valid   DOUBLE PRECISION NOT NULL,
    alarm_low   DOUBLE PRECISION,                 -- operating limits: outside = alarm
    alarm_high  DOUBLE PRECISION,
    CHECK (min_valid < max_valid)
);

CREATE TABLE core.readings (
    time        TIMESTAMPTZ      NOT NULL,
    well_id     TEXT             NOT NULL REFERENCES core.wells (well_id),
    tag         TEXT             NOT NULL REFERENCES core.tags (tag),
    value       DOUBLE PRECISION NOT NULL,
    ingested_at TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (well_id, tag, time)              -- a sensor cannot have two values at the same instant
);

-- BRIN index: tiny and fast for append-only time series (rows arrive in time order)
CREATE INDEX readings_time_brin ON core.readings USING BRIN (time);

CREATE TABLE raw.rejected (
    id          BIGSERIAL PRIMARY KEY,
    time        TIMESTAMPTZ,
    well_id     TEXT,
    tag         TEXT,
    value       DOUBLE PRECISION,
    reason      TEXT NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Latest value per well and tag, with its age: the basis for "is the data fresh?" checks
CREATE VIEW core.latest_readings AS
SELECT DISTINCT ON (r.well_id, r.tag)
       r.well_id, r.tag, t.unit, r.value, r.time,
       now() - r.time AS age
FROM core.readings r
JOIN core.tags t USING (tag)
ORDER BY r.well_id, r.tag, r.time DESC;

-- Readings outside operating limits
CREATE VIEW core.alarms AS
SELECT r.time, r.well_id, r.tag, r.value, t.unit,
       CASE WHEN r.value < t.alarm_low THEN 'LOW' ELSE 'HIGH' END AS level
FROM core.readings r
JOIN core.tags t USING (tag)
WHERE r.value < t.alarm_low OR r.value > t.alarm_high;

-- Least privilege: one role that can only write telemetry, one that can only read (for Grafana).
-- Passwords are set by 03_roles.sh from environment variables, never hard-coded here.
CREATE ROLE ingest_writer LOGIN;
GRANT USAGE ON SCHEMA core, raw TO ingest_writer;
GRANT SELECT ON core.wells, core.tags TO ingest_writer;
GRANT INSERT ON core.readings, raw.rejected TO ingest_writer;
GRANT USAGE ON SEQUENCE raw.rejected_id_seq TO ingest_writer;

CREATE ROLE grafana_reader LOGIN;
GRANT USAGE ON SCHEMA core, raw TO grafana_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA core, raw TO grafana_reader;
