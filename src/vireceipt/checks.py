"""Reusable receipt checks and a CLI for checking synthetic or unfrozen labels."""

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Literal

from vireceipt.eval.io import DataError, GoldRecord, load_gold
from vireceipt.normalize import norm_loose


@dataclass(frozen=True)
class Issue:
    """One label problem with a stable code and a Vietnamese explanation."""

    code: str
    severity: Literal["error", "warning"]
    message: str


def check_receipt(receipt: dict[str, Any], *, today: date | None = None) -> list[Issue]:
    """Check a schema-valid receipt without changing it or reading files."""
    issues = []

    def warn(code: str, message: str) -> None:
        issues.append(Issue(code, "warning", message))

    for index, item in enumerate(receipt["items"], start=1):
        quantity, price, amount = (item[key] for key in ("quantity", "unit_price", "amount"))
        if all(value is not None for value in (quantity, price, amount)):
            expected = int(
                (Decimal(str(quantity)) * Decimal(str(price))).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            if expected != amount:
                warn(
                    "line_amount",
                    f"Món {index}: {quantity} × {price} làm tròn lên ở .5 = {expected}, "
                    f"amount = {amount}.",
                )
    subtotal, discount, vat, total = (
        receipt[key] for key in ("subtotal", "discount", "vat", "total")
    )
    target = subtotal
    if subtotal is None and discount is None and vat is None:
        target = total
    items = receipt["items"]
    if items and target is not None and all(item["amount"] is not None for item in items):
        amount_sum = sum(item["amount"] for item in items)
        if amount_sum != target:
            field = "subtotal" if subtotal is not None else "total"
            warn("items_sum", f"Tổng amount = {amount_sum}, nhưng {field} = {target}.")
    if subtotal is not None and total is not None:
        expected = subtotal - (discount or 0) + (vat or 0)
        if expected != total:
            warn(
                "total",
                f"subtotal {subtotal} - discount {discount or 0} + vat {vat or 0}"
                f" = {expected}, nhưng total = {total}.",
            )
    issued = receipt["issued_at"]["date"]
    if issued is not None:
        current = (today or date.today()).isoformat()
        if issued > current:
            warn("date_future", f"Ngày {issued} sau ngày kiểm tra {current}.")
        if issued < "2015-01-01":
            warn("date_old", f"Ngày {issued} trước 2015-01-01.")
    if receipt["seller"]["name"] is None:
        warn("seller_name_missing", "seller.name = null: thiếu tên cửa hàng.")
    return issues


def check_labels(records: list[GoldRecord], *, today: date | None = None) -> dict[str, list[Issue]]:
    """Check receipts, record IDs and store names without reading files."""
    names: dict[str, set[str]] = {}
    for record in records:
        name = record.receipt["seller"]["name"]
        if name is not None:
            names.setdefault(record.store_id, set()).add(norm_loose(name))
    result = {}
    for record in records:
        issues = check_receipt(record.receipt, today=today)
        if not re.fullmatch(r"r\d{4}", record.id):
            issues.append(Issue("id_format", "error", f"ID {record.id!r} phải là r và 4 chữ số."))
        store_names = names.get(record.store_id, set())
        if record.receipt["seller"]["name"] is not None and len(store_names) > 1:
            issues.append(
                Issue(
                    "store_name_conflict",
                    "warning",
                    f"Cửa hàng {record.store_id!r} có {len(store_names)} tên khác nhau: "
                    f"{', '.join(sorted(store_names))}.",
                )
            )
        result[record.id] = issues
    return result


def main(argv: list[str] | None = None) -> int:
    """Print label issues and return a status suitable for shell scripts."""
    parser = argparse.ArgumentParser(description="Kiểm tra tính nhất quán của nhãn hóa đơn.")
    parser.add_argument("labels", help="file nhãn JSONL chưa đóng băng")
    parser.add_argument("--images-root", type=Path, help="thư mục gốc của đường dẫn ảnh")
    parser.add_argument("--strict", action="store_true", help="thoát mã 1 cả khi chỉ có warning")
    args = parser.parse_args(argv)
    try:
        records = load_gold(args.labels)
    except (DataError, OSError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    issues_by_id = check_labels(records)
    if args.images_root is not None:
        for record in records:
            if not record.image or not (args.images_root / record.image).is_file():
                issues_by_id[record.id].append(
                    Issue(
                        "image_missing",
                        "error",
                        f"Không có file ảnh {record.image!r} trong {args.images_root}.",
                    )
                )
    counts = {"error": 0, "warning": 0}
    for record_id, issues in issues_by_id.items():
        for issue in issues:
            print(f"{record_id}  {issue.severity}  {issue.code}  {issue.message}")
            counts[issue.severity] += 1
    print(f"error: {counts['error']}  warning: {counts['warning']}")
    return int(counts["error"] > 0 or (args.strict and counts["warning"] > 0))


if __name__ == "__main__":
    raise SystemExit(main())
