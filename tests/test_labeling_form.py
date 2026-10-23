import json

import pytest

from vireceipt.schema import validate_receipt


@pytest.mark.parametrize("text", ["12/11/2026", "12/11/26", "12-11-2026", "2026-11-12"])
def test_parse_date_accepts_printed_formats(text):
    from vireceipt.labeling.form import parse_date

    assert parse_date(text) == "2026-11-12"
    assert parse_date(" ") is None


@pytest.mark.parametrize("text", ["31/02/2026", "2026-13-01", "không rõ"])
def test_parse_date_rejects_invalid_calendar_dates(text):
    from vireceipt.labeling.form import parse_date

    with pytest.raises(ValueError, match="Ngày"):
        parse_date(text)


@pytest.mark.parametrize("text", ["18:42", "18:42:10", "6:42 PM", "06:42 pm"])
def test_parse_time_accepts_printed_formats(text):
    from vireceipt.labeling.form import parse_time

    assert parse_time(text) == "18:42"
    assert parse_time("") is None


@pytest.mark.parametrize("text", ["24:00", "18:60", "không rõ"])
def test_parse_time_rejects_invalid_values(text):
    from vireceipt.labeling.form import parse_time

    with pytest.raises(ValueError, match="Giờ"):
        parse_time(text)


@pytest.fixture
def values():
    return dict(
        id="r0001",
        image="images/a.png",
        store_id="demo-q1",
        seller_name=" Cửa  Hàng ",
        date="12/11/26",
        time="6:42 PM",
        total="14.400",
        items=[dict(name=" Gạo ", quantity="0,45", unit_price="32.000đ", amount="14.400")],
    )


def test_build_record_normalizes_text_money_and_optional_values(values):
    from vireceipt.labeling.form import build_record

    record = build_record(values)
    receipt = record["receipt"]
    assert validate_receipt(receipt) == []
    assert record["quality"] == ["good"] and record["source"] == "own"
    assert receipt["seller"]["name"] == "Cửa Hàng" and receipt["seller"]["phone"] is None
    assert receipt["items"] == [dict(name="Gạo", quantity=0.45, unit_price=32000, amount=14400)]
    assert receipt["total"] == 14400 and receipt["currency"] == "VND"
    values.update(seller_name="", date="", time="", total="", items=[])
    blank = build_record(values)["receipt"]
    assert blank["seller"]["name"] is blank["issued_at"]["date"] is blank["total"] is None


@pytest.mark.parametrize(
    "field,value",
    [("payment_method", "invalid"), ("total", "abc"), ("id", "bad"), ("store_id", "")],
)
def test_invalid_form_does_not_change_saved_labels(values, tmp_path, field, value):
    from vireceipt.labeling.form import build_record, upsert_record

    labels = tmp_path / "all.jsonl"
    upsert_record(labels, build_record(values))
    before = labels.read_bytes()
    values[field] = value
    with pytest.raises(ValueError):
        upsert_record(labels, build_record(values))
    assert labels.read_bytes() == before


def test_upsert_is_atomic_and_preserves_record_order(values, tmp_path, monkeypatch):
    from vireceipt.labeling import form

    labels = tmp_path / "labels" / "all.jsonl"
    first = form.build_record(values)
    form.upsert_record(labels, first)
    second = form.build_record(dict(values, id="r0002", image="images/b.png"))
    form.upsert_record(labels, second)
    first["notes"] = "đã sửa"
    form.upsert_record(labels, first)
    assert [json.loads(line) for line in labels.read_text(encoding="utf-8").splitlines()] == [
        first,
        second,
    ]
    before = labels.read_bytes()

    def fail_replace(*args):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(form.os, "replace", fail_replace)
    with pytest.raises(OSError):
        form.upsert_record(labels, second)
    assert labels.read_bytes() == before
    assert list(labels.parent.iterdir()) == [labels]


def test_unlabeled_images_and_next_id(values, tmp_path):
    from vireceipt.labeling.form import build_record, next_id, unlabeled_images, upsert_record

    images = tmp_path / "images"
    images.mkdir()
    for name in ("a.png", "b.JPG", "c.jpeg", "ignore.txt"):
        (images / name).touch()
    labels = tmp_path / "labels" / "all.jsonl"
    assert [p.name for p in unlabeled_images(images, labels)] == ["a.png", "b.JPG", "c.jpeg"]
    upsert_record(labels, build_record(values))
    assert [p.name for p in unlabeled_images(images, labels)] == ["b.JPG", "c.jpeg"]
    assert next_id([]) == "r0001"
    assert next_id(["r0003", "r0001"]) == "r0004"
