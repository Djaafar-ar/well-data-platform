"""Load every data file found in the given folders. Safe to run as often as you like:
files already loaded are skipped (fingerprint), so only new or changed files are processed.

  .csv / .xlsx -> production loader
  .las         -> well-log loader

Usage:  python load_all.py /fixtures /data
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import load_las
import load_production

log = logging.getLogger("load_all")


def main(folders: list[str]) -> None:
    files = sorted(p for f in folders for p in Path(f).rglob("*") if p.is_file())
    results = {"succeeded": 0, "skipped": 0, "failed": 0, "ignored": 0}
    for path in files:
        suffix = path.suffix.lower()
        try:
            if suffix in (".csv", ".xlsx", ".xls"):
                results[load_production.run(path)] += 1
            elif suffix == ".las":
                results[load_las.run(path)] += 1
            else:
                results["ignored"] += 1
        except Exception as e:                       # one bad file must not stop the others
            log.error("%s FAILED: %s", path.name, e)
            results["failed"] += 1
    log.info("done: %s", ", ".join(f"{k} {v}" for k, v in results.items()))
    sys.exit(1 if results["failed"] else 0)


if __name__ == "__main__":
    main(sys.argv[1:] or ["/fixtures", "/data"])
