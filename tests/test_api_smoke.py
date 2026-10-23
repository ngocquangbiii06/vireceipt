import io
import json
import threading
import time
import urllib.request
from datetime import date

import pytest

testing = pytest.importorskip("fastapi.testclient")
uvicorn = pytest.importorskip("uvicorn")
Image = pytest.importorskip("PIL.Image")


def _png():
    stream = io.BytesIO()
    Image.new("RGB", (2, 3), "blue").save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.parametrize("backend,prefix", [("vlm", "VLM"), ("ocr-llm", "LLM")])
def test_factory_uses_selected_chat_adapter(monkeypatch, chat_server, receipt, backend, prefix):
    from vireceipt.api import create_app

    monkeypatch.setenv("VIRECEIPT_API_BACKEND", backend)
    for key, value in {
        "BASE_URL": chat_server.url,
        "MODEL": "synthetic-only",
        "API_KEY": "synthetic-key",
    }.items():
        monkeypatch.setenv(f"VIRECEIPT_{prefix}_{key}", value)
    if backend == "ocr-llm":
        monkeypatch.setattr("vireceipt.extractors.ocr_llm.read_text", lambda image: "Tổng 89000")
    chat_server.replies = [
        (
            200,
            {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(receipt)}}]},
            {},
        )
    ]
    with testing.TestClient(create_app(today=date(2026, 10, 23))) as client:
        response = client.post(
            "/v1/extract?receipt_id=r0001", content=_png(), headers={"Content-Type": "image/png"}
        )
    assert response.status_code == 200 and response.json()["receipt"] == receipt
    assert response.json()["grounding"]["checked"] is (backend == "ocr-llm")
    _, _, body = chat_server.requests[0]
    assert body["model"] == "synthetic-only"
    user_content = body["messages"][1]["content"]
    if backend == "vlm":
        assert user_content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    else:
        assert "Tổng 89000" in user_content


def test_headless_uvicorn_serves_real_loopback_http_and_shuts_down(receipt):
    from vireceipt.api import create_app
    from vireceipt.extraction import ExtractionResult

    app = create_app(lambda image: ExtractionResult(receipt), today=date(2026, 10, 23))
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_config=None, access_log=False)
    )
    thread = threading.Thread(target=server.run)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started, "Uvicorn did not start"
        port = server.servers[0].sockets[0].getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(base_url + "/healthz", timeout=5) as response:
            assert response.status == 200 and json.load(response) == {"status": "ok"}
        request = urllib.request.Request(
            base_url + "/v1/extract?receipt_id=r0001",
            data=_png(),
            headers={"Content-Type": "image/png"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.load(response)
            assert response.status == 200 and body["receipt"] == receipt
            assert body["decision"] == "review"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), "Uvicorn failed to shut down"
