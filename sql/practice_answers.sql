-- Answers to sql/practice.sql. Look only after you have tried.

-- 1.
SELECT w.well_id,
       (SELECT count(*) FROM core.readings r WHERE r.well_id = w.well_id) AS valid,
       (SELECT count(*) FROM raw.rejected  x WHERE x.well_id = w.well_id) AS rejected
FROM core.wells w
ORDER BY w.well_id;

-- 2.
SELECT well_id,
       round(avg(value)::numeric, 1) AS avg_whp,
       min(value) AS min_whp,
       max(value) AS max_whp
FROM core.readings
WHERE tag = 'WHP' AND time > now() - interval '1 hour'
GROUP BY well_id
ORDER BY well_id;

-- 3.
SELECT time, value,
       round((value - LAG(value) OVER (ORDER BY time))::numeric, 2) AS change
FROM core.readings
WHERE well_id = 'W-01' AND tag = 'WHP'
ORDER BY time DESC
LIMIT 20;

-- 4.
SELECT well_id, time, round(abs(change)::numeric, 2) AS jump
FROM (
    SELECT well_id, time,
           value - LAG(value) OVER (PARTITION BY well_id ORDER BY time) AS change
    FROM core.readings
    WHERE tag = 'WHP'
) t
WHERE change IS NOT NULL
ORDER BY abs(change) DESC
LIMIT 5;

-- 5.
SELECT w.well_id
FROM core.wells w
WHERE NOT EXISTS (
    SELECT 1 FROM core.readings r
    WHERE r.well_id = w.well_id AND r.time > now() - interval '5 minutes'
);

-- 6.
SELECT date_trunc('hour', time) AS hour, well_id, round(avg(value)::numeric, 1) AS avg_whp
FROM core.readings
WHERE tag = 'WHP' AND time > now() - interval '6 hours'
GROUP BY 1, 2
ORDER BY 1, 2;

-- 7. Consecutive alarm readings form one "island". A new island starts when the
--    gap from the previous alarm reading is longer than one polling interval.
WITH a AS (
    SELECT well_id, tag, time,
           CASE WHEN time - LAG(time) OVER (PARTITION BY well_id, tag ORDER BY time)
                     <= interval '30 seconds' THEN 0 ELSE 1 END AS new_island
    FROM core.alarms
),
b AS (
    SELECT *, SUM(new_island) OVER (PARTITION BY well_id, tag ORDER BY time) AS island
    FROM a
)
SELECT well_id, tag, min(time) AS started, max(time) AS ended, max(time) - min(time) AS duration
FROM b
GROUP BY well_id, tag, island
ORDER BY duration DESC
LIMIT 10;
