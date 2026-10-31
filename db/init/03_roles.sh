#!/bin/bash
# Sets the passwords of the two application roles from environment variables.
# Runs once, the first time the Postgres container starts.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    ALTER ROLE ingest_writer  PASSWORD '${INGEST_PASSWORD}';
    ALTER ROLE grafana_reader PASSWORD '${GRAFANA_DB_PASSWORD}';
EOSQL
