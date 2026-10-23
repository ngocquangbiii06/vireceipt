"""Backend-independent extraction runner and prediction JSONL writer."""

import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from vireceipt.eval.io import Prediction
from vireceipt.verify import verify_receipt


@dataclass(frozen=True)
class ExtractionResult:
    """Raw JSON, optional backend metrics, and OCR evidence used only during verification."""

    receipt: Any
    confidence: float | None = None
    cost_usd: float | None = None
    ocr_text: str | None = None


class Extractor(Protocol):
    """Callable contract shared by future OCR/LLM and VLM backends."""

    def __call__(self, image: Path) -> ExtractionResult:
        """Extract one image without receiving gold labels."""
        ...


def extract_images(
    images: Mapping[str, Path], extractor: Extractor, *, today: date | None = None
) -> list[Prediction]:
    """Run in input order, retaining failed and schema-invalid predictions for evaluation."""
    predictions = []
    for record_id, image in images.items():
        started = perf_counter()
        try:
            result = extractor(image)
        except Exception:
            result, error = None, "extractor_failed"
        else:
            error = None
        elapsed = (perf_counter() - started) * 1000
        receipt, confidence, cost = None, None, None
        ocr_text = None
        if error is None:
            try:
                if not isinstance(result, ExtractionResult):
                    raise ValueError("Backend must return ExtractionResult")
                if result.ocr_text is not None:
                    if not isinstance(result.ocr_text, str):
                        raise ValueError("Invalid OCR text")
                    result.ocr_text.encode("utf-8")
                for value, upper in ((result.confidence, 1), (result.cost_usd, math.inf)):
                    if value is not None and (
                        isinstance(value, bool)
                        or not isinstance(value, int | float)
                        or not math.isfinite(value)
                        or not 0 <= value <= upper
                    ):
                        raise ValueError("Invalid confidence or cost")
                receipt = json.loads(
                    json.dumps(result.receipt, ensure_ascii=False, allow_nan=False).encode("utf-8")
                )
                confidence, cost = result.confidence, result.cost_usd
                ocr_text = result.ocr_text
            except (TypeError, ValueError, OverflowError, RecursionError):
                error = "invalid_result"
        verification = verify_receipt(receipt, today=today, ocr_text=ocr_text)
        extra = {
            "schema_valid": verification.schema_valid,
            "verification_issues": [asdict(issue) for issue in verification.issues],
            "grounding": {
                "checked": verification.grounding.checked,
                "unsupported_fields": list(verification.grounding.unsupported_fields),
            },
        }
        if error:
            extra["error"] = error
        predictions.append(
            Prediction(
                record_id,
                receipt,
                confidence=confidence,
                cost_usd=cost,
                latency_ms=elapsed,
                decision="review",
                extra=extra,
            )
        )
    return predictions


def write_predictions(predictions: Sequence[Prediction], output: str | Path) -> None:
    """Atomically write UTF-8 predictions in the existing eval JSONL format."""
    lines = []
    for prediction in predictions:
        row = vars(prediction).copy()
        row.update(row.pop("extra"))
        lines.append(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    payload = "".join(lines).encode("utf-8")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
