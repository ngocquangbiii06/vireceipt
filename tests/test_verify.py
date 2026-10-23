import copy
import math
from datetime import date

import pytest

TODAY = date(2026, 10, 23)


@pytest.mark.parametrize("raw", [None, "not JSON", [], {}, {"items": []}, math.nan])
def test_wrong_shape_is_one_schema_error_without_arithmetic(raw):
    from vireceipt.verify import verify_receipt

    result = verify_receipt(raw, today=TODAY)
    assert result.schema_valid is False
    assert [(i.code, i.severity) for i in result.issues] == [("schema_invalid", "error")]


def test_valid_receipt_has_no_issues_and_is_unchanged(receipt):
    from vireceipt.verify import verify_receipt

    before = copy.deepcopy(receipt)
    result = verify_receipt(receipt, today=TODAY)
    assert result.schema_valid and result.issues == () and receipt == before


def test_wrong_math_is_flagged_without_correcting_output(receipt):
    from vireceipt.verify import verify_receipt

    receipt["items"][0]["amount"] = 1
    receipt["total"] = 2
    before = copy.deepcopy(receipt)
    result = verify_receipt(receipt, today=TODAY)
    assert {i.code for i in result.issues} == {"line_amount", "items_sum", "total"}
    assert all(i.severity == "warning" for i in result.issues) and receipt == before


def test_null_numbers_skip_checks_and_missing_fields_remain_warnings(receipt):
    from vireceipt.verify import verify_receipt

    receipt.update(subtotal=None, discount=None, vat=None, total=None, items=[])
    receipt["issued_at"]["date"] = None
    receipt["seller"]["name"] = None
    result = verify_receipt(receipt, today=TODAY)
    assert result.schema_valid
    assert {i.code for i in result.issues} == {
        "date_missing",
        "total_missing",
        "items_missing",
        "seller_name_missing",
    }
    assert all(i.severity == "warning" for i in result.issues)


@pytest.mark.parametrize(
    "issued,code,severity",
    [
        ("2026-02-31", "date_invalid", "error"),
        ("2026-10-24", "date_future", "warning"),
        ("2014-12-31", "date_old", "warning"),
    ],
)
def test_calendar_and_date_checks_use_injected_today(receipt, issued, code, severity):
    from vireceipt.verify import verify_receipt

    receipt["issued_at"]["date"] = issued
    result = verify_receipt(receipt, today=TODAY)
    assert result.schema_valid
    assert any(i.code == code and i.severity == severity for i in result.issues)


def test_uncheckable_arithmetic_warns_instead_of_crashing(receipt):
    from vireceipt.verify import verify_receipt

    receipt["items"][0]["quantity"] = 1e100
    result = verify_receipt(receipt, today=TODAY)
    assert result.schema_valid
    assert any(
        i.code == "arithmetic_uncheckable" and i.severity == "warning" for i in result.issues
    )


@pytest.mark.parametrize("scenario", ["mixed-large-float", "sum-display-limit"])
def test_numeric_boundaries_preserve_date_checks_without_crashing(receipt, scenario):
    from vireceipt.verify import verify_receipt

    receipt["issued_at"]["date"] = "2026-10-24"
    if scenario == "mixed-large-float":
        receipt.update(items=[], subtotal=10**1000, total=10**1000, discount=1.0, vat=None)
    else:
        receipt["items"] = [
            {"name": "Synthetic", "quantity": None, "unit_price": None, "amount": 9 * 10**4299}
            for _ in range(2)
        ]
        receipt.update(subtotal=1, total=1)
    result = verify_receipt(receipt, today=TODAY)
    assert result.schema_valid
    assert {"arithmetic_uncheckable", "date_future"} <= {i.code for i in result.issues}
