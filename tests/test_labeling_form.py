import json
from datetime import date

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


def test_app_saves_two_images_and_edits_without_opening_splits(tmp_path, monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    image = pytest.importorskip("PIL.Image")
    from pathlib import Path

    class FixedDate(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 23)

    monkeypatch.setattr("vireceipt.checks.date", FixedDate)

    images, labels = tmp_path / "images", tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    image.new("RGB", (40, 20), "red").save(images / "a.png")
    image.new("RGB", (20, 40), "blue").save(images / "b.jpg")
    forbidden = {labels / f"{name}.jsonl" for name in ("train", "val", "test")}
    for path in forbidden:
        path.write_bytes(b"must never open")
    original_open = Path.open

    def guard(path, *args, **kwargs):
        assert path not in forbidden, f"App opened a split file: {path}"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guard)

    def launch(data_dir):
        from vireceipt.labeling.app import main

        main(["--data", data_dir])

    app = testing.AppTest.from_function(launch, args=(str(tmp_path),), default_timeout=45).run()
    assert not app.exception

    def text(label):
        return next(widget for widget in app.text_input if widget.label == label)

    def click(label):
        next(widget for widget in app.button if widget.label == label).click().run()
        assert not app.exception

    text("Tên cửa hàng").input("Không được mang sang ảnh khác")
    text("store_id").input("demo-q1")
    text("Ngày").input("31/02/2026")
    click("Lưu")
    assert app.error
    next(widget for widget in app.selectbox if widget.label == "Ảnh chưa gán").select(
        "images/b.jpg"
    ).run()
    assert text("Tên cửa hàng").value == ""
    next(widget for widget in app.selectbox if widget.label == "Ảnh chưa gán").select(
        "images/a.png"
    ).run()
    click("Xoay 90°")
    assert app.session_state["rotation:images/a.png"] == 90
    text("store_id").input("demo-q1")
    text("Ngày").input("31/02/2026")
    click("Lưu")
    assert app.error and not (labels / "all.jsonl").exists()
    text("Ngày").input("12/10/2026")
    text("Tổng thanh toán").input("20.000")
    click("Lưu")
    assert app.success and app.warning
    assert any("demo-q1" in caption.value for caption in app.caption)
    text("store_id").input("demo-q1")
    text("Tên cửa hàng").input("Quán thử nghiệm")
    click("Lưu")
    assert app.success
    app.radio[0].set_value("Sửa nhãn").run()
    assert not app.exception
    app.text_area[0].input("đã sửa bằng AppTest")
    click("Lưu")
    saved = [
        json.loads(line) for line in (labels / "all.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["id"] for row in saved] == ["r0001", "r0002"]
    assert saved[0]["notes"] == "đã sửa bằng AppTest"
    assert saved[0]["image"] == "images/a.png" and saved[1]["image"] == "images/b.jpg"
