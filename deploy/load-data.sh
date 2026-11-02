#!/bin/bash
# On the server, as the deploy user: download and load the real public data, then prove that
# backups work (backup + restore into a scratch database).
#   bash deploy/load-data.sh                 # Volve + 10 North Sea wells (~55 MB)
#   bash deploy/load-data.sh north-sea-all   # all 118 wells (~620 MB, ~3 GB of database)
# Safe to run again: downloads resume, already-loaded files are skipped.
set -euo pipefail
cd /opt/well-data-platform
SET="${1:-north-sea}"
DC=(docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml)

mkdir -p data
echo "==> building the loader images"
"${DC[@]}" --profile tools build
echo "==> database migrations"
"${DC[@]}" run --rm migrate

echo "==> downloading '$SET' (verified, resumable)"
for i in 1 2 3 4 5; do
    if "${DC[@]}" run --rm fetch "$SET"; then break; fi
    if [ "$i" = 5 ]; then echo "download failed 5 times: check the internet, then run this script again" >&2; exit 1; fi
    echo "download interrupted, retrying in 15 s ($i/5)"
    sleep 15
done

echo "==> loading"
"${DC[@]}" run --rm load-all

echo "==> backup, then restore test"
bash deploy/backup.sh
bash deploy/restore-test.sh
echo
echo "Done. Open the North Sea Wells and Field Production dashboards."
