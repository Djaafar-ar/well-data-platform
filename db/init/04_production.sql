-- Milestone 2: daily field production data (batch loads) and load auditing.
--
--   core.load_runs         one row per file load: who/what/when, row counts, file fingerprint (lineage)
--   core.daily_production  validated daily production per wellbore
--   raw.production_rejected rows that failed validation, kept with the reason and the original values

CREATE TABLE core.load_runs (
    run_id         BIGSERIAL PRIMARY KEY,
    source_name    TEXT        NOT NULL,              -- e.g. 'Volve production data.xlsx'
    file_sha256    TEXT        NOT NULL,              -- fingerprint: the same file is never loaded twice by accident
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    rows_read      INTEGER,
    rows_loaded    INTEGER,
    rows_rejected  INTEGER,
    rows_flagged   INTEGER,
    status         TEXT        NOT NULL DEFAULT 'running'
                   CHECK (status IN ('running', 'succeeded', 'failed', 'skipped'))
);

CREATE TABLE core.daily_production (
    wellbore           TEXT    NOT NULL,              -- e.g. '15/9-F-12'
    prod_date          DATE    NOT NULL,
    on_stream_hrs      NUMERIC(5, 2),
    avg_downhole_press DOUBLE PRECISION,              -- bar
    avg_downhole_temp  DOUBLE PRECISION,              -- degC
    avg_whp            DOUBLE PRECISION,              -- wellhead pressure, bar
    avg_wht            DOUBLE PRECISION,              -- wellhead temperature, degC
    avg_choke_pct      DOUBLE PRECISION,              -- %
    oil_sm3            DOUBLE PRECISION,
    gas_sm3            DOUBLE PRECISION,
    water_sm3          DOUBLE PRECISION,
    water_inj_sm3      DOUBLE PRECISION,
    flow_kind          TEXT,                          -- 'production' or 'injection'
    well_type          TEXT,                          -- e.g. 'OP' (oil producer), 'WI' (water injector)
    quality_flag       TEXT,                          -- kept but suspicious, e.g. volumes with zero hours on stream
    run_id             BIGINT  NOT NULL REFERENCES core.load_runs (run_id),
    PRIMARY KEY (wellbore, prod_date)
);

CREATE TABLE raw.production_rejected (
    id          BIGSERIAL PRIMARY KEY,
    run_id      BIGINT REFERENCES core.load_runs (run_id),
    source_row  INTEGER,                              -- line in the source file, to find it again
    wellbore    TEXT,
    prod_date   TEXT,
    reason      TEXT  NOT NULL,
    original    JSONB NOT NULL,                       -- the full original row, untouched
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Water cut = water / (oil + water): rising water cut is the classic sign of a maturing well
CREATE VIEW core.production_kpis AS
SELECT wellbore, prod_date, on_stream_hrs, oil_sm3, gas_sm3, water_sm3, water_inj_sm3,
       CASE WHEN COALESCE(oil_sm3, 0) + COALESCE(water_sm3, 0) > 0
            THEN 100.0 * COALESCE(water_sm3, 0) / (COALESCE(oil_sm3, 0) + COALESCE(water_sm3, 0))
       END AS water_cut_pct,
       CASE WHEN oil_sm3 > 0 THEN gas_sm3 / oil_sm3 END AS gor_sm3_sm3,
       quality_flag
FROM core.daily_production;

-- Least privilege for the batch loader: it can write production data and its own audit trail, nothing else
CREATE ROLE batch_loader LOGIN;
GRANT USAGE ON SCHEMA core, raw TO batch_loader;
GRANT SELECT, INSERT, UPDATE ON core.load_runs, core.daily_production TO batch_loader;
GRANT INSERT ON raw.production_rejected TO batch_loader;
GRANT USAGE ON SEQUENCE core.load_runs_run_id_seq, raw.production_rejected_id_seq TO batch_loader;

GRANT SELECT ON core.load_runs, core.daily_production, core.production_kpis, raw.production_rejected TO grafana_reader;
