#!/bin/bash
# Runs ON THE SERVER, called by the GitHub Actions deploy workflow (or by hand) after the code
# has been moved to the commit that passed CI:
#
#   cd /opt/well-data-platform && bash deploy/remote-deploy.sh
#
# 1. backup before changing anything (if the database is already running)
# 2. apply new database migrations
# 3. rebuild and restart the containers that changed
# 4. health check: Grafana answers and fresh telemetry is arriving -> otherwise exit 1 (deploy fails)
set -euo pipefail

PROFILE="${DEPLOY_PROFILE:-https}"
DC="docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile $PROFILE"
export DC

echo "deploying commit $(git rev-parse --short HEAD): $(git log -1 --format=%s)"

if [ -n "$($DC ps -q db 2>/dev/null)" ]; then
    echo "--- backup before deploy"
    bash deploy/backup.sh
fi

echo "--- start database and apply migrations"
$DC up -d db
$DC run --rm migrate

echo "--- build and restart services"
$DC up -d --build --remove-orphans
docker image prune -f > /dev/null

echo "--- health check"
for attempt in $(seq 1 30); do
    grafana_ok="$($DC exec -T grafana wget -qO- http://localhost:3000/api/health 2>/dev/null | grep -c '"database": *"ok"' || true)"
    fresh="$(echo "SELECT count(*) FROM core.readings WHERE time > now() - interval '2 minutes'" \
             | $DC exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA' 2>/dev/null || echo 0)"
    if [ "$grafana_ok" -ge 1 ] && [ "${fresh:-0}" -gt 0 ]; then
        echo "healthy: Grafana up, $fresh readings in the last 2 minutes"
        $DC ps
        exit 0
    fi
    echo "waiting for services ($attempt/30)..."
    sleep 10
done

echo "DEPLOY FAILED: services not healthy after 5 minutes" >&2
$DC ps >&2
$DC logs --tail 50 >&2
exit 1
