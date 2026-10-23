import json
from datetime import date

import pytest

TODAY = date(2026, 10, 23)


@pytest.fixture
def correction_input(tmp_path, receipt):
    from vireceipt.eval.io import Prediction
    from vireceipt.review_queue import ReviewItem

    image = tmp_path / "images/a.png"
    image.parent.mkdir()
    image.write_bytes(b"synthetic image")
    item = ReviewItem("r0001", image, Prediction("r0001", None))
    metadata = dict(store_id="demo", source="own", quality=["good"], today=TODAY)
    return tmp_path, item, receipt, metadata


def test_save_upserts_correction_without_repairing_printed_math(correction_input):
    from dataclasses import replace

    from vireceipt.review_store import load_corrections, save_correction

    root, item, receipt, metadata = correction_input
    assert load_corrections(root) == {}
    receipt["total"] = 1
    report = save_correction(root, item, json.dumps(receipt), **metadata)
    assert "total" in {issue.code for issue in report.issues}
    assert not report.grounding.checked
    save_correction(root, replace(item, id="r0002"), json.dumps(receipt), **metadata)
    save_correction(root, item, json.dumps(receipt), notes="đã đối chiếu ảnh", **metadata)
    saved = load_corrections(root)
    assert list(saved) == ["r0001", "r0002"]
    assert saved["r0001"]["receipt"] == receipt
    assert saved["r0001"]["image"] == "images/a.png"
    assert saved["r0001"]["notes"] == "đã đối chiếu ảnh"
    assert item.prediction.receipt is None
    assert not (root / "labels").exists()


@pytest.mark.parametrize(
    "scenario", ["json", "schema", "nan", "surrogate", "store", "source", "quality"]
)
def test_bad_correction_does_not_create_or_replace_file(correction_input, scenario):
    from vireceipt.review_store import save_correction

    root, item, receipt, metadata = correction_input
    text = json.dumps(receipt)
    if scenario == "json":
        text = "{bad"
    elif scenario == "schema":
        text = "null"
    elif scenario == "nan":
        receipt["items"][0]["quantity"] = float("nan")
        text = json.dumps(receipt)
    elif scenario == "surrogate":
        receipt["seller"]["name"] = "\ud800"
        text = json.dumps(receipt)
    else:
        metadata[{"store": "store_id", "source": "source", "quality": "quality"}[scenario]] = (
            [] if scenario == "quality" else ""
        )
    with pytest.raises(ValueError):
        save_correction(root, item, text, **metadata)
    assert not (root / "review/corrections.jsonl").exists()


def test_atomic_write_failure_preserves_existing_corrections(correction_input, monkeypatch):
    from vireceipt import review_store
    from vireceipt.review_store import save_correction

    root, item, receipt, metadata = correction_input
    save_correction(root, item, json.dumps(receipt), **metadata)
    path = root / "review/corrections.jsonl"
    before = path.read_bytes()

    def fail_replace(*args):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(review_store.os, "replace", fail_replace)
    with pytest.raises(OSError):
        save_correction(root, item, json.dumps(receipt), notes="changed", **metadata)
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


def test_corrupt_existing_corrections_are_not_overwritten(correction_input):
    from vireceipt.review_store import save_correction

    root, item, receipt, metadata = correction_input
    path = root / "review/corrections.jsonl"
    path.parent.mkdir()
    path.write_text('{"id":"r0001"}\n', encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        save_correction(root, item, json.dumps(receipt), **metadata)
    assert path.read_bytes() == before


def test_symlink_output_is_rejected_before_access(correction_input):
    from vireceipt.review_store import load_corrections

    root, _, _, _ = correction_input
    target = root / "labels"
    target.mkdir()
    try:
        (root / "review").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks unavailable on this host")
    with pytest.raises(ValueError):
        load_corrections(root)


@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
def test_unicode_line_separators_survive_load_and_later_upsert(correction_input, separator):
    from vireceipt.review_store import load_corrections, save_correction

    root, item, receipt, metadata = correction_input
    notes = "line A" + separator + "line B"
    save_correction(root, item, json.dumps(receipt), notes=notes, **metadata)
    assert load_corrections(root)[item.id]["notes"] == notes
    save_correction(root, item, json.dumps(receipt), notes=notes + " updated", **metadata)
    assert load_corrections(root)[item.id]["notes"] == notes + " updated"
