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

---

# Milestone 2: batch loading

## Questions

15. What are the three outcomes a production row can have, and why is "flagged" different from "rejected"? Give one example of each from the sample file.
16. What does the loader do if you run it twice on the same file? Which two mechanisms make that safe?
17. Why does a rejected row keep the original values and the source line number?
18. What is `core.load_runs` for? What question can it answer six months later?
19. Why can the `batch_loader` role not read `raw.production_rejected`? What did we change in the code because of that?
20. What is water cut, and why does it rise over a well's life?

## Hands-on tasks (no AI)

- [ ] Run the loader on the sample, then run it again and explain the second result.
- [ ] Open `tests/fixtures/sample_production.csv` in Excel, break one more row yourself (for example, a negative gas volume), save it under a new name in `data/`, load it, and find your row in the rejects panel.
- [ ] Find the rule that rejects a wellhead temperature (`AVG_WHT_P`) above 200 °C. Which file and which line? Prove it works by adding a test in `tests/test_production_rules.py`.
- [ ] Write a SQL query: total oil per wellbore per month for 2015.

---

# Milestone 3: well logs and data catalog

## Questions

21. What is a LAS file? What are its header, curves and data sections?
22. Why are depths converted to metres when they are loaded? What happens with an unknown depth unit, and why is that better than guessing?
23. `GR`, `GSGR` and `GAMN` are the same measurement. How does the database know that? What happens to a mnemonic it does not know?
24. In the real Scorpio E1 log, a gamma-ray value of −2324.28 appears 200 times. The file's declared NULL is −99999. What is going on, and how did the loader catch it?
25. `15/9-F-12` and `NO 15/9-F-12 H` are the same wellbore. Why does a company need `core.wellbore_aliases`?
26. What question does `core.data_catalog` answer? Why does it show the licence?
27. What is a migration, and why can you now upgrade the database without `docker compose down -v`?

## Hands-on tasks (no AI)

- [ ] `docker compose run --rm fetch` then `docker compose run --rm load-all`. Explain each line of the output.
- [ ] In **Well Logs**, select well 15/9-19. Find a depth interval where gamma ray is low and resistivity is high. What could it mean?
- [ ] Map the unmapped mnemonic `DNEAR` (near density) to `Bulk density`: write a new migration file `db/migrations/0004_map_dnear.sql` that (1) inserts the mapping into `core.curve_families` and (2) updates the curves **already loaded** (`UPDATE core.log_curves SET family = ... WHERE mnemonic = 'DNEAR'`). Run `docker compose run --rm migrate` and check the "Unmapped mnemonics" panel. Why is step (2) needed?

---

# Milestone 4: alerting

## Questions

28. List the 5 alert rules. For each: what it checks, the threshold, and who should react.
29. Why does "Telemetry stale" alert when there is **no data at all**, but "Wellhead pressure high" does not?
30. What is the `for: 1m` in an alert rule for? What would happen without it?
31. Why must alert message templates not contain `$values` in a provisioning file here?

## Hands-on tasks

- [ ] `docker compose stop simulator`, wait 7 minutes, and watch "Telemetry stale" go from Normal → Pending → Firing. Start it again and watch it resolve.
- [ ] (Optional) Configure Gmail SMTP with an App Password in `.env` and receive a real alert email.

---

# Milestone 5: deployment

## Questions

32. What does `deploy/provision.sh` do, step by step? Why does it only disable SSH passwords if the deploy user already has a key?
33. In production, which ports are open on the server, and which container publishes them? Why are the database and Grafana not published?
34. Docker-published ports bypass ufw. Explain what that means and why this project is still safe.
35. What is the difference between option A (Caddy + HTTPS) and option B (Cloudflare tunnel)? When would a company use B?
36. "A backup that has never been restored is only a hope." What exactly does `restore-test.sh` check?
37. Where should backups live besides the server, and why?

## Hands-on tasks

- [ ] Deploy with option A or B (docs/DEPLOY.md). Prove port 5432 is closed from your PC (`Test-NetConnection`).
- [ ] Run `bash deploy/backup.sh` and `bash deploy/restore-test.sh` on the server and read the output.

---

# Milestone 6: automatic deployment

## Questions

38. What happens, in order, from `git push` to the new version running on the server?
39. Why does the deploy job use `workflow_run.head_sha` instead of "the latest main"?
40. What is `DEPLOY_KNOWN_HOSTS` for? What attack does it prevent?
41. A deploy broke production. What are your two ways back (see RUNBOOK.md)?

## Hands-on tasks

- [ ] Set up the 4 secrets and the variable (RUNBOOK.md → Automatic deployment), push a small README change, and watch Actions → Deploy.
- [ ] Read the Deploy log and find: the backup line, the migrations line, and the health check line.

---

# Milestone 7: North Sea scale-up

## Questions

42. What is the FORCE 2020 dataset, who published it, and what may you do with it (licence)?
43. The download is verified with a *Git object id* instead of SHA-256. What is that id, and why could we compute it without downloading the files first?
44. A download is cut halfway. What does the fetch script do the next time, and which HTTP feature makes that possible?
45. The LAS header says `WELL = 15/9-13 Sleipner East Appr` and `UWI = 15/9-13`. Which name becomes the wellbore key, and why?
46. The logs give positions like `x = 437642, y = 6470975`. What coordinate system is that? How do they become latitude/longitude, and what is the uncertainty of the assumption we made?
47. Why are the position curves (X_LOC, Y_LOC, Z_LOC, DEPTH_MD) kept only as statistics and not stored sample by sample?
48. Well 29/6-1 has photoelectric factor readings up to 377 b/e. Rock is ~1.5-6. What causes this, and why is excluding those samples correct?
49. How does `core.lithology_intervals` turn thousands of depth samples into a short list of layers? (Hint: the same "gaps and islands" idea as SQL exercise 7.)
50. Why does the "Well-log samples" stat use `pg_class.reltuples` instead of `count(*)`?

## Hands-on tasks

- [ ] `docker compose run --rm migrate`, `docker compose run --rm fetch north-sea`, `docker compose run --rm load-all`. Open **North Sea Wells**.
- [ ] Pick a well on the map. In the rock composition, which lithology dominates? Find a sandstone interval in the table and check that gamma ray is low there.
- [ ] Interrupt the download (Ctrl+C) in the middle, run it again, and watch it resume.
