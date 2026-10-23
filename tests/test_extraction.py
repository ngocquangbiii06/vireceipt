import math
from pathlib import Path

import pytest

from vireceipt.eval.io import Prediction, load_predictions


def test_runner_preserves_outputs_and_continues_after_backend_failure(receipt, monkeypatch):
    from vireceipt import extraction

    clock = iter([0, 0.012, 1, 1.03, 2, 2.04])
    monkeypatch.setattr(extraction, "perf_counter", lambda: next(clock))

    def backend(image):
        if image.name == "broken.png":
            raise RuntimeError("private connection detail must not appear")
        return extraction.ExtractionResult(receipt if image.name == "valid.png" else {"total": 1})

    predictions = extraction.extract_images(
        {"r0001": Path("valid.png"), "r0002": Path("invalid.png"), "r0003": Path("broken.png")},
        backend,
    )
    assert [p.id for p in predictions] == ["r0001", "r0002", "r0003"]
    assert predictions[0].receipt == receipt and predictions[0].extra == {"schema_valid": True}
    assert predictions[1].receipt == {"total": 1} and predictions[1].extra == {
        "schema_valid": False
    }
    assert predictions[2].receipt is None and predictions[2].extra["error"] == "extractor_failed"
    assert "private" not in repr(predictions)
    assert [p.latency_ms for p in predictions] == pytest.approx([12, 30, 40])
    assert all(
        p.decision == "review" and p.confidence is None and p.cost_usd is None for p in predictions
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("confidence", -0.1),
        ("confidence", 1.1),
        ("confidence", True),
        ("confidence", math.nan),
        ("cost_usd", -1),
        ("cost_usd", math.inf),
        pytest.param("cost_usd", 10**1000, id="huge-cost"),
        pytest.param("confidence", 10**1000, id="huge-confidence"),
    ],
)
def test_invalid_backend_metadata_is_an_explicit_failure(receipt, field, value):
    from vireceipt.extraction import ExtractionResult, extract_images

    prediction, following = extract_images(
        {"r0001": Path("a.png"), "r0002": Path("b.png")},
        lambda image: ExtractionResult(
            receipt, **({field: value} if image.name == "a.png" else {})
        ),
    )
    assert prediction.receipt is None and prediction.extra["error"] == "invalid_result"
    assert following.receipt == receipt and "error" not in following.extra


def test_non_json_result_fails_but_supplied_confidence_and_cost_are_kept(receipt):
    from vireceipt.extraction import ExtractionResult, extract_images

    (bad,) = extract_images({"r0001": Path("a.png")}, lambda image: ExtractionResult({1, 2}))
    assert bad.receipt is None and bad.extra["error"] == "invalid_result"
    (good,) = extract_images(
        {"r0001": Path("a.png")},
        lambda image: ExtractionResult(receipt, confidence=0.8, cost_usd=0.001),
    )
    assert good.confidence == 0.8 and good.cost_usd == 0.001
    assert good.decision == "review"


def test_predictions_are_snapshots_if_backend_reuses_its_dictionary(receipt):
    from vireceipt.extraction import ExtractionResult, extract_images

    def backend(image):
        receipt["total"] = 10 if image.name == "a.png" else 20
        return ExtractionResult(receipt)

    results = extract_images({"r0001": Path("a.png"), "r0002": Path("b.png")}, backend)
    assert [p.receipt["total"] for p in results] == [10, 20]


def test_non_utf8_backend_output_fails_one_image_not_the_whole_write(receipt, tmp_path):
    from vireceipt.extraction import ExtractionResult, extract_images, write_predictions

    predictions = extract_images(
        {"r0001": Path("a.png"), "r0002": Path("b.png")},
        lambda image: ExtractionResult("\ud800" if image.name == "a.png" else receipt),
    )
    assert predictions[0].receipt is None and predictions[0].extra["error"] == "invalid_result"
    output = tmp_path / "pred.jsonl"
    write_predictions(predictions, output)
    assert len(load_predictions(output)) == 2
    assert load_predictions(output)[1].receipt == receipt


def test_deep_json_is_written_without_recursive_dataclass_conversion(tmp_path):
    from vireceipt.extraction import ExtractionResult, extract_images, write_predictions

    raw = 1
    for _ in range(1500):
        raw = [raw]
    predictions = extract_images({"r0001": Path("a.png")}, lambda image: ExtractionResult(raw))
    output = tmp_path / "pred.jsonl"
    write_predictions(predictions, output)
    (prediction,) = load_predictions(output)
    value = prediction.receipt
    for _ in range(1500):
        value = value[0]
    assert value == 1 and prediction.extra["schema_valid"] is False


def test_unserializable_depth_fails_one_image_and_continues(receipt):
    from vireceipt.extraction import ExtractionResult, extract_images

    raw = 1
    for _ in range(10000):
        raw = [raw]
    bad, good = extract_images(
        {"r0001": Path("a.png"), "r0002": Path("b.png")},
        lambda image: ExtractionResult(raw if image.name == "a.png" else receipt),
    )
    assert bad.receipt is None and bad.extra["error"] == "invalid_result"
    assert good.receipt == receipt


def test_writer_is_utf8_atomic_and_loadable_by_eval(receipt, tmp_path, monkeypatch):
    from vireceipt import extraction

    output = tmp_path / "predictions.jsonl"
    predictions = [Prediction("r0001", receipt, decision="review", extra={"schema_valid": True})]
    extraction.write_predictions(predictions, output)
    assert load_predictions(output) == predictions
    assert "Cửa hàng" in output.read_text(encoding="utf-8")
    before = output.read_bytes()

    def fail_replace(*args):
        raise OSError("replacement failed")

    monkeypatch.setattr(extraction.os, "replace", fail_replace)
    with pytest.raises(OSError):
        extraction.write_predictions(predictions, output)
    assert output.read_bytes() == before
    assert list(tmp_path.iterdir()) == [output]
