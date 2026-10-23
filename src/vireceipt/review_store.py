"""Save candidate labels in one local corrections file, outside all dataset splits."""

import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from vireceipt.eval.io import QUALITY_TAGS
from vireceipt.review_queue import ReviewItem
from vireceipt.schema import validate_receipt
from vireceipt.verify import Verification, verify_receipt


def _corrections_path(data_dir: Path) -> Path:
    path = data_dir.resolve() / "review" / "corrections.jsonl"
    if path.resolve() != path:
        raise ValueError("Corrections path must not use symlinks")
    return path


def _validate_record(record: Any, root: Path) -> None:
    json.dumps(record, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if not isinstance(record, dict):
        raise ValueError("Correction must be an object")
    record_id = record.get("id")
    if not isinstance(record_id, str) or not re.fullmatch(r"r[0-9]{4}", record_id):
        raise ValueError("Correction needs an rNNNN ID")
    image, store, source, quality = (
        record.get(key) for key in ("image", "store_id", "source", "quality")
    )
    if not isinstance(image, str) or Path(image).anchor or ".." in Path(image).parts:
        raise ValueError("Correction image must be relative to the data directory")
    image_path = (root / image).resolve()
    if not image_path.is_relative_to(root) or image_path.suffix.lower() not in {
        ".jpg",
        ".jpeg",
        ".png",
    }:
        raise ValueError("Correction image must be a JPG/PNG inside data")
    if not isinstance(store, str) or not store.strip():
        raise ValueError("store_id is required")
    if not isinstance(source, str) or source not in {"own", "mcocr"}:
        raise ValueError("Choose the image source")
    if (
        not isinstance(quality, list)
        or not quality
        or any(not isinstance(tag, str) or tag not in QUALITY_TAGS for tag in quality)
    ):
        raise ValueError("Choose at least one known quality tag")
    if not isinstance(record.get("notes", ""), str):
        raise ValueError("Notes must be text")
    errors = validate_receipt(record.get("receipt"))
    if errors:
        raise ValueError("Receipt does not match schema: " + errors[0])


def load_corrections(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Read only the fixed corrections file, rejecting corrupt or duplicate records."""
    path = _corrections_path(data_dir)
    if not path.exists():
        return {}
    records = {}
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        record = json.loads(line)
        _validate_record(record, data_dir.resolve())
        if record["id"] in records:
            raise ValueError("Duplicate correction ID")
        records[record["id"]] = record
    return records


def save_correction(
    data_dir: Path,
    item: ReviewItem,
    receipt_json: str,
    *,
    store_id: str,
    source: str,
    quality: list[str],
    notes: str = "",
    today: date | None = None,
) -> Verification:
    """Validate a human correction, atomically upsert it, and return non-blocking checks."""
    root, path = data_dir.resolve(), _corrections_path(data_dir)
    image = item.image.resolve().relative_to(root).as_posix()
    record = dict(
        id=item.id,
        image=image,
        store_id=store_id.strip(),
        source=source,
        quality=quality,
        receipt=json.loads(receipt_json),
        notes=notes,
    )
    _validate_record(record, root)
    records = load_corrections(root)  # Never overwrite a corrupt candidate-label file.
    report = verify_receipt(record["receipt"], today=today)
    records[item.id] = record
    payload = "".join(
        json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in records.values()
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return report
