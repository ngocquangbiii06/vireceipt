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


@pytest.mark.parametrize("separator", ["/", "-", "."])
@pytest.mark.parametrize(
    "iso,day,month,year",
    [
        ("2026-11-12", "12", "11", "2026"),
        ("2026-02-01", "1", "2", "2026"),
    ],
)
def test_two_digit_and_year_first_dates(grounded_receipt, separator, iso, day, month, year):
    from vireceipt.grounding import check_grounding

    grounded_receipt["issued_at"]["date"] = iso
    for printed in (
        f"{day}{separator}{month}{separator}{year[-2:]}",
        f"{year}{separator}{month}{separator}{day}",
        f"{int(day):02}{separator}{int(month):02}{separator}{year[-2:]}",
    ):
        assert "issued_at.date" not in check_grounding(grounded_receipt, printed).unsupported_fields


@pytest.mark.parametrize(
    "printed",
    [
        "11/12/2026",
        "12/11/25",
        "112/11/26",
        "12/11/261",
        "12026/11/12",
        "2026/11/121",
    ],
)
def test_date_mismatches_and_longer_numbers_do_not_ground(grounded_receipt, printed):
    from vireceipt.grounding import check_grounding

    grounded_receipt["issued_at"]["date"] = "2026-11-12"
    assert "issued_at.date" in check_grounding(grounded_receipt, printed).unsupported_fields


def test_vietnamese_diacritics_are_not_erased(grounded_receipt):
    from vireceipt.grounding import check_grounding

    assert "items.0.name" in check_grounding(grounded_receipt, "Sua tuoi").unsupported_fields


def test_literal_date_presence_is_independent_of_calendar_validity(grounded_receipt):
    from vireceipt.grounding import check_grounding

    grounded_receipt["issued_at"]["date"] = "2026-02-31"
    report = check_grounding(grounded_receipt, "Ngày: 2026-02-31")
    assert "issued_at.date" not in report.unsupported_fields


@pytest.mark.parametrize("printed", ["2k", "2 VND"])
def test_explicit_money_token_does_not_ground_item_quantity(grounded_receipt, printed):
    from vireceipt.grounding import check_grounding

    grounded_receipt["items"][0]["quantity"] = 2
    assert "items.0.quantity" in check_grounding(grounded_receipt, printed).unsupported_fields


@pytest.mark.parametrize("field,value", [("phone", "0901234567"), ("tax_code", "0312345678")])
@pytest.mark.parametrize("position", ["prefix", "suffix"])
def test_contact_is_not_part_of_a_longer_separated_number(grounded_receipt, field, value, position):
    from vireceipt.grounding import check_grounding

    printed = f"1 {value}" if position == "prefix" else f"{value} 89"
    assert f"seller.{field}" in check_grounding(grounded_receipt, printed).unsupported_fields


@pytest.mark.parametrize("printed", ["2 VND.", "2 VND,", "2 đồng.", "2 ₫.", "2 đ.", "2 k.", "2 d"])
def test_currency_punctuation_does_not_turn_money_into_quantity(grounded_receipt, printed):
    from vireceipt.grounding import check_grounding

    grounded_receipt["items"][0]["quantity"] = 2
    assert "items.0.quantity" in check_grounding(grounded_receipt, printed).unsupported_fields
