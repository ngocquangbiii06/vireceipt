"""Image adapter for an explicitly configured vision Chat Completions model."""

import base64
import os
from pathlib import Path

from vireceipt.extraction import ExtractionResult
from vireceipt.extractors.chat_api import ChatClient
from vireceipt.extractors.receipt_json import build_prompt, parse_receipt


def extract(image: Path) -> ExtractionResult:
    """Read a JPG/PNG and extract raw receipt JSON using environment configuration."""
    with image.open("rb") as stream:
        raw = stream.read(10 * 1024 * 1024 + 1)
    suffix = image.suffix.lower()
    if suffix == ".png" and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif suffix in {".jpg", ".jpeg"} and raw.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    else:
        raise ValueError("invalid_image")
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("invalid_image")
    base_url = os.environ.get("VIRECEIPT_VLM_BASE_URL", "")
    model = os.environ.get("VIRECEIPT_VLM_MODEL", "")
    if not base_url or not model:
        raise ValueError("Set VIRECEIPT_VLM_BASE_URL and VIRECEIPT_VLM_MODEL")
    client = ChatClient(
        base_url,
        model,
        api_key=os.environ.get("VIRECEIPT_VLM_API_KEY"),
        timeout=float(os.environ.get("VIRECEIPT_VLM_TIMEOUT", "60")),
        max_tokens=int(os.environ.get("VIRECEIPT_VLM_MAX_TOKENS", "4096")),
    )
    uri = f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
    content = client.complete(
        [
            {"role": "system", "content": build_prompt()},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": uri}}]},
        ]
    )
    return ExtractionResult(parse_receipt(content))
