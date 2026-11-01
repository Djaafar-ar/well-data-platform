#!/bin/bash
# Prove the latest backup can actually be restored -- without touching the live database.
#
#   bash deploy/restore-test.sh
#
# 1. checks the backup file's fingerprint
# 2. restores it into a scratch database (wells_restore_test)
# 3. compares row counts of the key tables with the live database
# 4. drops the scratch database
# Exit code 0 = restore works. Run weekly by cron (see deploy/provision.sh).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/wells}"
DC="${DC:-docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml}"
SCRATCH=wells_restore_test
TABLES="core.wells core.readings core.daily_production core.load_runs core.wellbores core.well_logs core.log_samples"

latest="$(ls -1t "$BACKUP_DIR"/wells-*.dump 2>/dev/null | head -1 || true)"
if [ -z "$latest" ]; then
    echo "restore test FAILED: no backup found in $BACKUP_DIR" >&2
    exit 1
fi
echo "$(date -u +%FT%TZ) restore test of $latest"

if [ -f "$latest.sha256" ]; then
    (cd "$(dirname "$latest")" && sha256sum --check --quiet "$(basename "$latest").sha256")
    echo "fingerprint ok"
fi

psql_db() { $DC exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d $1 -v ON_ERROR_STOP=1 -tAq"; }

echo "DROP DATABASE IF EXISTS $SCRATCH; CREATE DATABASE $SCRATCH;" | psql_db postgres
$DC exec -T db sh -c "pg_restore -U \"\$POSTGRES_USER\" -d $SCRATCH --no-owner --exit-on-error" < "$latest"

# Live rows can only have grown since the backup, so restored <= live, and restored must be > 0
status=0
for t in $TABLES; do
    restored="$(echo "SELECT count(*) FROM $t" | psql_db $SCRATCH)"
    live="$(echo "SELECT count(*) FROM $t" | psql_db wells)"
    if [ "$restored" -gt 0 ] && [ "$restored" -le "$live" ]; then mark=ok; else mark=MISMATCH; status=1; fi
    printf '  %-26s restored %10s   live %10s   %s\n' "$t" "$restored" "$live" "$mark"
done

echo "DROP DATABASE $SCRATCH;" | psql_db postgres
if [ "$status" -eq 0 ]; then
    echo "$(date -u +%FT%TZ) restore test PASSED"
else
    echo "$(date -u +%FT%TZ) restore test FAILED" >&2
fi
exit "$status"
