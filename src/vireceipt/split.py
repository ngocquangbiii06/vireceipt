"""Split labels by store while preserving the original JSONL bytes."""

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

from vireceipt.eval.io import DataError, GoldRecord, load_gold
from vireceipt.eval.lock import DEFAULT_LOCK


def split_by_store(
    records: list[GoldRecord], *, test_n: int, val_frac: float, seed: int
) -> dict[str, list[GoldRecord]]:
    """Choose whole stores deterministically; only entirely own stores enter test."""
    if test_n < 0 or not 0 <= val_frac <= 1:
        raise ValueError("test_n phải không âm và val_frac phải trong [0, 1].")
    stores: dict[str, list[GoldRecord]] = {}
    for record in records:
        stores.setdefault(record.store_id, []).append(record)
    candidates = sorted(s for s, rows in stores.items() if all(r.source == "own" for r in rows))
    available = sum(len(stores[s]) for s in candidates)
    if available < test_n:
        raise ValueError(
            f"Chỉ có {available} hóa đơn tự chụp ở cửa hàng đủ điều kiện; cần {test_n}."
        )
    rng = random.Random(seed)
    rng.shuffle(candidates)
    test_stores, count = set(), 0
    for store in candidates:
        if count >= test_n:
            break
        test_stores.add(store)
        count += len(stores[store])
    remaining = sorted(set(stores) - test_stores)
    rng.shuffle(remaining)
    target = val_frac * sum(len(stores[s]) for s in remaining)
    val_stores, count = set(), 0
    for store in remaining:
        if count >= target:
            break
        val_stores.add(store)
        count += len(stores[store])
    groups: dict[str, list[GoldRecord]] = {"train": [], "val": [], "test": []}
    for record in records:
        name = (
            "test"
            if record.store_id in test_stores
            else "val"
            if record.store_id in val_stores
            else "train"
        )
        groups[name].append(record)
    return groups


def main(argv: list[str] | None = None) -> int:
    """Write split files and print record, store and source counts."""
    parser = argparse.ArgumentParser(description="Split receipt labels by store.")
    parser.add_argument("labels")
    parser.add_argument("--out-dir", type=Path, default=Path("data/labels"))
    parser.add_argument("--test-n", type=int, default=100)
    parser.add_argument("--val-frac", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if (args.out_dir / "test.jsonl").exists() and DEFAULT_LOCK.exists() and not args.force:
        print(
            "error: Tập test đã khóa; dùng --force thì phải đóng băng lại và ghi lý do vào guide.",
            file=sys.stderr,
        )
        return 1
    try:
        records = load_gold(args.labels)
        groups = split_by_store(records, test_n=args.test_n, val_frac=args.val_frac, seed=args.seed)
        lines = [
            line
            for line in Path(args.labels).read_bytes().splitlines(keepends=True)
            if line.decode("utf-8").strip()
        ]
        raw = dict(zip((r.id for r in records), lines, strict=True))
        args.out_dir.mkdir(parents=True, exist_ok=True)
        print("split  receipts  stores  source")
        for name, rows in groups.items():
            (args.out_dir / f"{name}.jsonl").write_bytes(b"".join(raw[r.id] for r in rows))
            sources = ", ".join(
                f"{source}={n}" for source, n in sorted(Counter(r.source for r in rows).items())
            )
            print(f"{name}  {len(rows)}  {len({r.store_id for r in rows})}  {sources or '-'}")
    except (DataError, ValueError, OSError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
