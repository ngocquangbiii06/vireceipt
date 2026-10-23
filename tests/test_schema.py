from vireceipt.schema import is_valid_receipt, load_schema, validate_receipt


def test_schema_loads_and_example_is_valid(receipt):
    assert load_schema()["title"] == "Receipt"
    assert validate_receipt(receipt) == []


def test_money_must_be_non_negative_integer(receipt):
    receipt["total"] = 89000.5
    assert not is_valid_receipt(receipt)
    receipt["total"] = -1
    assert not is_valid_receipt(receipt)


def test_date_and_time_formats(receipt):
    receipt["issued_at"]["date"] = "12/11/2026"
    assert any("issued_at/date" in e for e in validate_receipt(receipt))
    receipt["issued_at"] = {"date": "2026-11-12", "time": "24:00"}
    assert not is_valid_receipt(receipt)


def test_unknown_fields_and_payment_methods_rejected(receipt):
    receipt["tip"] = 5000
    assert not is_valid_receipt(receipt)
    del receipt["tip"]
    receipt["payment_method"] = "momo"
    assert not is_valid_receipt(receipt)


def test_nulls_allowed_where_field_may_be_absent(receipt):
    receipt["seller"] = {"name": None, "address": None, "phone": None, "tax_code": None}
    receipt["items"] = []
    receipt["subtotal"] = receipt["total"] = None
    assert is_valid_receipt(receipt)
