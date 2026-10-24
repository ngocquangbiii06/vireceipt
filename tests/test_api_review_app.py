import json
import threading
import time
from datetime import date

import pytest


@pytest.fixture
def api_review(api_repository, api_png, receipt):
    testing = pytest.importorskip("streamlit.testing.v1")
    uvicorn = pytest.importorskip("uvicorn")
    from vireceipt.api import create_app
    from vireceipt.eval.io import Prediction

    store, ids, _ = api_repository
    for raw in (receipt, None):
        ids.append(store.save(Prediction("r0001", raw, decision="review"), "image/png", api_png))

    def forbidden(image):
        raise AssertionError("Review UI must not invoke the model")

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(forbidden, store=store, today=date(2026, 10, 23)),
            host="127.0.0.1",
            port=0,
            log_config=None,
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        port = server.servers[0].sockets[0].getsockname()[1]

        def launch(url):
            from vireceipt.api_review_app import main

            main(["--api", url])

        def start():
            return testing.AppTest.from_function(
                launch,
                args=(f"http://127.0.0.1:{port}",),
                default_timeout=45,
            ).run()

        yield store, ids, start
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def _widget(app, group, label):
    return next(widget for widget in getattr(app, group) if widget.label == label)


def test_api_editor_saves_distinct_jobs_and_preserves_draft_on_conflict(api_review, receipt):
    store, ids, start = api_review
    before = store.get(ids[0]).prediction
    app = start()
    assert not app.exception
    assert json.loads(_widget(app, "text_area", "JSON hóa đơn đã đối chiếu").value)["total"] is None
    _widget(app, "selectbox", "Job cần review").select(ids[0]).run()
    assert json.loads(_widget(app, "text_area", "JSON hóa đơn đã đối chiếu").value) == receipt

    def save(text, store_id):
        _widget(app, "text_area", "JSON hóa đơn đã đối chiếu").input(text)
        _widget(app, "text_input", "store_id").input(store_id)
        _widget(app, "selectbox", "Nguồn ảnh").select("own")
        app.multiselect[0].set_value(["good"])
        _widget(app, "button", "Lưu bản sửa").click().run()
        assert not app.exception

    save("{broken", "first")
    assert app.error and store.get(ids[0]).revision == 0
    assert _widget(app, "text_area", "JSON hóa đơn đã đối chiếu").value == "{broken"
    receipt["total"] = 123
    _widget(app, "text_area", "Ghi chú").input("đã xem\u2028ảnh")
    save(json.dumps(receipt), "first")
    assert app.success and app.warning and store.get(ids[0]).revision == 1
    assert store.get(ids[0]).correction["notes"] == "đã xem\u2028ảnh"
    _widget(app, "text_area", "Ghi chú").input("draft chưa lưu")
    store.correct(
        ids[0],
        1,
        receipt,
        store_id="external",
        source="own",
        quality=["good"],
        notes="bản mới bên ngoài",
        today=date(2026, 10, 23),
    )
    _widget(app, "button", "Lưu bản sửa").click().run()
    assert not app.exception and app.error and "409" in app.error[0].value
    assert _widget(app, "text_area", "Ghi chú").value == "draft chưa lưu"
    assert store.get(ids[0]).correction["notes"] == "bản mới bên ngoài"
    _widget(app, "button", "Đọc lại bản mới").click().run()
    assert not app.exception and _widget(app, "text_area", "Ghi chú").value == "bản mới bên ngoài"
    _widget(app, "selectbox", "Job cần review").select(ids[1]).run()
    assert _widget(app, "selectbox", "Nguồn ảnh").value == "" and app.multiselect[0].value == []
    save(json.dumps(receipt), "second")
    assert app.success and store.get(ids[1]).correction["store_id"] == "second"
    assert store.get(ids[0]).prediction == before
    app = start()
    assert not app.exception and _widget(app, "text_input", "store_id").value == "second"


@pytest.mark.parametrize("scenario", ["empty", "unavailable", "bad_image"])
def test_api_editor_reports_unusable_queue_without_crashing(api_review, monkeypatch, scenario):
    from vireceipt.review_client import ReviewAPIClient, ReviewClientError

    _, _, start = api_review
    if scenario == "empty":
        monkeypatch.setattr(ReviewAPIClient, "list_requests", lambda *args, **kwargs: {"items": []})
    elif scenario == "bad_image":
        monkeypatch.setattr(ReviewAPIClient, "image", lambda *args: b"bad image")
    else:

        def unavailable(*args, **kwargs):
            raise ReviewClientError(503)

        monkeypatch.setattr(ReviewAPIClient, "list_requests", unavailable)
    app = start()
    assert not app.exception and (app.info if scenario == "empty" else app.error)
