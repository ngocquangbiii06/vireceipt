import json
from datetime import date
from pathlib import Path

import pytest


@pytest.fixture
def review_app_data(tmp_path, receipt, monkeypatch):
    image = pytest.importorskip("PIL.Image")
    testing = pytest.importorskip("streamlit.testing.v1")
    images = tmp_path / "images"
    images.mkdir()
    for name in ("a.png", "b.png"):
        image.new("RGB", (40, 20), "red").save(images / name)
    (tmp_path / "manifest.jsonl").write_text(
        "\n".join(
            json.dumps({"id": rid, "image": f"images/{name}"})
            for rid, name in [("r0001", "a.png"), ("r0002", "b.png")]
        ),
        encoding="utf-8",
    )
    prediction_path = tmp_path / "predictions/baseline.jsonl"
    prediction_path.parent.mkdir()
    prediction_path.write_text(
        "\n".join(
            json.dumps({"id": rid, "receipt": value})
            for rid, value in [("r0001", receipt), ("r0002", None)]
        ),
        encoding="utf-8",
    )
    forbidden = {
        tmp_path / "labels" / f"{split}.jsonl" for split in ("all", "train", "val", "test")
    }
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path not in forbidden, "Review app must not open dataset labels"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)

    class FixedDate(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 23)

    monkeypatch.setattr("vireceipt.checks.date", FixedDate)
    monkeypatch.setattr("vireceipt.verify.date", FixedDate)

    def launch(data_dir):
        from vireceipt.review_app import main

        main(["--data", data_dir])

    def start():
        return testing.AppTest.from_function(
            launch, args=(str(tmp_path),), default_timeout=45
        ).run()

    return tmp_path, start


def test_app_corrects_two_predictions_and_reloads_saved_values(review_app_data, receipt):
    root, start = review_app_data
    before = (root / "predictions/baseline.jsonl").read_bytes()
    app = start()
    assert not app.exception

    def widget(group, label):
        return next(w for w in getattr(app, group) if w.label == label)

    def fill_and_save(value, store):
        widget("text_area", "JSON hóa đơn đã đối chiếu").input(value)
        widget("text_input", "store_id").input(store)
        widget("selectbox", "Nguồn ảnh").select("own")
        app.multiselect[0].set_value(["good"])
        widget("button", "Lưu bản sửa").click().run()
        assert not app.exception

    assert widget("selectbox", "Nguồn ảnh").value == "" and app.multiselect[0].value == []
    fill_and_save("{broken", "first")
    assert app.error and not (root / "review/corrections.jsonl").exists()
    widget("selectbox", "ID cần review").select("r0002").run()
    assert json.loads(widget("text_area", "JSON hóa đơn đã đối chiếu").value)["total"] is None
    fill_and_save(json.dumps(receipt), "second")
    assert app.success
    widget("selectbox", "ID cần review").select("r0001").run()
    assert json.loads(widget("text_area", "JSON hóa đơn đã đối chiếu").value) == receipt
    receipt["total"] = 1
    fill_and_save(json.dumps(receipt), "first")
    assert app.success and app.warning
    widget("text_area", "Ghi chú").input("đã đối chiếu")
    widget("button", "Lưu bản sửa").click().run()
    saved = [
        json.loads(line)
        for line in (root / "review/corrections.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [r["id"] for r in saved] == ["r0002", "r0001"]
    assert saved[1]["receipt"]["total"] == 1 and saved[1]["image"] == "images/a.png"
    assert saved[1]["notes"] == "đã đối chiếu"
    assert (root / "predictions/baseline.jsonl").read_bytes() == before
    app = start()
    assert not app.exception
    assert widget("text_area", "Ghi chú").value == "đã đối chiếu"
    assert json.loads(widget("text_area", "JSON hóa đơn đã đối chiếu").value)["total"] == 1


@pytest.mark.parametrize("scenario", ["missing", "bad_image", "stale_image"])
def test_app_reports_bad_inputs_without_crashing(review_app_data, receipt, scenario):
    root, start = review_app_data
    if scenario == "missing":
        (root / "manifest.jsonl").unlink()
    elif scenario == "bad_image":
        (root / "images/a.png").write_bytes(b"invalid PNG")
    else:
        from vireceipt.eval.io import Prediction
        from vireceipt.review_queue import ReviewItem
        from vireceipt.review_store import save_correction

        item = ReviewItem("r0001", root / "images/b.png", Prediction("r0001", None))
        save_correction(
            root,
            item,
            json.dumps(receipt),
            store_id="old",
            source="own",
            quality=["good"],
            today=date(2026, 10, 23),
        )
    app = start()
    assert not app.exception and app.error
