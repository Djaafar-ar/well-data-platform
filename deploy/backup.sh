#!/bin/bash
# Back up the database to BACKUP_DIR (default /var/backups/wells), keep KEEP_DAYS days (default 7).
# Optionally copies each backup off the server with rclone if RCLONE_REMOTE is set
# (a backup on the same disk as the database does not survive the loss of that disk).
#
#   bash deploy/backup.sh
#
# The dump is in PostgreSQL's custom format (-Fc): compressed, and restorable table by table.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/wells}"
KEEP_DAYS="${KEEP_DAYS:-7}"
DC="${DC:-docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml}"

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="$BACKUP_DIR/wells-$stamp.dump"

echo "$(date -u +%FT%TZ) backup start -> $file"
# The container's own POSTGRES_USER/POSTGRES_DB are used, so no password is needed here
$DC exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$file.part"

# A backup that cannot be read is not a backup: check the archive's table of contents
if ! $DC exec -T db pg_restore --list < "$file.part" > /dev/null; then
    echo "backup FAILED: archive is not readable" >&2
    rm -f "$file.part"
    exit 1
fi
mv "$file.part" "$file"
sha256sum "$file" > "$file.sha256"
echo "$(date -u +%FT%TZ) backup ok: $(du -h "$file" | cut -f1)"

if [ -n "${RCLONE_REMOTE:-}" ]; then
    rclone copy "$file" "$RCLONE_REMOTE" && rclone copy "$file.sha256" "$RCLONE_REMOTE"
    echo "copied off-site to $RCLONE_REMOTE"
fi

find "$BACKUP_DIR" -name 'wells-*.dump*' -mtime +"$KEEP_DAYS" -print -delete | sed 's/^/deleted old backup: /'
