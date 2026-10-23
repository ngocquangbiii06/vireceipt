import json
import os
import subprocess
import sys

import pytest

from vireceipt.eval.io import GoldRecord


@pytest.fixture
def records(receipt):
    stores = [
        ("a", "own"),
        ("a", "own"),
        ("b", "own"),
        ("b", "mcocr"),
        ("c", "own"),
        ("d", "own"),
        ("d", "own"),
        ("e", "mcocr"),
        ("f", "own"),
        ("g", "own"),
    ]
    return [
        GoldRecord(f"r{i:04}", store, receipt, source=source)
        for i, (store, source) in enumerate(stores, start=1)
    ]


def test_groups_are_disjoint_complete_and_test_has_only_own_stores(records):
    from vireceipt.split import split_by_store

    groups = split_by_store(records, test_n=3, val_frac=0.2, seed=0)
    stores = {name: {r.store_id for r in rows} for name, rows in groups.items()}
    assert not stores["test"] & (stores["train"] | stores["val"])
    assert not stores["train"] & stores["val"]
    assert len(groups["test"]) >= 3
    assert len(groups["val"]) >= 0.2 * (10 - len(groups["test"]))
    assert {r.source for r in groups["test"]} == {"own"}
    assert not stores["test"] & {"b", "e"}
    assert sorted(r.id for rows in groups.values() for r in rows) == sorted(r.id for r in records)


def test_seed_controls_membership_independent_of_input_order(records):
    from vireceipt.split import split_by_store

    def membership(rows, seed):
        return {
            name: {r.id for r in group}
            for name, group in split_by_store(rows, test_n=3, val_frac=0.2, seed=seed).items()
        }

    assert membership(records, 0) == membership(list(reversed(records)), 0)
    assert membership(records, 0) != membership(records, 1)


@pytest.mark.parametrize("test_n,val_frac", [(-1, 0.2), (0, -0.1), (0, 1.1), (0, float("nan"))])
def test_invalid_sizes_are_rejected(records, test_n, val_frac):
    from vireceipt.split import split_by_store

    with pytest.raises(ValueError):
        split_by_store(records, test_n=test_n, val_frac=val_frac, seed=0)


def test_insufficient_eligible_own_receipts_is_explained(records):
    from vireceipt.split import split_by_store

    with pytest.raises(ValueError, match="7"):
        split_by_store(records, test_n=100, val_frac=0.2, seed=0)
    groups = split_by_store(records, test_n=0, val_frac=0, seed=0)
    assert groups == {"train": records, "val": [], "test": []}


def test_cli_preserves_original_lines_and_respects_frozen_test(
    records, tmp_path, monkeypatch, capsys
):
    from vireceipt import split

    lines = [
        json.dumps(
            dict(
                id=r.id,
                store_id=r.store_id,
                source=r.source,
                receipt=r.receipt,
                notes="giữ nguyên chữ và khoảng trắng",
            ),
            ensure_ascii=False,
            separators=(", ", " : "),
        ).encode()
        + (b"\r\n" if i < 9 else b"")
        for i, r in enumerate(records)
    ]
    labels = tmp_path / "all.jsonl"
    labels.write_bytes(b"\n" + b"".join(lines))
    output = tmp_path / "labels"
    output.mkdir()
    target = output / "test.jsonl"
    target.write_bytes(b"frozen sentinel")
    lock = tmp_path / "test.sha256"
    lock.touch()
    monkeypatch.setattr(split, "DEFAULT_LOCK", lock)
    args = [str(labels), "--out-dir", str(output), "--test-n", "3", "--seed", "0"]
    assert split.main(args) == 1
    assert "guide" in capsys.readouterr().err
    assert target.read_bytes() == b"frozen sentinel"
    assert not (output / "train.jsonl").exists()
    assert split.main([*args, "--force"]) == 0
    summary = capsys.readouterr().out
    assert all(name in summary for name in ("train", "val", "test", "own", "mcocr"))
    groups = split.split_by_store(records, test_n=3, val_frac=0.15, seed=0)
    for name, rows in groups.items():
        ids = {r.id for r in rows}
        assert (output / f"{name}.jsonl").read_bytes() == b"".join(
            line for r, line in zip(records, lines, strict=True) if r.id in ids
        )


def test_cli_help_works_with_windows_output_encoding():
    result = subprocess.run(
        [sys.executable, "-m", "vireceipt.split", "--help"],
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert b"--test-n" in result.stdout
