"""Parse form values and save labels without importing the UI dependencies."""

import json
import math
import os
import re
import tempfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from vireceipt.eval.io import QUALITY_TAGS
from vireceipt.normalize import norm_text, parse_money
from vireceipt.schema import validate_receipt


def _text(value: Any) -> str | None:
    return norm_text(str(value)) or None if value is not None else None


def parse_date(text: str) -> str | None:
    """Convert a printed date to ISO format, rejecting impossible calendar dates."""
    if not text.strip():
        return None
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Ngày không hợp lệ: {text!r}.")


def parse_time(text: str) -> str | None:
    """Convert a printed time to 24-hour HH:MM, dropping seconds."""
    if not text.strip():
        return None
    for pattern in ("%H:%M", "%H:%M:%S", "%I:%M %p"):
        try:
            return datetime.strptime(text.strip().upper(), pattern).strftime("%H:%M")
        except ValueError:
            pass
    raise ValueError(f"Giờ không hợp lệ: {text!r}.")


def build_record(values: dict[str, Any]) -> dict[str, Any]:
    """Build a label from flat metadata, seller_* fields, date/time and item rows."""

    def money(value: Any, field: str) -> int | None:
        text = _text(value)
        if text is None:
            return None
        amount = parse_money(text)
        if amount is None:
            raise ValueError(f"Số tiền {field} không hợp lệ: {text!r}.")
        return amount

    items = []
    for row in values.get("items", []):
        if not any(_text(value) for value in row.values()):
            continue
        quantity = _text(row.get("quantity"))
        try:
            quantity = float(quantity.replace(",", ".")) if quantity is not None else None
            if quantity is not None and not math.isfinite(quantity):
                raise ValueError
        except ValueError as error:
            raise ValueError(f"Số lượng không hợp lệ: {row.get('quantity')!r}.") from error
        items.append(
            dict(
                name=_text(row.get("name")),
                quantity=quantity,
                unit_price=money(row.get("unit_price"), "unit_price"),
                amount=money(row.get("amount"), "amount"),
            )
        )
    receipt = dict(
        schema_version="1.0",
        seller={
            key: _text(values.get(f"seller_{key}"))
            for key in ("name", "address", "phone", "tax_code")
        },
        issued_at=dict(
            date=parse_date(values.get("date") or ""), time=parse_time(values.get("time") or "")
        ),
        items=items,
        **{key: money(values.get(key), key) for key in ("subtotal", "discount", "vat", "total")},
        currency="VND",
        payment_method=_text(values.get("payment_method")),
    )
    errors = validate_receipt(receipt)
    if errors:
        raise ValueError("Nhãn không đúng schema: " + "; ".join(errors))
    record_id, image, store_id = (_text(values.get(key)) for key in ("id", "image", "store_id"))
    if record_id is None or not re.fullmatch(r"r\d{4}", record_id):
        raise ValueError("ID phải là r và 4 chữ số.")
    if image is None or Path(image).is_absolute() or ".." in Path(image).parts:
        raise ValueError("Ảnh phải có đường dẫn tương đối trong thư mục dữ liệu.")
    if store_id is None:
        raise ValueError("Cần điền store_id.")
    source, quality = values.get("source", "own"), values.get("quality", ["good"])
    if (
        source not in {"own", "mcocr"}
        or not isinstance(quality, list)
        or not quality
        or set(quality) - QUALITY_TAGS
    ):
        raise ValueError("Nguồn hoặc nhãn chất lượng không hợp lệ.")
    return dict(
        id=record_id,
        image=Path(image).as_posix(),
        store_id=store_id,
        source=source,
        quality=list(quality),
        receipt=receipt,
        notes=_text(values.get("notes")) or "",
    )


def next_id(existing_ids: Iterable[str]) -> str:
    """Allocate the next unused sequential rNNNN ID without filling old gaps."""
    number = (
        max((int(value[1:]) for value in existing_ids if re.fullmatch(r"r\d{4}", value)), default=0)
        + 1
    )
    if number > 9999:
        raise ValueError("Đã dùng hết ID r0001 đến r9999.")
    return f"r{number:04}"


def _read_labels(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()
    ]


def unlabeled_images(images_dir: str | Path, labels_path: str | Path) -> list[Path]:
    """Return JPG/JPEG/PNG paths absent from the supplied labels file."""
    images_dir = Path(images_dir)
    used = {Path(record["image"]).as_posix() for record in _read_labels(Path(labels_path))}
    return sorted(
        path
        for path in images_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        and path.relative_to(images_dir.parent).as_posix() not in used
    )


def upsert_record(labels_path: str | Path, record: dict[str, Any]) -> None:
    """Append or replace one ID atomically, preserving the other records' order."""
    errors = validate_receipt(record["receipt"])
    if errors:
        raise ValueError("Nhãn không đúng schema: " + "; ".join(errors))
    path = Path(labels_path)
    records = _read_labels(path)
    for index, existing in enumerate(records):
        if existing["id"] == record["id"]:
            records[index] = record
            break
    else:
        records.append(record)
    payload = "".join(
        json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in records
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload.encode("utf-8"))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
