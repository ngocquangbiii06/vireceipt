"""Optional CPU PaddleOCR baseline with explicit mobile detection/Latin recognition models."""

import os
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any


@cache
def _engine(device: str) -> Any:
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        raise RuntimeError("Install OCR dependencies: uv sync --group ocr") from None
    return PaddleOCR(
        device=device,
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
        text_rec_score_thresh=0.0,
    )


def read_text(image: Path) -> str:
    """Read one image, preserving the OCR engine's line order and Unicode text."""
    if not image.is_file():
        raise FileNotFoundError("OCR image does not exist")
    engine = _engine(os.environ.get("VIRECEIPT_OCR_DEVICE") or "cpu")
    pages = list(engine.predict(input=str(image)))
    if len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise RuntimeError("invalid_ocr_output")
    texts = pages[0].get("rec_texts")
    if not isinstance(texts, list) or any(not isinstance(text, str) for text in texts):
        raise RuntimeError("invalid_ocr_output")
    return "\n".join(texts)
