import json

import pytest

from vireceipt.eval import cli, lock
from vireceipt.eval.io import DataError


def _reformatted_copy(src, dst):
    """Same labels, different key order and spacing."""
    rows = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines()]
    dst.write_text(
        "\n".join(json.dumps(dict(reversed(r.items())), indent=None) for r in reversed(rows))
        + "\n",
        encoding="utf-8",
    )


def test_hash_ignores_formatting_but_not_values(gold_path, tmp_path):
    digest, n = lock.canonical_hash(gold_path)
    assert n == 3
    copy = tmp_path / "copy.jsonl"
    _reformatted_copy(gold_path, copy)
    assert lock.canonical_hash(copy)[0] == digest

    edited = copy.read_text(encoding="utf-8").replace("120000", "121000")
    copy.write_text(edited, encoding="utf-8")
    assert lock.canonical_hash(copy)[0] != digest


def test_check_lock_detects_changes(gold_path, tmp_path):
    labels = tmp_path / "test.jsonl"
    labels.write_text(gold_path.read_text(encoding="utf-8"), encoding="utf-8")
    lock_file = tmp_path / "locks" / "test.sha256"
    lock.write_lock(labels, lock_file)
    assert lock.check_lock(labels, lock_file)["n"] == 3

    labels.write_text(
        labels.read_text(encoding="utf-8").replace("08:05", "08:06"), encoding="utf-8"
    )
    with pytest.raises(DataError, match="changed since it was frozen"):
        lock.check_lock(labels, lock_file)


def _eval(gold, pred, out, *extra):
    return cli.main(["--gold", str(gold), "--pred", str(pred), "--run-name", "demo",
                     "--out", str(out), *extra])  # fmt: skip


def test_val_run_writes_json_and_markdown(gold_path, pred_path, tmp_path):
    assert _eval(gold_path, pred_path, tmp_path, "--split", "val", "--model", "fixture") == 0
    (report,) = tmp_path.glob("*-demo-val.json")
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["summary"]["all_correct"] == 1
    assert data["meta"]["model"] == "fixture" and "commit" in data["meta"]["git"]
    md = report.with_suffix(".md").read_text(encoding="utf-8")
    assert "All fields and items correct: 1/3" in md


def test_test_split_is_run_once(gold_path, pred_path, tmp_path, capsys):
    out = tmp_path / "results"
    lock_file = tmp_path / "test.sha256"
    args = ("--split", "test", "--lock", str(lock_file))

    assert _eval(gold_path, pred_path, out, *args) == 1
    assert "--final" in capsys.readouterr().err

    assert _eval(gold_path, pred_path, out, *args, "--final") == 1
    assert "vireceipt-freeze" in capsys.readouterr().err

    lock.write_lock(gold_path, lock_file)
    assert _eval(gold_path, pred_path, out, *args, "--final") == 0
    assert _eval(gold_path, pred_path, out, *args, "--final") == 1
    assert "--rerun-reason" in capsys.readouterr().err

    assert _eval(gold_path, pred_path, out, *args, "--final", "--rerun-reason", "fixed label") == 0
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in out.glob("*-test.json")]
    assert len(reports) == 2  # the first final report was not overwritten
    assert sorted(str(r["meta"]["rerun_reason"]) for r in reports) == ["None", "fixed label"]


def test_freeze_cli(gold_path, tmp_path, capsys):
    lock_file = tmp_path / "test.sha256"
    assert lock.main([str(gold_path), "--lock", str(lock_file)]) == 0
    assert lock.main([str(gold_path), "--lock", str(lock_file), "--check"]) == 0
    assert "OK" in capsys.readouterr().out
