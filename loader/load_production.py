"""Batch loader: daily production file (Excel or CSV, Volve format) -> PostgreSQL.

What it guarantees:
  - every row ends up somewhere: loaded, flagged, or rejected with a reason (nothing silently lost)
  - re-running the same file changes nothing (idempotent upsert + file fingerprint)
  - every load is recorded in core.load_runs (lineage: which file, licence, when, what happened)
  - every wellbore it sees is added to the catalog (core.wellbores) with its aliases

Usage:
  python load_production.py /data/your_file.xlsx [--sheet "Daily Production Data"] [--force]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
from psycopg.types.json import Jsonb

from common import connect, fail_run, finish_run, sha256, start_run, upsert_wellbore
from production_rules import COLUMN_MAP, REQUIRED, check_row, is_missing

log = logging.getLogger("production")

# Extra source columns used for the catalog only (not stored in the production table)
CATALOG_COLUMNS = {"WELL_BORE_CODE": "wellbore_code", "NPD_FIELD_NAME": "field"}

DB_COLUMNS = ["wellbore", "prod_date", "on_stream_hrs", "avg_downhole_press", "avg_downhole_temp",
              "avg_whp", "avg_wht", "avg_choke_pct", "oil_sm3", "gas_sm3", "water_sm3",
              "water_inj_sm3", "flow_kind", "well_type", "quality_flag", "run_id"]
NUMERIC = ["on_stream_hrs", "avg_downhole_press", "avg_downhole_temp", "avg_whp", "avg_wht",
           "avg_choke_pct", "oil_sm3", "gas_sm3", "water_sm3", "water_inj_sm3"]


def read_source(path: Path, sheet: str | None) -> pd.DataFrame:
    if path.suffix.lower() in (".xlsx", ".xls"):
        if sheet is None:                     # Volve's workbook has a daily and a monthly sheet
            sheets = pd.ExcelFile(path).sheet_names
            sheet = next((s for s in sheets if "daily" in s.lower()), sheets[0])
        log.info("reading sheet '%s'", sheet)
        return pd.read_excel(path, sheet_name=sheet)
    return pd.read_csv(path)


def parse_dates(col: pd.Series) -> pd.Series:
    """Volve style first (01-Jan-15), then any other unambiguous format. Unreadable -> None."""
    parsed = pd.to_datetime(col, format="%d-%b-%y", errors="coerce")
    retry = parsed.isna() & col.notna()
    if retry.any():
        parsed[retry] = pd.to_datetime(col[retry].astype(str), format="mixed", errors="coerce")
    return pd.Series([d.date() if pd.notna(d) else None for d in parsed], index=col.index, dtype=object)


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Rename source columns to ours, convert types. Unparseable values become missing, not crashes."""
    lookup = {c.strip().upper(): c for c in df.columns}
    mapping = {**COLUMN_MAP, **CATALOG_COLUMNS}
    rename = {lookup[src]: dst for src, dst in mapping.items() if src in lookup}
    missing = REQUIRED - set(rename.values())
    if missing:
        raise SystemExit(f"source file is missing required columns for: {sorted(missing)}. "
                         f"Columns found: {list(df.columns)}")
    out = df.rename(columns=rename)[list(rename.values())].copy()
    out["prod_date"] = parse_dates(out["prod_date"])
    for col in NUMERIC:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    for col in ("wellbore", "flow_kind", "well_type", "wellbore_code", "field"):
        if col in out:
            out[col] = out[col].astype("string").str.strip()
    return out


def to_python(v):
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, float) and v != v:
        return None
    if hasattr(v, "item"):                    # numpy scalar -> plain Python
        return v.item()
    return v


def run(path: Path, sheet: str | None = None, force: bool = False) -> str:
    """Load one file. Returns 'succeeded' or 'skipped'; raises on failure."""
    conn = connect()
    run_id, previous = start_run(conn, "production", path, sha256(path), force)
    if previous and not force:
        log.info("%s: already loaded in run %s; nothing to do (use --force to reload)", path.name, previous)
        return "skipped"

    try:
        raw = read_source(path, sheet)
        df = normalise(raw)
        today = date.today()
        good, rejected, seen, flagged, wells = [], [], set(), 0, {}

        for i, row in enumerate(df.to_dict("records")):
            source_row = i + 2                 # +1 for the header line, +1 because files count from 1
            reason, flag = check_row(row, today)
            key = (row.get("wellbore"), row.get("prod_date"))
            if reason is None and key in seen:
                reason = "duplicate wellbore and date in the same file"
            if reason:
                original = {k: to_python(v) for k, v in raw.iloc[i].items()}
                rejected.append((run_id, source_row,
                                 None if is_missing(row.get("wellbore")) else str(row["wellbore"]),
                                 None if not isinstance(row.get("prod_date"), date) else row["prod_date"].isoformat(),
                                 reason, Jsonb(original, dumps=lambda o: json.dumps(o, default=str))))
                continue
            seen.add(key)
            flagged += flag is not None
            wells.setdefault(str(row["wellbore"]), (to_python(row.get("field")), to_python(row.get("wellbore_code"))))
            record = {c: to_python(row.get(c)) for c in DB_COLUMNS}
            record["quality_flag"], record["run_id"] = flag, run_id
            good.append(tuple(record[c] for c in DB_COLUMNS))

        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in DB_COLUMNS if c not in ("wellbore", "prod_date"))
        with conn.cursor() as cur:
            for wellbore, (field, code) in wells.items():          # catalog first: production rows reference it
                upsert_wellbore(cur, wellbore, field=field, aliases=[code], source=path.name)
            cur.executemany(
                f"INSERT INTO core.daily_production ({', '.join(DB_COLUMNS)}) "
                f"VALUES ({', '.join(['%s'] * len(DB_COLUMNS))}) "
                f"ON CONFLICT (wellbore, prod_date) DO UPDATE SET {updates}", good)
            cur.executemany(
                "INSERT INTO raw.production_rejected (run_id, source_row, wellbore, prod_date, reason, original) "
                "VALUES (%s, %s, %s, %s, %s, %s)", rejected)
            finish_run(conn, run_id, len(df), len(good), len(rejected), flagged)
        conn.commit()
    except BaseException as e:
        fail_run(conn, run_id, e)
        raise

    log.info("%s run %s: %d rows read, %d loaded (%d flagged), %d rejected, %d wellbores",
             path.name, run_id, len(df), len(good), flagged, len(rejected), len(wells))
    # Summarise from memory: the loader is deliberately not allowed to read the reject table.
    # Numbers are masked so the same kind of problem is counted once.
    for reason, n in Counter(re.sub(r"(?<![A-Za-z_])-?\d[\d.e+-]*", "N", r[4]) for r in rejected).most_common():
        log.info("  rejected %5d  %s", n, reason)
    return "succeeded"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--sheet", default=None)
    parser.add_argument("--force", action="store_true", help="load even if this exact file was loaded before")
    args = parser.parse_args()
    if not args.file.exists():
        sys.exit(f"file not found: {args.file}")
    run(args.file, args.sheet, args.force)


if __name__ == "__main__":
    main()
