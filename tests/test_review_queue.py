import json

import pytest


@pytest.fixture
def review_files(tmp_path, receipt):
    (tmp_path / "images").mkdir()
    for name in ("a.png", "b.png"):
        (tmp_path / "images" / name).write_bytes(b"synthetic image")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "\n".join(
            json.dumps({"id": rid, "image": f"images/{name}"})
            for rid, name in [("r0001", "a.png"), ("r0002", "b.png")]
        ),
        encoding="utf-8",
    )
    predictions = tmp_path / "pred.jsonl"
    rows = [
        {"id": "r0002", "receipt": None, "error": "extractor_failed"},
        {"id": "r0001", "receipt": receipt, "verification_issues": [{"code": "test"}]},
    ]
    predictions.write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
    return tmp_path, manifest, predictions, rows


def test_queue_joins_by_id_and_preserves_manifest_order_and_raw_output(review_files):
    from vireceipt.review_queue import load_review_queue

    root, manifest, predictions, rows = review_files
    before = predictions.read_bytes()
    queue = load_review_queue(root, manifest, predictions)
    assert [item.id for item in queue] == ["r0001", "r0002"]
    assert queue[0].image == root / "images/a.png"
    assert queue[0].prediction.receipt == rows[1]["receipt"]
    assert queue[0].prediction.extra["verification_issues"] == [{"code": "test"}]
    assert queue[1].prediction.receipt is None
    assert queue[1].prediction.extra["error"] == "extractor_failed"
    assert predictions.read_bytes() == before


@pytest.mark.parametrize("scenario", ["missing", "extra", "duplicate", "bad_id", "bad_json"])
def test_queue_rejects_mismatched_or_malformed_predictions(review_files, scenario):
    from vireceipt.review_queue import load_review_queue

    root, manifest, predictions, rows = review_files
    if scenario == "missing":
        rows.pop()
    elif scenario == "extra":
        rows.append({"id": "r9999", "receipt": None})
    elif scenario == "duplicate":
        rows.append(rows[0])
    elif scenario == "bad_id":
        rows[0]["id"] = []
    predictions.write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
    if scenario == "bad_json":
        predictions.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        load_review_queue(root, manifest, predictions)


@pytest.mark.parametrize("argument", ["manifest", "predictions"])
@pytest.mark.parametrize("location", ["outside", "labels"])
def test_queue_refuses_protected_paths_before_reading(
    review_files, monkeypatch, argument, location
):
    from pathlib import Path

    from vireceipt.review_queue import load_review_queue

    root, manifest, predictions, _ = review_files
    forbidden = root / "labels/test.jsonl" if location == "labels" else root.parent / "other.jsonl"
    original = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path != forbidden, "Protected file must not be opened"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    with pytest.raises(ValueError):
        load_review_queue(
            root,
            forbidden if argument == "manifest" else manifest,
            forbidden if argument == "predictions" else predictions,
        )


def test_queue_retains_schema_invalid_receipt(review_files):
    from vireceipt.review_queue import load_review_queue

    root, manifest, predictions, rows = review_files
    rows[1]["receipt"] = "invalid model JSON"
    predictions.write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
    assert (
        load_review_queue(root, manifest, predictions)[0].prediction.receipt == "invalid model JSON"
    )


def test_queue_cannot_use_corrections_as_original_predictions(review_files):
    from vireceipt.review_queue import load_review_queue

    root, manifest, predictions, _ = review_files
    corrections = root / "review/corrections.jsonl"
    corrections.parent.mkdir()
    corrections.write_bytes(predictions.read_bytes())
    with pytest.raises(ValueError, match="corrections"):
        load_review_queue(root, manifest, corrections)
