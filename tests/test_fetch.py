import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_public_data as f  # noqa: E402


def test_git_blob_id_matches_git(tmp_path):
    p = tmp_path / "hello.txt"
    p.write_bytes(b"hello\n")
    # `printf 'hello\n' | git hash-object --stdin` prints this id
    assert f.git_blob_sha1(p) == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_verified_rejects_wrong_size_or_content(tmp_path):
    p = tmp_path / "x.las"
    p.write_bytes(b"hello\n")
    good = {"git_blob_sha1": "ce013625030ba8dba906f756967f9e9ca394464a", "bytes": 6}
    assert f.verified(p, good)
    assert not f.verified(p, good | {"bytes": 7})
    assert not f.verified(p, good | {"git_blob_sha1": "0" * 40})


def test_manifest_is_complete_and_pinned():
    sources = json.loads(f.MANIFEST.read_text(encoding="utf-8"))
    by_set = {}
    for s in sources:
        by_set[s["set"]] = by_set.get(s["set"], 0) + 1
        assert s["set"] in f.SETS
        assert "sha256" in s or ("git_blob_sha1" in s and "bytes" in s)
        assert s["licence"] and s["attribution"]
        # pinned to a commit (40 hex chars in the URL), never to a moving branch
        assert any(len(part) == 40 and all(c in "0123456789abcdef" for c in part) for part in s["url"].split("/"))
    assert by_set == {"core": 3, "north-sea": 10, "north-sea-all": 108}
