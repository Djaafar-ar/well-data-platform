#!/bin/bash
# Sets the passwords of the application roles from environment variables.
# Runs once, the first time the Postgres container starts (after 01_ and 02_ .sql,
# and before 04_ .sql, so the batch_loader role is created there and its password set by 05_).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    ALTER ROLE ingest_writer  PASSWORD '${INGEST_PASSWORD}';
    ALTER ROLE grafana_reader PASSWORD '${GRAFANA_DB_PASSWORD}';
EOSQL
