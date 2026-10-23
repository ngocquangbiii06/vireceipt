"""Read gold labels and predictions from JSON Lines files."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vireceipt.schema import validate_receipt

QUALITY_TAGS = {"good", "blurry", "skewed", "low_light", "crumpled", "cropped"}
DECISIONS = {"accept", "review"}


class DataError(ValueError):
    """A labels or predictions file is malformed."""


@dataclass(frozen=True)
class GoldRecord:
    id: str
    store_id: str
    receipt: dict[str, Any]
    quality: tuple[str, ...] = ("good",)
    source: str = "own"
    image: str | None = None


@dataclass(frozen=True)
class Prediction:
    id: str
    receipt: Any  # raw value from the file; may be None or schema-invalid
    confidence: float | None = None
    decision: str | None = None
    latency_ms: float | None = None
    cost_usd: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise DataError(f"{path}:{lineno}: invalid JSON ({e.msg})") from e
            if not isinstance(obj, dict):
                raise DataError(f"{path}:{lineno}: expected a JSON object")
            rows.append((lineno, obj))
    return rows


def load_gold(path: str | Path) -> list[GoldRecord]:
    """Load and validate a labels file. Raises DataError with the line number on any problem."""
    path = Path(path)
    records, seen = [], set()
    for lineno, obj in _read_jsonl(path):
        where = f"{path}:{lineno}"
        for key in ("id", "store_id", "receipt"):
            if key not in obj:
                raise DataError(f"{where}: missing '{key}'")
        if obj["id"] in seen:
            raise DataError(f"{where}: duplicate id {obj['id']!r}")
        seen.add(obj["id"])
        errors = validate_receipt(obj["receipt"])
        if errors:
            raise DataError(f"{where}: receipt does not match schema: {errors[0]}")
        quality = tuple(obj.get("quality") or ["good"])
        unknown = set(quality) - QUALITY_TAGS
        if unknown:
            raise DataError(f"{where}: unknown quality tag(s) {sorted(unknown)}")
        records.append(
            GoldRecord(
                id=obj["id"],
                store_id=obj["store_id"],
                receipt=obj["receipt"],
                quality=quality,
                source=obj.get("source", "own"),
                image=obj.get("image"),
            )
        )
    if not records:
        raise DataError(f"{path}: no records")
    return records


def load_predictions(path: str | Path) -> list[Prediction]:
    """Load a predictions file. The receipt itself is not validated here (that is a metric)."""
    path = Path(path)
    preds, seen = [], set()
    known = {"id", "receipt", "confidence", "decision", "latency_ms", "cost_usd"}
    for lineno, obj in _read_jsonl(path):
        where = f"{path}:{lineno}"
        if "id" not in obj or "receipt" not in obj:
            raise DataError(f"{where}: each prediction needs 'id' and 'receipt'")
        if obj["id"] in seen:
            raise DataError(f"{where}: duplicate id {obj['id']!r}")
        seen.add(obj["id"])
        decision = obj.get("decision")
        if decision is not None and decision not in DECISIONS:
            raise DataError(f"{where}: decision must be one of {sorted(DECISIONS)}")
        confidence = obj.get("confidence")
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, int | float)
            or not 0.0 <= confidence <= 1.0
        ):
            raise DataError(f"{where}: confidence must be in [0, 1]")
        preds.append(
            Prediction(
                id=obj["id"],
                receipt=obj["receipt"],
                confidence=None if confidence is None else float(confidence),
                decision=decision,
                latency_ms=obj.get("latency_ms"),
                cost_usd=obj.get("cost_usd"),
                extra={k: v for k, v in obj.items() if k not in known},
            )
        )
    return preds
