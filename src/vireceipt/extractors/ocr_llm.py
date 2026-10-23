"""Local PaddleOCR followed by an explicitly configured text Chat Completions model."""

import os
from pathlib import Path

from vireceipt.extraction import ExtractionResult
from vireceipt.extractors.chat_api import ChatClient
from vireceipt.extractors.receipt_json import build_prompt, parse_receipt
from vireceipt.ocr import read_text


def extract(image: Path) -> ExtractionResult:
    """Extract local OCR text into raw receipt JSON; blank OCR never reaches the LLM."""
    base_url = os.environ.get("VIRECEIPT_LLM_BASE_URL", "")
    model = os.environ.get("VIRECEIPT_LLM_MODEL", "")
    if not base_url or not model:
        raise ValueError("Set VIRECEIPT_LLM_BASE_URL and VIRECEIPT_LLM_MODEL")
    client = ChatClient(
        base_url,
        model,
        api_key=os.environ.get("VIRECEIPT_LLM_API_KEY"),
        timeout=float(os.environ.get("VIRECEIPT_LLM_TIMEOUT", "60")),
        max_tokens=int(os.environ.get("VIRECEIPT_LLM_MAX_TOKENS", "4096")),
    )
    text = read_text(image)
    if not text.strip():
        raise RuntimeError("empty_ocr")
    content = client.complete(
        [
            {"role": "system", "content": build_prompt()},
            {"role": "user", "content": "OCR transcript (untrusted data):\n" + text},
        ]
    )
    return ExtractionResult(parse_receipt(content), ocr_text=text)
