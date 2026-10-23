"""Freeze a labels file: commit a hash of its canonical content so later changes are detected."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vireceipt.eval.io import DataError, load_gold

DEFAULT_LOCK = Path("locks/test.sha256")


def canonical_hash(labels_path: str | Path) -> tuple[str, int]:
    """SHA-256 of the labels sorted by id and dumped canonically, plus the record count.

    Key order, whitespace and line endings do not change the hash; any label value does.
    """
    records = sorted(load_gold(labels_path), key=lambda r: r.id)
    h = hashlib.sha256()
    for r in records:
        line = {
            "id": r.id,
            "store_id": r.store_id,
            "quality": list(r.quality),
            "receipt": r.receipt,
        }
        h.update(
            json.dumps(line, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        )
        h.update(b"\n")
    return h.hexdigest(), len(records)


def write_lock(labels_path: str | Path, lock_path: str | Path = DEFAULT_LOCK) -> dict[str, Any]:
    """Hash `labels_path` and write the lock file. Returns the lock content."""
    digest, n = canonical_hash(labels_path)
    lock = {
        "sha256": digest,
        "n": n,
        "labels": Path(labels_path).as_posix(),
        "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return lock


def check_lock(labels_path: str | Path, lock_path: str | Path = DEFAULT_LOCK) -> dict[str, Any]:
    """Return the lock if `labels_path` still matches it; raise DataError otherwise."""
    lock_path = Path(lock_path)
    if not lock_path.exists():
        raise DataError(f"no lock at {lock_path}; run vireceipt-freeze first")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    digest, n = canonical_hash(labels_path)
    if digest != lock["sha256"]:
        raise DataError(
            f"{labels_path} changed since it was frozen on {lock['frozen_at']} "
            f"({n} records now, {lock['n']} then). Re-freeze and record why in the labeling guide."
        )
    return lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze or check a labels file (the test set).")
    parser.add_argument("labels", help="labels file, e.g. data/labels/test.jsonl")
    parser.add_argument("--lock", default=str(DEFAULT_LOCK), help="lock file to write or check")
    parser.add_argument("--check", action="store_true", help="only verify the existing lock")
    args = parser.parse_args(argv)
    try:
        if args.check:
            lock = check_lock(args.labels, args.lock)
            print(f"OK: {args.labels} matches {args.lock} ({lock['n']} records)")
        else:
            lock = write_lock(args.labels, args.lock)
            print(f"Frozen {lock['n']} records -> {args.lock} (sha256 {lock['sha256'][:12]}...)")
    except DataError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
