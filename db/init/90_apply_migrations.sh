#!/bin/bash
# On a brand-new database, apply all migrations right after the base schema.
set -euo pipefail
PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" MIGRATIONS_DIR=/migrations bash /migrate.sh
