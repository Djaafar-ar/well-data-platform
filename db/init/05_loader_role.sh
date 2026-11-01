#!/bin/bash
# Sets the batch loader's password (its role is created in 04_production.sql).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    ALTER ROLE batch_loader PASSWORD '${LOADER_PASSWORD}';
EOSQL
