"""Plumbing shared by every loader: file fingerprint, load-run bookkeeping, source metadata."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import psycopg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])


def source_metadata(path: Path) -> dict:
    """Licence and origin of a file, from the SOURCES.json written by scripts/fetch_public_data.py.

    Looks in the file's folder and its parents. Files without an entry (like the synthetic samples)
    get a default description.
    """
    for folder in [path.parent, *path.parents]:
        manifest = folder / "SOURCES.json"
        if manifest.exists():
            entries = json.loads(manifest.read_text(encoding="utf-8"))
            if path.name in entries:
                return entries[path.name]
    if "fixtures" in path.parts:
        return {"licence": "synthetic sample (MIT, this repository)", "source_url": None}
    return {"licence": None, "source_url": None}


def start_run(conn, kind: str, path: Path, fingerprint: str, force: bool) -> tuple[int, int | None]:
    """Register a load run. Returns (run_id, previous_run_id_if_this_exact_file_was_already_loaded)."""
    meta = source_metadata(path)
    with conn.cursor() as cur:
        cur.execute("SELECT run_id FROM core.load_runs WHERE file_sha256 = %s AND kind = %s "
                    "AND status = 'succeeded' ORDER BY run_id DESC LIMIT 1", (fingerprint, kind))
        previous = cur.fetchone()
        cur.execute("INSERT INTO core.load_runs (kind, source_name, file_sha256, licence, source_url) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING run_id",
                    (kind, path.name, fingerprint, meta.get("licence"), meta.get("source_url")))
        run_id = cur.fetchone()[0]
    conn.commit()
    if previous and not force:
        with conn.cursor() as cur:
            cur.execute("UPDATE core.load_runs SET status='skipped', finished_at=now(), rows_read=0, "
                        "rows_loaded=0, rows_rejected=0, rows_flagged=0, message=%s WHERE run_id=%s",
                        (f"same file already loaded in run {previous[0]}", run_id))
        conn.commit()
    return run_id, (previous[0] if previous else None)


def finish_run(conn, run_id: int, read: int, loaded: int, rejected: int, flagged: int, message: str | None = None):
    with conn.cursor() as cur:
        cur.execute("UPDATE core.load_runs SET status='succeeded', finished_at=now(), rows_read=%s, "
                    "rows_loaded=%s, rows_rejected=%s, rows_flagged=%s, message=%s WHERE run_id=%s",
                    (read, loaded, rejected, flagged, message, run_id))


def fail_run(conn, run_id: int, error: BaseException):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("UPDATE core.load_runs SET status='failed', finished_at=now(), message=%s WHERE run_id=%s",
                    (f"{type(error).__name__}: {error}"[:500], run_id))
    conn.commit()


def upsert_wellbore(cur, wellbore: str, *, field=None, operator=None, country=None,
                    aliases=(), source: str | None = None):
    """Add a wellbore to the catalog (or fill in details we did not know yet) and record its aliases."""
    cur.execute(
        "INSERT INTO core.wellbores (wellbore, field, operator, country, is_synthetic) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (wellbore) DO UPDATE SET "
        "  field    = COALESCE(core.wellbores.field, EXCLUDED.field), "
        "  operator = COALESCE(core.wellbores.operator, EXCLUDED.operator), "
        "  country  = COALESCE(core.wellbores.country, EXCLUDED.country)",
        (wellbore, field or None, operator or None, country or None, wellbore.startswith("DEMO-")))
    for alias in aliases:
        if alias and alias != wellbore:
            cur.execute("INSERT INTO core.wellbore_aliases (alias, wellbore, source) VALUES (%s, %s, %s) "
                        "ON CONFLICT (alias) DO NOTHING", (alias, wellbore, source))
