#!/bin/bash
# First start on a server prepared by provision.sh. Run as the deploy user:
#   bash deploy/first-start.sh            # tunnel mode (VM on your PC, no open ports)
#   bash deploy/first-start.sh https      # cloud VM with Caddy (set DOMAIN in .env first)
# Safe to run again: only default 'change-me' passwords are replaced, existing ones are kept.
set -euo pipefail
cd /opt/well-data-platform

[ -f .env ] || cp .env.example .env
for k in POSTGRES INGEST GRAFANA_DB GRAFANA_ADMIN LOADER; do
    sed -i "s|^${k}_PASSWORD=change-me.*|${k}_PASSWORD=$(openssl rand -hex 16)|" .env
done
chmod 600 .env
if grep -q 'change-me' .env; then echo "a default password is still in .env" >&2; exit 1; fi
echo ".env ready: random passwords, readable only by $(whoami)"

PROFILE="${1:-tunnel}"
DC=(docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile "$PROFILE")
"${DC[@]}" up -d --build
"${DC[@]}" ps

if [ "$PROFILE" = tunnel ]; then
    url=""
    for _ in $(seq 1 30); do
        url="$("${DC[@]}" logs tunnel 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 || true)"
        [ -n "$url" ] && break
        sleep 2
    done
    echo
    echo "Public URL: ${url:-not printed yet -- run: ${DC[*]} logs tunnel}"
fi
echo "Grafana login: admin + the password shown by:  grep GRAFANA_ADMIN_PASSWORD /opt/well-data-platform/.env"
