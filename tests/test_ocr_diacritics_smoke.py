import runpy
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
