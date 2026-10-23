import json
from copy import deepcopy
from datetime import date

import pytest

from vireceipt import checks
from vireceipt.checks import check_labels, check_receipt, main
from vireceipt.eval.io import GoldRecord, load_gold

TODAY = date(2026, 10, 23)


@pytest.mark.parametrize(
    "path,value,expected",
    [
        ("items.0.amount", 63000, {"line_amount", "items_sum"}),
        ("subtotal", 88000, {"items_sum", "total"}),
        ("total", 90000, {"total"}),
        ("issued_at.date", "2026-10-24", {"date_future"}),
        ("issued_at.date", "2014-12-31", {"date_old"}),
        ("seller.name", None, {"seller_name_missing"}),
        ("issued_at.date", "2026-10-23", set()),
        ("issued_at.date", "2015-01-01", set()),
        ("issued_at.date", None, set()),
        ("items.0.quantity", None, set()),
        ("items.0.unit_price", None, set()),
        ("items.0.amount", None, set()),
        ("subtotal", None, set()),
        ("total", None, set()),
        ("items", [], set()),
    ],
)
def test_receipt_checks_skip_missing_numbers_and_respect_boundaries(receipt, path, value, expected):
    parts = path.split(".")
    target = receipt
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    key = int(parts[-1]) if isinstance(target, list) else parts[-1]
    target[key] = value
    original = deepcopy(receipt)
    issues = check_receipt(receipt, today=TODAY)
    assert {issue.code for issue in issues} == expected
    assert all(issue.severity == "warning" and issue.message for issue in issues)
    assert receipt == original


@pytest.mark.parametrize(
    "quantity,amount,expected",
    [(0.45, 14400, set()), (0.3333, 10666, set()), (0.45, 14000, {"line_amount"})],
)
def test_fractional_quantity_is_rounded_to_dong(receipt, quantity, amount, expected):
    receipt["items"] = [dict(receipt["items"][0], quantity=quantity, amount=amount)]
    receipt["subtotal"] = receipt["total"] = amount
    assert {i.code for i in check_receipt(receipt, today=TODAY)} == expected


@pytest.mark.parametrize(
    "discount,vat,total,expected",
    [
        (None, None, 90000, {"items_sum"}),
        (0, None, 90000, set()),
        (None, 0, 90000, set()),
        (None, None, None, set()),
        (None, None, 89000, set()),
    ],
)
def test_items_sum_uses_total_only_without_subtotal_discount_and_vat(
    receipt, discount, vat, total, expected
):
    receipt.update(subtotal=None, discount=discount, vat=vat, total=total)
    assert {i.code for i in check_receipt(receipt, today=TODAY)} == expected


@pytest.mark.parametrize("total,expected", [(84000, set()), (83000, {"total"})])
def test_total_subtracts_discount_and_adds_vat(receipt, total, expected):
    receipt.update(discount=10000, vat=5000, total=total)
    assert {i.code for i in check_receipt(receipt, today=TODAY)} == expected


def test_synthetic_labels_have_no_issues(gold_path):
    assert all(not issues for issues in check_labels(load_gold(gold_path), today=TODAY).values())


@pytest.mark.parametrize(
    "record_id,store,name,expected",
    [
        ("bad", "same", "Cửa hàng Minh Anh", {"id_format": "error"}),
        ("r0002", "same", "Khác", {"store_name_conflict": "warning"}),
        ("r0002", "same", " CỬA HÀNG  MINH ANH. ", {}),
        ("r0002", "different", "Khác", {}),
        ("r0002", "same", None, {"seller_name_missing": "warning"}),
    ],
)
def test_label_ids_and_store_names(receipt, record_id, store, name, expected):
    other = deepcopy(receipt)
    other["seller"]["name"] = name
    records = [GoldRecord("r0001", "same", receipt), GoldRecord(record_id, store, other)]
    issues = check_labels(records, today=TODAY)
    assert {i.code: i.severity for i in issues[record_id]} == expected
    assert bool(issues["r0001"]) == ("store_name_conflict" in expected)


@pytest.fixture
def fixed_today(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return TODAY

    monkeypatch.setattr(checks, "date", FixedDate)


@pytest.mark.parametrize(
    "record_id,warning,strict,image,exit_code,code",
    [
        ("r0001", False, False, "unchecked", 0, None),
        ("r0001", True, False, "unchecked", 0, "total"),
        ("r0001", True, True, "unchecked", 1, "total"),
        ("bad", False, False, "unchecked", 1, "id_format"),
        ("r0001", False, True, "file", 0, None),
        ("r0001", False, False, "missing", 1, "image_missing"),
        ("r0001", False, False, "directory", 1, "image_missing"),
        ("r0001", False, False, None, 1, "image_missing"),
    ],
)
def test_cli_reports_issues_and_exit_status(
    receipt, tmp_path, capsys, fixed_today, record_id, warning, strict, image, exit_code, code
):
    if warning:
        receipt["total"] = 90000
    image_name = None if image is None else "receipt.jpg"
    if image == "file":
        (tmp_path / image_name).write_bytes(b"synthetic image placeholder")
    elif image == "directory":
        (tmp_path / image_name).mkdir()
    labels = tmp_path / "labels.jsonl"
    labels.write_text(
        json.dumps(dict(id=record_id, store_id="store", receipt=receipt, image=image_name)) + "\n",
        encoding="utf-8",
    )
    args = [str(labels)] + (["--strict"] if strict else [])
    if image != "unchecked":
        args += ["--images-root", str(tmp_path)]
    assert main(args) == exit_code
    output = capsys.readouterr().out
    if code:
        severity = "warning" if warning else "error"
        assert f"{record_id}  {severity}  {code}  " in output
        assert f"{severity}: 1" in output
        if warning:
            assert "89000" in output and "90000" in output
    else:
        assert "error: 0" in output and "warning: 0" in output


@pytest.mark.parametrize(
    "content", [None, b"{\n", b"\xff", b"", b'{"id":"r0001","store_id":"s","receipt":{}}\n']
)
def test_cli_handles_read_and_schema_errors(tmp_path, capsys, fixed_today, content):
    labels = tmp_path / "invalid.jsonl"
    if content is not None:
        labels.write_bytes(content)
    assert main([str(labels)]) == 1
    assert "error:" in capsys.readouterr().err
