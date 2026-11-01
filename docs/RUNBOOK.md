# Runbook

What to do when something happens. Every Grafana alert links to its section here.
On the server, run commands from `/opt/well-data-platform` as the `deploy` user, with:

```bash
DC="docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile https"   # or --profile tunnel
```
(On your PC, just use `docker compose`.)

## Daily 2-minute check

1. Grafana → **Alerting → Alert rules**: everything green ("Normal")?
2. **Well Overview**: freshness column green, rejection rate under 2%?
3. **Field Production → Load runs**: no `failed` runs?
4. On the server: `tail -3 /var/backups/wells/backup.log` shows last night's `backup ok`.

## Common commands

| Task | Command |
|---|---|
| What is running? | `$DC ps` |
| Logs of one service | `$DC logs --tail 100 -f grafana` |
| Restart one service | `$DC restart simulator` |
| SQL shell | `$DC exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'` |
| Apply new migrations | `$DC run --rm migrate` |
| Fetch + load public data | `$DC run --rm fetch north-sea && $DC run --rm load-all` |
| Backup now | `bash deploy/backup.sh` |
| Prove the backup restores | `bash deploy/restore-test.sh` |
| Disk usage | `df -h /` and `docker system df` |

---

## Telemetry stale

**Alert:** no reading for more than 5 minutes. **Severity: critical.** Operators are blind to the wells.

1. `$DC ps`: is `simulator` (in real life: the SCADA/OPC collector) running? If it restarts in a loop:
   `$DC logs --tail 100 simulator`.
2. Database reachable? `$DC exec db pg_isready`. If not: `$DC logs --tail 100 db`, check disk space
   (`df -h /`): a full disk stops PostgreSQL.
3. Real-world equivalent: RTU powered off, radio/satellite link down, collector lost its connection.
4. When data flows again, the alert resolves by itself. Note the gap duration in the shift log:
   **the data from the gap is lost unless the RTU buffers it.**

## Wellhead pressure high

**Alert:** WHP above 180 bar on a well for at least 1 minute.

1. Open **Well Overview**, select the well and the WHP tag: sudden step (valve closed downstream,
   blocked flowline) or slow rise (pressure build-up after a shut-in)?
2. Check the other tags of the same well: falling flowline pressure + rising WHP = restriction
   between the wellhead and the flowline.
3. Rule out bad data: a value of 4,000 bar would have been **rejected** (physical limit), not alarmed.
   An alarm means the value was physically possible.
4. Real world: call the control room / field operator. Data engineers do not operate wells.

## Gas-lift injection low

**Alert:** gas-lift injection below 5,000 Sm3/d on a gas-lifted well.

1. Is it one well (its injection valve) or all gas-lifted wells at once (compressor / gas supply trip)?
2. Watch the well's WHP and production: without lift gas, a gas-lifted well slows down or stops.
3. Escalate to production operations with the time it started (alarms table).

## Telemetry rejection rate high

**Alert:** more than 5% of readings rejected in 15 minutes.

1. **Well Overview → Rejection reasons**: one reason dominating?
   - `outside physical range` on one tag → a faulty sensor or a wrong scaling in the SCADA config;
   - `unknown tag` → someone added a tag in the field that is not in `core.tags`;
   - `not a number` → transmitter fault or communication errors.
2. Find the well and tag: `SELECT well_id, tag, reason, count(*) FROM raw.rejected WHERE time > now() - interval '1 hour' GROUP BY 1,2,3 ORDER BY 4 DESC;`
3. Fix at the source (instrument technician), or, if the tag is legitimate, add it to `core.tags`
   with a migration. Never widen a physical limit just to make the alert go away.

## Batch load failed

**Alert:** a load run has status `failed` in the last 24 hours.

1. Why: `SELECT run_id, kind, source_name, message FROM core.load_runs WHERE status = 'failed' ORDER BY run_id DESC LIMIT 5;`
2. Typical messages:
   - `missing required columns` → the export format changed: compare the file's header with `COLUMN_MAP` in `loader/production_rules.py`;
   - `no WELL name` / `depth column ...` → the LAS file is broken: ask the provider for a corrected file;
   - `password authentication failed` → `.env` and the database disagree (see "Rotate a password").
3. A failed run changes **nothing** in the data (it is one transaction). Fix the cause, run the load again.

## Rotate a password

Example for the batch loader:
1. New password: `openssl rand -base64 24`. Put it in `.env` (`LOADER_PASSWORD=...`).
2. In the database:
   ```bash
   echo "ALTER ROLE batch_loader PASSWORD '<new>';" | $DC exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
   ```
3. Restart what uses it (`$DC up -d`). For the Grafana reader role, restart `grafana`.

## Restore from backup

1. Pick the file: `ls -lt /var/backups/wells/`.
2. `bash deploy/restore.sh /var/backups/wells/<file>.dump`. It asks you to type RESTORE and takes a
   safety backup of the current state first.
3. `bash deploy/restore-test.sh`, then check the dashboards.

## Automatic deployment

Every push to `main` runs **CI**. If CI passes, the **Deploy** workflow connects to the server over SSH,
moves the code to exactly the commit CI tested, takes a backup, applies migrations, restarts the
services and runs a health check. A failed health check makes the deploy fail (red in GitHub Actions).

### One-time setup
1. On **your PC**, create a key used only by GitHub:
   ```powershell
   ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\wdp_deploy -C "github-deploy" -N '""'
   ```
2. Authorise it on the server for the `deploy` user (append the **.pub** content to
   `/home/deploy/.ssh/authorized_keys`).
3. Record the server's identity (run on your PC, after checking you are on the right server):
   ```powershell
   ssh-keyscan -t ed25519 <server-ip>
   ```
4. GitHub → repository → **Settings → Secrets and variables → Actions**:
   - secret `DEPLOY_HOST` = server IP or name
   - secret `DEPLOY_USER` = `deploy`
   - secret `DEPLOY_SSH_KEY` = content of `wdp_deploy` (the **private** key, never commit it)
   - secret `DEPLOY_KNOWN_HOSTS` = the line printed by `ssh-keyscan`
   - variable `DEPLOY_PROFILE` = `https` or `tunnel`
5. Push any commit to `main` and watch **Actions → Deploy**.

Without `DEPLOY_HOST`, the Deploy workflow simply prints a notice and does nothing.

### Roll back
Revert the bad commit on GitHub (`git revert <sha>` then push): CI runs and the previous version is
deployed. If a migration damaged data, restore the backup the deploy took just before (see above).
