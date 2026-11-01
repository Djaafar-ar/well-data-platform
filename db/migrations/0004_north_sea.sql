-- Milestone 7: North Sea scale-up -- well locations, interpreted lithology, more curve families.

-- Where each well is. Surface location from the log's X/Y, converted to latitude/longitude for maps.
ALTER TABLE core.wellbores
    ADD COLUMN surface_x DOUBLE PRECISION,
    ADD COLUMN surface_y DOUBLE PRECISION,
    ADD COLUMN crs       TEXT,                          -- coordinate reference system of surface_x/y
    ADD COLUMN latitude  DOUBLE PRECISION CHECK (latitude BETWEEN -90 AND 90),
    ADD COLUMN longitude DOUBLE PRECISION CHECK (longitude BETWEEN -180 AND 180);

-- Lithology codes used by the FORCE 2020 dataset (interpreted by geoscientists)
CREATE TABLE core.lithology_codes (
    code   INTEGER PRIMARY KEY,
    name   TEXT NOT NULL,
    colour TEXT NOT NULL                               -- conventional colour for plots
);
INSERT INTO core.lithology_codes VALUES
    (30000, 'Sandstone',       '#f4d03f'),
    (65030, 'Sandstone/Shale', '#c9b458'),
    (65000, 'Shale',           '#5d6d7e'),
    (80000, 'Marl',            '#82e0aa'),
    (74000, 'Dolomite',        '#d7bde2'),
    (70000, 'Limestone',       '#5dade2'),
    (70032, 'Chalk',           '#ebf5fb'),
    (88000, 'Halite',          '#f5b7b1'),
    (86000, 'Anhydrite',       '#bb8fce'),
    (99000, 'Tuff',            '#e59866'),
    (90000, 'Coal',            '#17202a'),
    (93000, 'Basement',        '#a04000');

INSERT INTO core.curve_families (mnemonic, family) VALUES
    ('FORCE_2020_LITHOFACIES_LITHOLOGY', 'Lithology (interpreted)'),
    ('FORCE_2020_LITHOFACIES_CONFIDENCE', 'Lithology confidence'),
    ('X_LOC', 'Position'), ('Y_LOC', 'Position'), ('Z_LOC', 'Position'), ('DEPTH_MD', 'Position'),
    ('MUDWEIGHT', 'Mud weight'),
    ('ROP', 'Rate of penetration'), ('ROPA', 'Rate of penetration'),
    ('RSHA', 'Shallow resistivity'),
    ('RXO', 'Flushed-zone resistivity'), ('RMIC', 'Flushed-zone resistivity'),
    ('DRHO', 'Density correction'),
    ('DTS', 'Shear sonic slowness'),
    ('BS', 'Bit size'),
    ('DCAL', 'Differential caliper')
ON CONFLICT (mnemonic) DO NOTHING;

-- Consecutive samples with the same lithology become one interval (top, base, thickness)
CREATE VIEW core.lithology_intervals AS
WITH s AS (
    SELECT s.log_id, s.depth_m, s.value::int AS code,
           CASE WHEN s.value::int = LAG(s.value::int) OVER w THEN 0 ELSE 1 END AS starts_new
    FROM core.log_samples s
    JOIN core.log_curves c USING (log_id, mnemonic)
    WHERE c.family = 'Lithology (interpreted)'
    WINDOW w AS (PARTITION BY s.log_id ORDER BY s.depth_m)
),
g AS (
    SELECT *, SUM(starts_new) OVER (PARTITION BY log_id ORDER BY depth_m) AS interval_no FROM s
)
SELECT g.log_id, g.interval_no, g.code, l.name AS lithology, l.colour,
       min(g.depth_m) AS top_m, max(g.depth_m) AS base_m,
       max(g.depth_m) - min(g.depth_m) AS thickness_m
FROM g
JOIN core.lithology_codes l USING (code)
GROUP BY g.log_id, g.interval_no, g.code, l.name, l.colour;

-- One row per well for maps: where it is and what data we hold for it
CREATE VIEW core.well_map AS
SELECT w.wellbore, w.field, w.country, w.latitude, w.longitude, w.is_synthetic,
       count(DISTINCT l.log_id)                                AS logs,
       max(l.bottom_depth_m)                                   AS deepest_log_m,
       EXISTS (SELECT 1 FROM core.daily_production p WHERE p.wellbore = w.wellbore) AS has_production,
       EXISTS (SELECT 1 FROM core.log_curves c JOIN core.well_logs l2 USING (log_id)
               WHERE l2.wellbore = w.wellbore AND c.family = 'Lithology (interpreted)') AS has_lithology
FROM core.wellbores w
LEFT JOIN core.well_logs l USING (wellbore)
GROUP BY w.wellbore, w.field, w.country, w.latitude, w.longitude, w.is_synthetic;

GRANT SELECT ON core.lithology_codes TO batch_loader;
GRANT SELECT ON core.lithology_codes, core.lithology_intervals, core.well_map TO grafana_reader;
