# Milestone 1: what you must be able to explain

This project only helps you if you can defend every line in an interview.
Before you push milestone 1 to GitHub, answer each question **in your own words, without looking**.
Write your answers in `docs/answers-m1.md`. If you can't answer one, read the file it points to
until you can.

## Docker

1. What is the difference between an image and a container?
2. Why does `docker-compose.yml` bind ports to `127.0.0.1:5432` instead of just `5432`? What would change on a server?
3. What happens to the data if you run `docker compose down`? And `docker compose down -v`? Why? (look at `volumes:`)
4. How does the simulator find the database? Why is the host called `db` and not `localhost`?
5. Why does the simulator's Dockerfile create a user called `app`?

## PostgreSQL

6. Why is the primary key of `core.readings` `(well_id, tag, time)`? What would go wrong without it?
7. What is the difference between `min_valid`/`max_valid` and `alarm_low`/`alarm_high`? Give an oil-field example of each.
8. Why do rejected readings go to a table instead of being deleted?
9. What can the `grafana_reader` role do? What can it not do? Why does that matter?
10. What is a BRIN index, and why does it suit telemetry better than a normal index here?

## Python

11. Why is `validate()` in its own file with no database code?
12. Walk through what happens to one corrupted reading, from `corrupt()` to the database.
13. What does `ON CONFLICT DO NOTHING` protect against?

## CI

14. List what `.github/workflows/ci.yml` checks, in order. Why test against a real PostgreSQL and not only unit tests?

## Hands-on tasks (do them yourself, no AI)

- [ ] Add a new tag `CASING_P` (casing pressure, bar, physical 0–300, alarm high 150) to the seed and the simulator. Rebuild with `docker compose down -v && docker compose up -d --build`. It should appear in the dashboard's Tag list.
- [ ] Add a validation rule: reject readings whose timestamp is more than 24 hours old (late data from a buffered RTU). Write the test first in `tests/test_validation.py`, watch it fail, then make it pass.
- [ ] Solve all 7 exercises in `sql/practice.sql` before opening the answers.
- [ ] Stop the simulator for 6 minutes and watch the freshness table turn red. Explain why.

When all of this is done, milestone 1 is yours, not mine.
