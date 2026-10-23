"""Conservative output verification without gold labels or an auto-accept policy."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import DecimalException
from typing import Any

from vireceipt.checks import Issue, check_receipt
from vireceipt.schema import is_valid_receipt


@dataclass(frozen=True)
class Verification:
    """Schema status and issues; an empty issue list does not certify correctness."""

    schema_valid: bool
    issues: tuple[Issue, ...]


def verify_receipt(receipt: Any, *, today: date | None = None) -> Verification:
    """Check raw output without changing it; missing numbers never become arithmetic errors."""
    try:
        json.dumps(receipt, ensure_ascii=False, allow_nan=False).encode("utf-8")
        valid = is_valid_receipt(receipt)
    except (TypeError, ValueError, RecursionError, OverflowError):
        valid = False
    if not valid:
        return Verification(
            False, (Issue("schema_invalid", "error", "Output không đúng schema JSON."),)
        )
    try:
        issues = check_receipt(receipt, today=today)
    except DecimalException:
        # Keep date/seller/total checks even when line arithmetic exceeds Decimal's precision.
        issues = check_receipt({**receipt, "items": []}, today=today)
        issues.append(
            Issue("arithmetic_uncheckable", "warning", "Không kiểm được số học dòng hàng.")
        )
    issued = receipt["issued_at"]["date"]
    if issued is None:
        issues.append(Issue("date_missing", "warning", "Không đọc được ngày hóa đơn."))
    else:
        try:
            date.fromisoformat(issued)
        except ValueError:
            issues.append(Issue("date_invalid", "error", "Ngày hóa đơn không tồn tại trong lịch."))
    if receipt["total"] is None:
        issues.append(Issue("total_missing", "warning", "Không đọc được tổng tiền."))
    if not receipt["items"]:
        issues.append(Issue("items_missing", "warning", "Không có dòng hàng đọc được."))
    return Verification(True, tuple(issues))
