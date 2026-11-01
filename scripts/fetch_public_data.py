"""Download real public datasets into data/, next to (never instead of) the synthetic samples.

Sets (each includes the previous ones):
  core          Volve production + 2 well logs                       ~5 MB
  north-sea     + 10 FORCE 2020 wells across the Norwegian North Sea  ~55 MB
  north-sea-all + the other 108 FORCE 2020 wells (118 in total)       ~620 MB

  docker compose run --rm fetch                  (core)
  docker compose run --rm fetch north-sea
  python scripts/fetch_public_data.py data north-sea-all

- Downloads are pinned to exact commits, so everyone gets the same bytes.
- Every file is verified (SHA-256, or the Git object id for files mirrored on GitHub);
  a mismatch is reported and the file is not kept.
- Interrupted downloads resume where they stopped, with retries (slow connections welcome).
- data/<folder>/SOURCES.json records licence and origin; the loaders copy it into core.load_runs.
- The data itself is never committed to Git (data/ is in .gitignore).
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MANIFEST = Path(__file__).with_name("public_sources.json")
SETS = ["core", "north-sea", "north-sea-all"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(path: Path) -> str:
    """The id Git gives a file: sha1 of 'blob <size>\\0' + content. Lets us verify against `git ls-tree`."""
    h = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verified(path: Path, src: dict) -> bool:
    if not path.exists():
        return False
    if "sha256" in src:
        return sha256(path) == src["sha256"]
    return path.stat().st_size == src["bytes"] and git_blob_sha1(path) == src["git_blob_sha1"]


def download(url: str, dest: Path, attempts: int = 5) -> None:
    """Download to <dest>.part, resuming a partial file if one exists, then rename."""
    part = dest.with_name(dest.name + ".part")
    for attempt in range(1, attempts + 1):
        have = part.stat().st_size if part.exists() else 0
        request = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                resumed = have and response.status == 206
                with part.open("ab" if resumed else "wb") as out:
                    while chunk := response.read(1 << 16):
                        out.write(chunk)
            part.replace(dest)
            return
        except urllib.error.HTTPError as e:
            if e.code == 416:                     # we already have every byte
                part.replace(dest)
                return
            error = e
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            error = e
        wait = 5 * attempt
        print(f"         attempt {attempt}/{attempts} interrupted ({error}); resuming in {wait}s", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"gave up after {attempts} attempts")


def main(data_dir: str, wanted: str) -> int:
    if wanted not in SETS:
        print(f"unknown set '{wanted}', choose one of: {', '.join(SETS)}")
        return 2
    included = SETS[: SETS.index(wanted) + 1]
    sources = [s for s in json.loads(MANIFEST.read_text(encoding="utf-8")) if s["set"] in included]
    total_mb = sum(s.get("bytes", 0) for s in sources) / 1e6
    print(f"set '{wanted}': {len(sources)} files" + (f" (~{total_mb:.0f} MB of well logs)" if total_mb else ""))

    root = Path(data_dir)
    failures = 0
    for n, src in enumerate(sources, 1):
        folder = root / src["folder"]
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / src["file"]
        tag = f"[{n:3}/{len(sources)}]"

        if verified(dest, src):
            print(f"{tag} ok        {src['file']} (already present, verified)")
        else:
            print(f"{tag} download  {src['file']} ...", flush=True)
            try:
                download(src["url"], dest)
            except Exception as e:
                print(f"{tag} FAILED    {src['file']}: {e}")
                failures += 1
                continue
            if not verified(dest, src):
                print(f"{tag} FAILED    {src['file']}: fingerprint mismatch, file removed")
                dest.unlink()
                failures += 1
                continue
            print(f"{tag} ok        {src['file']} ({dest.stat().st_size / 1e6:.1f} MB, verified)")

        manifest = folder / "SOURCES.json"
        entries = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
        entries[src["file"]] = {k: src[k] for k in ("licence", "attribution", "description") if k in src}
        entries[src["file"]]["source_url"] = src["mirror"]
        manifest.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nAttribution:")
    for line in sorted({s["attribution"] for s in sources}):
        print(f"  - {line}")
    if failures:
        print(f"\n{failures} file(s) failed. Run the same command again: finished files are skipped "
              f"and partial downloads resume.")
    return 1 if failures else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main(args[0] if args else "/data", args[1] if len(args) > 1 else "core"))
