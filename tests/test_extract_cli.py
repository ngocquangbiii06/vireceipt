import sys
from types import SimpleNamespace

import pytest

from vireceipt.eval.io import load_predictions
from vireceipt.extraction import ExtractionResult


@pytest.fixture
def inputs(tmp_path, monkeypatch, receipt):
    for name in ("a.png", "b.jpg"):
        (tmp_path / name).write_bytes(b"synthetic image placeholder")
    manifest, output = tmp_path / "images.jsonl", tmp_path / "pred.jsonl"
    manifest.write_text(
        '\n{"id":"r0001","image":"a.png"}\n{"id":"r0002","image":"b.jpg"}\n',
        encoding="utf-8",
    )
    calls = []

    def backend(image):
        calls.append(image)
        return ExtractionResult(receipt)

    monkeypatch.setitem(sys.modules, "synthetic_backend", SimpleNamespace(extract=backend))
    args = [str(manifest), "--extractor", "synthetic_backend:extract", "--out", str(output)]
    return manifest, output, calls, args


def test_cli_writes_eval_predictions_and_requires_opt_in_overwrite(inputs):
    from vireceipt.extract_cli import main

    manifest, output, calls, args = inputs
    assert main(args) == 0
    assert calls == [manifest.parent / "a.png", manifest.parent / "b.jpg"]
    predictions = load_predictions(output)
    assert [p.id for p in predictions] == ["r0001", "r0002"]
    assert all(p.decision == "review" and p.confidence is None for p in predictions)
    assert "Cửa hàng" in output.read_text(encoding="utf-8")
    before = output.read_bytes()
    assert main(args) == 1 and len(calls) == 2 and output.read_bytes() == before
    assert main([*args, "--overwrite"]) == 0 and len(calls) == 4


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "[]",
        '{"id":"r0001","image":"a.png","receipt":{}}',
        '{"id":"bad","image":"a.png"}',
        '{"id":1,"image":"a.png"}',
        '{"id":"r0001","image":"../a.png"}',
        '{"id":"r0001","image":"missing.png"}',
        '{"id":"r0001","image":"images.jsonl"}',
        '{"id":"r0001","image":"a.png"}\n{"id":"r0001","image":"b.jpg"}',
    ],
)
def test_bad_manifest_is_rejected_before_backend_runs(inputs, content):
    from vireceipt.extract_cli import main

    manifest, output, calls, args = inputs
    manifest.write_text(content, encoding="utf-8")
    assert main(args) == 1 and calls == [] and not output.exists()


@pytest.mark.parametrize("target", ["images.jsonl", "a.png"])
def test_output_cannot_replace_manifest_or_input_image(inputs, target):
    from vireceipt.extract_cli import main

    manifest, _, calls, args = inputs
    destination = manifest.parent / target
    before = destination.read_bytes()
    args[-1] = str(destination)
    assert main([*args, "--overwrite"]) == 1 and calls == []
    assert destination.read_bytes() == before


def test_backend_failure_keeps_other_images_and_returns_failure(inputs, monkeypatch):
    from vireceipt.extract_cli import main

    _, output, _, args = inputs

    def backend(image):
        if image.name == "a.png":
            raise RuntimeError("private backend detail")
        return ExtractionResult({"total": 1})

    monkeypatch.setitem(sys.modules, "synthetic_backend", SimpleNamespace(extract=backend))
    assert main(args) == 1
    failed, invalid = load_predictions(output)
    assert failed.receipt is None and failed.extra["error"] == "extractor_failed"
    assert invalid.receipt == {"total": 1} and invalid.extra["schema_valid"] is False
    assert "private" not in output.read_text(encoding="utf-8")


def test_frozen_test_label_path_is_refused_before_open(inputs, tmp_path, monkeypatch):
    from vireceipt.extract_cli import main

    _, output, calls, args = inputs
    forbidden = tmp_path / "data" / "labels" / "test.jsonl"
    original_open = type(forbidden).open

    def guarded_open(path, *positional, **kwargs):
        assert path != forbidden, "frozen test labels must never be opened"
        return original_open(path, *positional, **kwargs)

    monkeypatch.setattr(type(forbidden), "open", guarded_open)
    assert main([str(forbidden), *args[1:]]) == 1
    assert calls == [] and not output.exists()


def test_explicit_images_root_and_invalid_adapter(inputs):
    from vireceipt.extract_cli import main

    manifest, output, calls, args = inputs
    nested = manifest.parent / "manifests"
    nested.mkdir()
    relocated = nested / manifest.name
    manifest.replace(relocated)
    args[0] = str(relocated)
    assert main([*args, "--images-root", str(manifest.parent)]) == 0
    assert len(calls) == 2
    output.unlink()
    args[2] = "synthetic_backend:missing"
    assert main([*args, "--images-root", str(manifest.parent)]) == 1
    assert not output.exists()


def test_absolute_image_and_frozen_test_output_are_refused(inputs):
    from vireceipt.extract_cli import main

    manifest, output, calls, args = inputs
    image = str(manifest.parent / "a.png").replace("\\", "/")
    manifest.write_text('{"id":"r0001","image":"' + image + '"}', encoding="utf-8")
    assert main(args) == 1 and calls == [] and not output.exists()
    manifest.write_text('{"id":"r0001","image":"a.png"}', encoding="utf-8")
    args[-1] = str(manifest.parent / "data" / "labels" / "test.jsonl")
    assert main([*args, "--overwrite"]) == 1 and calls == []
    assert not (manifest.parent / "data").exists()
