import io
import runpy
import sys
from pathlib import Path

import pytest


@pytest.fixture
def smoke():
    return runpy.run_path(str(Path(__file__).parents[1] / "scripts/ocr_diacritics_smoke.py"))


def test_vietnamese_diacritics_and_aggregate_cer(smoke):
    assert smoke["strip_accents"]("ĐẶNG Thị Sữa ă â ê ô ơ ư") == "DANG Thi Sua a a e o o u"
    assert smoke["cer"]("Sữa", "Sua") == pytest.approx(1 / 3)
    assert smoke["cer"]("abc", "abxc") == pytest.approx(1 / 3)
    assert smoke["cer"]("abc", "ac") == pytest.approx(1 / 3)
    assert smoke["cer"]("", "") == 0
    metrics = smoke["summarize"](["Sữa", "Đỏ"], ["Sua", "Đỏ"])
    assert metrics == {
        "lines": 2,
        "exact": 1,
        "accentless": 2,
        "edits": 1,
        "characters": 5,
        "cer": 0.2,
    }
    assert smoke["summarize"]([" Sữa\n"], ["Sữa"])["exact"] == 1
    with pytest.raises(ValueError):
        smoke["summarize"](["Sữa"], [])


def test_render_single_line_and_fixed_corpus_cover_vietnamese(smoke):
    image_font = pytest.importorskip("PIL.ImageFont")
    image = smoke["render_line"]("Receipt 123", image_font.load_default())
    assert image.mode == "RGB" and image.getpixel((0, 0)) == (255, 255, 255)
    assert image.convert("L").getextrema()[0] < 128  # Antialiased small glyphs can be near-black.
    assert len(smoke["LINES"]) == 40
    corpus = " ".join(smoke["LINES"]).lower()
    assert set("ăâđêôơưáàảãạ") <= set(corpus)


def test_report_file_keeps_utf8_with_legacy_console(smoke, tmp_path, monkeypatch):
    buffer = io.BytesIO()
    console = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    output = tmp_path / "report.md"
    smoke["write_report"]("Sữa\n", output)
    console.flush()
    assert output.read_text(encoding="utf-8") == "Sữa\n"
    assert buffer.getvalue()


def test_report_records_configured_device_without_running_ocr(smoke, tmp_path, monkeypatch):
    from PIL import ImageFont

    font = ImageFont.load_default()
    monkeypatch.setattr(ImageFont, "truetype", lambda *args, **kwargs: font)
    monkeypatch.setattr("vireceipt.ocr.read_text", lambda image: "Sữa")
    monkeypatch.setenv("VIRECEIPT_OCR_DEVICE", "gpu:0")
    monkeypatch.setitem(smoke["main"].__globals__, "version", lambda package: "synthetic-version")
    monkeypatch.setattr("subprocess.check_output", lambda *args, **kwargs: "synthetic-commit")
    monkeypatch.chdir(tmp_path)
    assert smoke["main"]([]) == 0
    report = next((tmp_path / "results").glob("*.md")).read_text(encoding="utf-8")
    assert "device=gpu:0" in report
