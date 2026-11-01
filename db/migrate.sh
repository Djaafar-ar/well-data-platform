#!/bin/bash
# Applies every db/migrations/*.sql file that has not been applied yet, in name order,
# each in its own transaction, and records it in public.schema_migrations.
#
# Used in two places:
#   - on a brand-new database, by db/init/90_apply_migrations.sh
#   - on an existing database:  docker compose run --rm migrate
#
# Connection comes from the standard PG* environment variables (PGHOST, PGUSER, PGDATABASE, PGPASSWORD).
set -euo pipefail
export PGOPTIONS="-c client_min_messages=warning"

MIGRATIONS_DIR="${MIGRATIONS_DIR:-/migrations}"

psql -v ON_ERROR_STOP=1 -q -c "CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"

applied=0
for file in $(ls "$MIGRATIONS_DIR"/*.sql | sort); do
    version="$(basename "$file" .sql)"
    done_already="$(psql -tA -c "SELECT 1 FROM public.schema_migrations WHERE version = '$version'")"
    if [ -n "$done_already" ]; then
        continue
    fi
    echo "applying $version"
    psql -v ON_ERROR_STOP=1 -q --single-transaction \
         -f "$file" \
         -c "INSERT INTO public.schema_migrations (version) VALUES ('$version')"
    applied=$((applied + 1))
done
echo "migrations applied: $applied"
psql -c "SELECT version, applied_at FROM public.schema_migrations ORDER BY version"
