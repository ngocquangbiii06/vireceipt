"""Validate candidate corrections without changing printed values or dataset labels."""

import json
from datetime import date
from typing import Any

from vireceipt.eval.io import QUALITY_TAGS
from vireceipt.verify import Verification, verify_receipt


def prepare_correction(
    receipt: Any,
    *,
    store_id: str,
    source: str,
    quality: list[str],
    notes: str = "",
    today: date | None = None,
) -> tuple[str, Verification]:
    """Return a strict JSON snapshot and non-blocking verification of the human's values."""
    if (
        not isinstance(store_id, str)
        or not store_id.strip()
        or not isinstance(source, str)
        or source not in {"own", "mcocr"}
        or not isinstance(quality, list)
        or not quality
        or any(not isinstance(tag, str) or tag not in QUALITY_TAGS for tag in quality)
        or not isinstance(notes, str)
    ):
        raise ValueError("Invalid correction metadata")
    record = dict(
        receipt=receipt, store_id=store_id.strip(), source=source, quality=quality, notes=notes
    )
    try:
        payload = json.dumps(record, ensure_ascii=False, allow_nan=False)
        payload.encode("utf-8")
        snapshot = json.loads(payload)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError("Correction must be strict UTF-8 JSON") from None
    report = verify_receipt(snapshot["receipt"], today=today)
    if not report.schema_valid:
        raise ValueError("Correction receipt must match schema")
    return payload, report
