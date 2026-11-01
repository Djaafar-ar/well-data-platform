-- Milestone 3: well logs (LAS) and a data catalog.
--
--   core.wellbores        master list of wellbores, whatever file they came from
--   core.wellbore_aliases other names for the same wellbore (e.g. 'NO 15/9-F-12', '15/9-19 SR')
--   core.curve_families   reference data: vendor mnemonics -> one standard measurement family
--   core.well_logs        one row per loaded LAS file: wellbore, depth range, header (catalog entry)
--   core.log_curves       one row per curve: unit, family, valid/null/out-of-range counts, min/max/mean
--   core.log_samples      the measurements themselves, depth in metres
--   core.data_catalog     one view to answer "what data do we have, for which well, from where?"

-- Lineage: what kind of file each run loaded, under which licence, from where
ALTER TABLE core.load_runs
    ADD COLUMN kind       TEXT NOT NULL DEFAULT 'production' CHECK (kind IN ('production', 'well_log')),
    ADD COLUMN licence    TEXT,
    ADD COLUMN source_url TEXT,
    ADD COLUMN message    TEXT;

CREATE TABLE core.wellbores (
    wellbore     TEXT PRIMARY KEY,
    field        TEXT,
    operator     TEXT,
    country      TEXT,
    is_synthetic BOOLEAN NOT NULL DEFAULT false,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE core.wellbore_aliases (
    alias    TEXT PRIMARY KEY,
    wellbore TEXT NOT NULL REFERENCES core.wellbores (wellbore),
    source   TEXT
);

-- Every wellbore already in the production table becomes a catalog entry
INSERT INTO core.wellbores (wellbore, is_synthetic)
SELECT DISTINCT wellbore, wellbore LIKE 'DEMO-%' FROM core.daily_production
ON CONFLICT DO NOTHING;

ALTER TABLE core.daily_production
    ADD CONSTRAINT daily_production_wellbore_fk FOREIGN KEY (wellbore) REFERENCES core.wellbores (wellbore);

CREATE TABLE core.curve_families (
    mnemonic TEXT PRIMARY KEY,                     -- upper case, as written in LAS files
    family   TEXT NOT NULL
);

-- Different logging companies use different names for the same measurement
INSERT INTO core.curve_families (mnemonic, family) VALUES
    ('GR', 'Gamma ray'), ('SGR', 'Gamma ray'), ('CGR', 'Gamma ray'), ('GSGR', 'Gamma ray'),
    ('IDGR', 'Gamma ray'), ('GAMN', 'Gamma ray'), ('GRC', 'Gamma ray'),
    ('DEN', 'Bulk density'), ('RHOB', 'Bulk density'), ('ZDEN', 'Bulk density'), ('DLDN', 'Bulk density'),
    ('DFAR', 'Bulk density'), ('RHOZ', 'Bulk density'),
    ('NEU', 'Neutron porosity'), ('NPHI', 'Neutron porosity'), ('TNPH', 'Neutron porosity'),
    ('NCNPL', 'Neutron porosity'),
    ('RDEP', 'Deep resistivity'), ('ILD', 'Deep resistivity'), ('IDID', 'Deep resistivity'),
    ('LLD', 'Deep resistivity'), ('RT', 'Deep resistivity'), ('AT90', 'Deep resistivity'),
    ('RMED', 'Medium resistivity'), ('ILM', 'Medium resistivity'), ('IDIM', 'Medium resistivity'),
    ('LLS', 'Medium resistivity'), ('AT30', 'Medium resistivity'),
    ('AC', 'Sonic slowness'), ('DT', 'Sonic slowness'), ('DTC', 'Sonic slowness'), ('ACTC', 'Sonic slowness'),
    ('CALI', 'Caliper'), ('CAL', 'Caliper'), ('HCAL', 'Caliper'), ('DLCL', 'Caliper'),
    ('SP', 'Spontaneous potential'), ('IDSP', 'Spontaneous potential'),
    ('PE', 'Photoelectric factor'), ('PEF', 'Photoelectric factor'), ('DLPE', 'Photoelectric factor'),
    ('COND', 'Conductivity'), ('IDIDC', 'Conductivity');

CREATE TABLE core.well_logs (
    log_id          BIGSERIAL PRIMARY KEY,
    run_id          BIGINT NOT NULL REFERENCES core.load_runs (run_id),
    wellbore        TEXT   NOT NULL REFERENCES core.wellbores (wellbore),
    source_name     TEXT   NOT NULL,
    file_sha256     TEXT   NOT NULL,
    depth_unit      TEXT   NOT NULL,                -- as written in the file (M, FT...)
    top_depth_m     DOUBLE PRECISION,
    bottom_depth_m  DOUBLE PRECISION,
    step_m          DOUBLE PRECISION,
    n_depths        INTEGER NOT NULL,
    null_value      DOUBLE PRECISION,
    service_company TEXT,
    log_date        TEXT,
    header          JSONB  NOT NULL,                -- the full LAS header, kept for traceability
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE core.log_curves (
    log_id         BIGINT NOT NULL REFERENCES core.well_logs (log_id) ON DELETE CASCADE,
    mnemonic       TEXT   NOT NULL,
    unit           TEXT,
    description    TEXT,
    family         TEXT,                            -- NULL = unknown mnemonic: a job for the data steward
    n_valid        INTEGER NOT NULL,
    n_null         INTEGER NOT NULL,
    n_out_of_range INTEGER NOT NULL,
    min_value      DOUBLE PRECISION,
    max_value      DOUBLE PRECISION,
    mean_value     DOUBLE PRECISION,
    PRIMARY KEY (log_id, mnemonic)
);

CREATE TABLE core.log_samples (
    log_id   BIGINT NOT NULL,
    mnemonic TEXT   NOT NULL,
    depth_m  DOUBLE PRECISION NOT NULL,
    value    DOUBLE PRECISION NOT NULL,             -- nulls and out-of-range values are not stored
    PRIMARY KEY (log_id, mnemonic, depth_m),
    FOREIGN KEY (log_id, mnemonic) REFERENCES core.log_curves (log_id, mnemonic) ON DELETE CASCADE
);

CREATE VIEW core.data_catalog AS
SELECT 'production'::text                         AS kind,
       p.wellbore,
       w.field,
       w.is_synthetic,
       min(p.prod_date)::text                     AS covers_from,
       max(p.prod_date)::text                     AS covers_to,
       count(*)                                   AS records,
       string_agg(DISTINCT r.source_name, ', ')   AS sources,
       string_agg(DISTINCT r.licence, ', ')       AS licences
FROM core.daily_production p
JOIN core.wellbores w USING (wellbore)
JOIN core.load_runs r USING (run_id)
GROUP BY p.wellbore, w.field, w.is_synthetic
UNION ALL
SELECT 'well_log',
       l.wellbore,
       w.field,
       w.is_synthetic,
       round(l.top_depth_m::numeric, 1) || ' m',
       round(l.bottom_depth_m::numeric, 1) || ' m',
       l.n_depths,
       l.source_name,
       r.licence
FROM core.well_logs l
JOIN core.wellbores w USING (wellbore)
JOIN core.load_runs r USING (run_id);

-- Batch loader: can maintain the catalog and replace a log it loaded, nothing else
GRANT SELECT, INSERT, UPDATE ON core.wellbores, core.wellbore_aliases TO batch_loader;
GRANT SELECT ON core.curve_families TO batch_loader;
GRANT SELECT, INSERT, DELETE ON core.well_logs, core.log_curves, core.log_samples TO batch_loader;
GRANT USAGE ON SEQUENCE core.well_logs_log_id_seq TO batch_loader;

GRANT SELECT ON core.wellbores, core.wellbore_aliases, core.curve_families, core.well_logs,
               core.log_curves, core.log_samples, core.data_catalog TO grafana_reader;
