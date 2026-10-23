import sys
from types import SimpleNamespace

import pytest


def test_ocr_preserves_lines_and_reuses_engine(tmp_path, monkeypatch):
    from vireceipt import ocr

    image = tmp_path / "a.png"
    image.write_bytes(b"image handled by external engine")
    created, paths = [], []

    def predict(*, input):
        paths.append(input)
        return [{"rec_texts": ["Cửa hàng", "", "TỔNG 10.000"], "rec_scores": [0.9, 0.0, 0.8]}]

    def factory(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(predict=predict)

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=factory))
    monkeypatch.setenv("VIRECEIPT_OCR_DEVICE", "cpu")
    ocr._engine.cache_clear()
    try:
        assert ocr.read_text(image) == "Cửa hàng\n\nTỔNG 10.000"
        assert ocr.read_text(image) == "Cửa hàng\n\nTỔNG 10.000"
        assert len(created) == 1 and paths == [str(image), str(image)]
        assert created[0]["device"] == "cpu"
        assert created[0]["text_recognition_model_name"] == "latin_PP-OCRv5_mobile_rec"
        assert created[0]["text_detection_model_name"] == "PP-OCRv5_mobile_det"
    finally:
        ocr._engine.cache_clear()


@pytest.mark.parametrize(
    "pages",
    [
        [],
        [{}],
        [{"rec_texts": "wrong"}],
        [{"rec_texts": [1]}],
        [{"rec_texts": []}, {"rec_texts": []}],
    ],
)
def test_invalid_ocr_output_is_not_silently_dropped(tmp_path, monkeypatch, pages):
    from vireceipt import ocr

    image = tmp_path / "a.png"
    image.touch()
    monkeypatch.setattr(ocr, "_engine", lambda device: SimpleNamespace(predict=lambda **kw: pages))
    with pytest.raises(RuntimeError, match="invalid_ocr_output"):
        ocr.read_text(image)


def test_empty_ocr_result_remains_empty(tmp_path, monkeypatch):
    from vireceipt import ocr

    image = tmp_path / "a.png"
    image.touch()
    monkeypatch.setattr(
        ocr, "_engine", lambda device: SimpleNamespace(predict=lambda **kw: [{"rec_texts": []}])
    )
    assert ocr.read_text(image) == ""


def test_missing_file_does_not_initialize_engine(tmp_path, monkeypatch):
    from vireceipt import ocr

    def unexpected(device):
        pytest.fail("must not initialize OCR for a missing image")

    monkeypatch.setattr(ocr, "_engine", unexpected)
    with pytest.raises(FileNotFoundError):
        ocr.read_text(tmp_path / "missing.png")


def test_optional_dependency_has_install_instruction(tmp_path, monkeypatch):
    from vireceipt import ocr

    image = tmp_path / "a.png"
    image.touch()
    monkeypatch.setitem(sys.modules, "paddleocr", None)
    ocr._engine.cache_clear()
    with pytest.raises(RuntimeError, match="uv sync --group ocr"):
        ocr.read_text(image)
