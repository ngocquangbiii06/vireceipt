import copy

import pytest


@pytest.fixture
def grounded_receipt(receipt):
    receipt["seller"].update(phone="0901234567", tax_code="0312345678")
    receipt["items"] = [{"name": "Sữa tươi", "quantity": 1.5, "unit_price": 32000, "amount": 48000}]
    receipt.update(subtotal=48000, total=48000, discount=None, vat=None)
    receipt["issued_at"].update(date="2026-10-12", time="18:42")
    return receipt


def test_printed_variants_match_without_changing_receipt(grounded_receipt):
    from vireceipt.grounding import check_grounding

    text = (
        "CỬA HÀNG MINH ANH\n12 Lý Thường Kiệt, Q.10, TP.HCM\n"
        "ĐT 090 123 4567 MST 031-234-5678\n12/10/2026 18h42\n"
        "Sữa tươi 1,5 x 32.000đ = 48k\nTiền mặt"
    )
    before = copy.deepcopy(grounded_receipt)
    report = check_grounding(grounded_receipt, text)
    assert report.checked and report.unsupported_fields == ()
    assert grounded_receipt == before


def test_missing_fields_and_substrings_do_not_count_as_evidence(grounded_receipt):
    from vireceipt.grounding import check_grounding

    report = check_grounding(
        grounded_receipt, "Cửa hàng Minh Anhhhh\nSữa tươiX 148000\n109012345678"
    )
    missing = set(report.unsupported_fields)
    assert {"seller.name", "seller.phone", "items.0.name", "items.0.amount", "total"} <= missing
    assert report.unsupported_fields == tuple(sorted(missing))


@pytest.mark.parametrize("ocr", [None, "", "  \n\t"])
def test_unavailable_ocr_is_not_a_pass(receipt, ocr):
    from vireceipt.grounding import check_grounding

    report = check_grounding(receipt, ocr)
    assert report.checked is False and report.unsupported_fields == ()


def test_null_values_are_not_reported_and_contract_constants_need_no_ocr(receipt):
    from vireceipt.grounding import check_grounding

    receipt["seller"] = {key: None for key in receipt["seller"]}
    receipt["issued_at"] = {"date": None, "time": None}
    receipt.update(
        items=[], subtotal=None, discount=None, vat=None, total=None, payment_method=None
    )
    assert check_grounding(receipt, "unrelated text").unsupported_fields == ()


@pytest.mark.parametrize("printed", ["2026-10-12", "12.10.2026", "12-10-2026"])
def test_date_printing_variants(grounded_receipt, printed):
    from vireceipt.grounding import check_grounding

    assert "issued_at.date" not in check_grounding(grounded_receipt, printed).unsupported_fields


def test_vietnamese_diacritics_are_not_erased(grounded_receipt):
    from vireceipt.grounding import check_grounding

    assert "items.0.name" in check_grounding(grounded_receipt, "Sua tuoi").unsupported_fields


@pytest.mark.parametrize("printed", ["2k", "2 VND"])
def test_explicit_money_token_does_not_ground_item_quantity(grounded_receipt, printed):
    from vireceipt.grounding import check_grounding

    grounded_receipt["items"][0]["quantity"] = 2
    assert "items.0.quantity" in check_grounding(grounded_receipt, printed).unsupported_fields
