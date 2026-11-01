#!/bin/bash
# Restore the live database from a backup. DESTRUCTIVE: the current data is replaced.
#
#   bash deploy/restore.sh /var/backups/wells/wells-20261101T023000Z.dump
#
# Stops the services that write to the database, restores, starts everything again.
set -euo pipefail

DC="${DC:-docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml}"
file="${1:?usage: restore.sh <backup file>}"

[ -f "$file" ] || { echo "no such file: $file" >&2; exit 1; }
if [ -f "$file.sha256" ]; then
    (cd "$(dirname "$file")" && sha256sum --check --quiet "$(basename "$file").sha256")
fi

echo "This will REPLACE the live database with: $file"
read -r -p "Type the word RESTORE to continue: " answer
[ "$answer" = "RESTORE" ] || { echo "cancelled"; exit 1; }

echo "safety copy of the current database first..."
bash "$(dirname "$0")/backup.sh"

$DC stop simulator grafana
$DC exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error' < "$file"
$DC start simulator grafana
echo "restore done. Check the dashboards, then run: bash deploy/restore-test.sh"
