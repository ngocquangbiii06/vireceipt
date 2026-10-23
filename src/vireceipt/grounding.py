"""Conservative OCR presence checks; presence does not prove field alignment or correctness."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from vireceipt.normalize import digits_only, norm_loose, norm_text, parse_money

_NUMBER = re.compile(
    r"(?<![\w.,])[+-]?\d+(?:[.,]\d+)*(?:[ \u00a0]\d{3})*"
    r"(?:\s*(?:vnđ|vnd|đồng|dong|đ|₫|k))?(?![\w.,])",
    re.IGNORECASE,
)
_PAYMENT = {
    "cash": ("tiền mặt", "cash"),
    "card": ("thẻ", "card"),
    "bank_transfer": ("chuyển khoản", "bank transfer"),
    "e_wallet": ("ví điện tử", "e wallet", "momo", "zalopay"),
    "other": (),
}


@dataclass(frozen=True)
class GroundingResult:
    """Whether OCR was available and which populated fields lack normalized evidence."""

    checked: bool
    unsupported_fields: tuple[str, ...] = ()


def _text_present(value: str, normalized: str) -> bool:
    needle = norm_loose(value)
    return bool(needle) and f" {needle} " in f" {normalized} "


def _date_present(value: str, text: str) -> bool:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    day = f"0?{parsed.day}" if parsed.day < 10 else str(parsed.day)
    month = f"0?{parsed.month}" if parsed.month < 10 else str(parsed.month)
    pattern = rf"(?<!\d)(?:{re.escape(value)}|{day}[-/.]{month}[-/.]{parsed.year})(?!\d)"
    return re.search(pattern, text) is not None


def check_grounding(receipt: dict[str, Any], ocr_text: str | None) -> GroundingResult:
    """Check populated fields of a schema-valid receipt without reading labels or files."""
    if ocr_text is None or not ocr_text.strip():
        return GroundingResult(False)
    normalized = norm_loose(ocr_text)
    money, quantities = set(), set()
    for match in _NUMBER.finditer(ocr_text):
        token = match.group()
        try:
            amount = parse_money(token)
            if amount is not None:
                money.add(amount)
            if re.search(r"(vnđ|vnd|đồng|dong|đ|₫|k)$", token, re.IGNORECASE):
                continue
            number = norm_text(token).replace(" ", "")
            quantities.add(Decimal(number.replace(",", ".")))
        except (ValueError, InvalidOperation):
            continue
    missing = []

    def check(path: str, value: Any, supported: bool) -> None:
        if value is not None and not supported:
            missing.append(path)

    for key, value in receipt["seller"].items():
        if value is None:
            continue
        if key in {"phone", "tax_code"}:
            digits = digits_only(value)
            pattern = r"(?<!\d)" + r"[\s().+-]*".join(map(re.escape, digits)) + r"(?!\d)"
            supported = bool(digits) and re.search(pattern, ocr_text) is not None
        else:
            supported = _text_present(value, normalized)
        check(f"seller.{key}", value, supported)
    for index, item in enumerate(receipt["items"]):
        check(f"items.{index}.name", item["name"], _text_present(item["name"], normalized))
        quantity = item["quantity"]
        check(
            f"items.{index}.quantity",
            quantity,
            quantity is None or Decimal(str(quantity)) in quantities,
        )
        for key in ("unit_price", "amount"):
            check(f"items.{index}.{key}", item[key], item[key] in money)
    for key in ("subtotal", "discount", "vat", "total"):
        check(key, receipt[key], receipt[key] in money)
    issued = receipt["issued_at"]
    check(
        "issued_at.date",
        issued["date"],
        issued["date"] is None or _date_present(issued["date"], ocr_text),
    )
    clock = issued["time"]
    check(
        "issued_at.time",
        clock,
        clock is None
        or re.search(rf"(?<!\d){re.escape(clock).replace(':', '[:hH]')}(?!\d)", ocr_text)
        is not None,
    )
    method = receipt["payment_method"]
    check(
        "payment_method",
        method,
        method is None or any(_text_present(word, normalized) for word in _PAYMENT[method]),
    )
    return GroundingResult(True, tuple(sorted(missing)))
