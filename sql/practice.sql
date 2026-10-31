-- SQL practice on your own data.
-- Connect with:  docker compose exec db psql -U wells_admin -d wells
-- Try to write each query yourself first. The answers are in sql/practice_answers.sql.

-- 1. How many valid readings and how many rejected readings are there per well?

-- 2. For each well, the average, minimum and maximum wellhead pressure (WHP) over the last hour.

-- 3. For W-01, the change in WHP between each reading and the previous one.
--    (hint: window function LAG)

-- 4. The 5 largest one-step jumps in WHP across all wells. A big jump can mean a bad sensor.

-- 5. Wells that have sent NO reading at all for any tag in the last 5 minutes.
--    (stop the simulator first:  docker compose stop simulator)

-- 6. Hourly average WHP per well for the last 6 hours.
--    (hint: date_trunc)

-- 7. For each alarm, how long did the well stay in alarm? (hard: "gaps and islands")
