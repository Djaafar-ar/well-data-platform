"""Well-log loader: LAS file -> catalog (core.well_logs, core.log_curves) + samples (core.log_samples).

What it does:
  - reads the LAS header and curves (lasio), converts depths to metres
  - maps vendor mnemonics (GR, GAMN, GSGR...) to standard families via core.curve_families
  - drops nulls and physically impossible samples (or unknown lithology codes) and counts them per curve
  - adds the well to core.wellbores with its aliases and, when the log carries X/Y, its map position
  - is idempotent: the same file is skipped; --force replaces the earlier copy of that file

Usage:
  python load_las.py /data/logs/15-9-19_SR_COMP.LAS [--force]
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path

import lasio
from psycopg.types.json import Jsonb

from common import connect, fail_run, finish_run, sha256, start_run, upsert_wellbore
from las_rules import (SUMMARY_ONLY_FAMILIES, check_depths, classify, depth_factor, looks_like_utm,
                       utm31n_ed50_to_latlon, valid_range, wellbore_name)

log = logging.getLogger("well_log")
logging.getLogger("lasio").setLevel(logging.WARNING)


def header_dict(las) -> dict:
    out = {}
    for section in ("Version", "Well", "Parameter"):
        items = las.sections.get(section) or []
        out[section] = {i.mnemonic: {"value": str(i.value), "unit": i.unit, "descr": i.descr} for i in items}
    return out


def well_value(las, *mnemonics: str) -> str | None:
    for m in mnemonics:
        if m in las.well:
            v = str(las.well[m].value).strip()
            if v:
                return v
    return None


def first_valid(values, null_value) -> float | None:
    for v in values:
        v = float(v)
        if not math.isnan(v) and (null_value is None or not math.isclose(v, null_value, abs_tol=1e-6)):
            return v
    return None


def surface_location(las, null_value):
    """First valid X/Y pair from position curves (FORCE 2020 style X_LOC / Y_LOC), if any."""
    curves = {c.mnemonic.strip().upper(): c for c in las.curves}
    if "X_LOC" not in curves or "Y_LOC" not in curves:
        return None
    for x, y in zip(curves["X_LOC"].data, curves["Y_LOC"].data):
        x, y = float(x), float(y)
        if any(math.isnan(v) or (null_value is not None and math.isclose(v, null_value, abs_tol=1e-6))
               for v in (x, y)):
            continue
        return (x, y) if looks_like_utm(x, y) else None
    return None


def run(path: Path, force: bool = False) -> str:
    conn = connect()
    fingerprint = sha256(path)
    run_id, previous = start_run(conn, "well_log", path, fingerprint, force)
    if previous and not force:
        log.info("%s: already loaded in run %s; nothing to do (use --force to reload)", path.name, previous)
        return "skipped"

    try:
        las = lasio.read(str(path), ignore_header_errors=True)
        raw_well, uwi = well_value(las, "WELL"), well_value(las, "UWI")
        wellbore = wellbore_name(raw_well, uwi)
        if not wellbore:
            raise ValueError("LAS header has no WELL name: cannot tell which well this log belongs to")

        factor = depth_factor(las.index_unit or las.curves[0].unit)
        depths = [float(d) * factor for d in las.index]
        problem = check_depths(depths)
        if problem:
            raise ValueError(problem)

        null_value = las.well["NULL"].value if "NULL" in las.well else None
        null_value = float(null_value) if null_value not in (None, "") else None
        location = surface_location(las, null_value)

        with conn.cursor() as cur:
            families = dict(cur.execute("SELECT mnemonic, family FROM core.curve_families").fetchall())
            lithology_codes = {r[0] for r in cur.execute("SELECT code FROM core.lithology_codes").fetchall()}

            upsert_wellbore(cur, wellbore,
                            field=well_value(las, "FLD"), operator=well_value(las, "COMP"),
                            country=well_value(las, "CTRY", "NATI"),
                            aliases=[raw_well, well_value(las, "WBN"), uwi, well_value(las, "APIN"),
                                     well_value(las, "API")],
                            source=path.name)
            if location:
                lat, lon = utm31n_ed50_to_latlon(*location)
                cur.execute("UPDATE core.wellbores SET surface_x = %s, surface_y = %s, crs = %s, "
                            "latitude = %s, longitude = %s WHERE wellbore = %s AND latitude IS NULL",
                            (location[0], location[1], "ED50 / UTM zone 31N (EPSG:23031, assumed)",
                             lat, lon, wellbore))

            if force:      # replace the earlier copy of this exact file, keep everything else
                cur.execute("DELETE FROM core.well_logs WHERE file_sha256 = %s", (fingerprint,))

            cur.execute(
                "INSERT INTO core.well_logs (run_id, wellbore, source_name, file_sha256, depth_unit, top_depth_m, "
                "bottom_depth_m, step_m, n_depths, null_value, service_company, log_date, header) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING log_id",
                (run_id, wellbore, path.name, fingerprint, las.index_unit or las.curves[0].unit,
                 min(depths), max(depths), abs(depths[1] - depths[0]), len(depths), null_value,
                 well_value(las, "SRVC"), well_value(las, "DATE"),
                 Jsonb(header_dict(las), dumps=lambda o: json.dumps(o, default=str))))
            log_id = cur.fetchone()[0]

            total_valid = total_out = curves_unmapped = 0
            for curve in las.curves[1:]:                     # curve 0 is the depth index
                mnemonic = curve.mnemonic.strip().upper()
                family = families.get(mnemonic)
                curves_unmapped += family is None
                rng = valid_range(family, curve.unit)
                codes = lithology_codes if family == "Lithology (interpreted)" else None
                keep_samples = family not in SUMMARY_ONLY_FAMILIES
                counts = {"valid": 0, "null": 0, "out_of_range": 0}
                samples = []
                for depth, value in zip(depths, curve.data):
                    value = float(value) if value is not None else None
                    status = classify(value, null_value, rng, codes)
                    counts[status] += 1
                    if status == "valid":
                        samples.append((log_id, mnemonic, round(depth, 4), value))
                values = [s[3] for s in samples]
                cur.execute(
                    "INSERT INTO core.log_curves (log_id, mnemonic, unit, description, family, n_valid, n_null, "
                    "n_out_of_range, min_value, max_value, mean_value) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (log_id, mnemonic, curve.unit or None, curve.descr or None, family,
                     counts["valid"], counts["null"], counts["out_of_range"],
                     min(values) if values else None, max(values) if values else None,
                     math.fsum(values) / len(values) if values else None))
                if keep_samples:
                    with cur.copy("COPY core.log_samples (log_id, mnemonic, depth_m, value) FROM STDIN") as copy:
                        for s in samples:
                            copy.write_row(s)
                    total_valid += counts["valid"]
                total_out += counts["out_of_range"]
                log.debug("  %-6s %-8s %-22s valid %6d  null %6d  out of range %4d", mnemonic, curve.unit or "",
                          family or "UNMAPPED", counts["valid"], counts["null"], counts["out_of_range"])
                if counts["out_of_range"] or family is None:
                    log.info("  %-34s %-24s out of range %5d%s", mnemonic, family or "UNMAPPED",
                             counts["out_of_range"], "" if keep_samples else "  (summary only)")

            finish_run(conn, run_id, len(depths) * (len(las.curves) - 1), total_valid, total_out,
                       curves_unmapped, message=f"log_id {log_id}")
        conn.commit()
    except BaseException as e:
        fail_run(conn, run_id, e)
        raise

    where = f", at {lat:.3f}N {lon:.3f}E" if location else ""
    log.info("%s run %s: well %s%s, %.0f-%.0f m, %d curves, %d samples stored, %d out of range, %d unmapped",
             path.name, run_id, wellbore, where, min(depths), max(depths), len(las.curves) - 1,
             total_valid, total_out, curves_unmapped)
    return "succeeded"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--force", action="store_true", help="replace the earlier copy of this exact file")
    args = parser.parse_args()
    if not args.file.exists():
        sys.exit(f"file not found: {args.file}")
    run(args.file, args.force)


if __name__ == "__main__":
    main()
