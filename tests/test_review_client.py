import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.fixture
def review_http():
    state = SimpleNamespace(calls=[], replies=[])

    class Handler(BaseHTTPRequestHandler):
        def respond(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            state.calls.append((self.command, self.path, body))
            status, payload, headers = state.replies.pop(0)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_PUT = respond

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01))
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", state
        finally:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive()


def test_review_client_roundtrip_uses_correct_methods_and_keeps_json(review_http):
    from vireceipt.review_client import ReviewAPIClient

    url, state = review_http
    raw = {"_sale_note": "Cửa hàng\u2028A"}
    state.replies = [(200, json.dumps(raw).encode(), {})] * 3 + [(200, b"original image", {})]
    client, job_id = ReviewAPIClient(url), str(uuid4())
    assert client.list_requests(limit=20, offset=40, status="corrected") == raw
    assert client.get(job_id.upper()) == raw
    assert client.correct(job_id, raw) == raw
    assert client.image(job_id) == b"original image"
    assert state.calls[0][:2] == ("GET", "/v1/requests?limit=20&offset=40&status=corrected")
    assert state.calls[1][:2] == ("GET", "/v1/requests/" + job_id)
    assert state.calls[2][:2] == ("PUT", f"/v1/requests/{job_id}/correction")
    assert json.loads(state.calls[2][2]) == raw


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://user:pass@localhost",
        "http://127.0.0.1/v1",
        "http://localhost?x=1",
        "http://localhost#fragment",
        "http://localhost:0",
        " http://localhost",
    ],
)
def test_review_client_refuses_unsupported_url(url):
    from vireceipt.review_client import ReviewAPIClient

    with pytest.raises(ValueError):
        ReviewAPIClient(url)


@pytest.mark.parametrize(
    "scenario", ["conflict", "redirect", "json", "nonfinite", "surrogate", "size", "image_size"]
)
def test_review_client_sanitizes_errors_and_never_retries_or_redirects(
    review_http, monkeypatch, scenario
):
    from vireceipt.review_client import ReviewAPIClient, ReviewClientError

    url, state = review_http
    payloads = {
        "json": b"PRIVATE_BAD_JSON",
        "nonfinite": b'{"bad":NaN}',
        "surrogate": b'{"bad":"\\ud800"}',
        "size": b"x" * 33,
        "image_size": b"x" * 33,
    }
    monkeypatch.setattr("vireceipt.review_client.MAX_JSON_BYTES", 32)
    monkeypatch.setattr("vireceipt.review_client.MAX_IMAGE_BYTES", 32)
    status = {"conflict": 409, "redirect": 302}.get(scenario, 200)
    state.replies = [
        (status, payloads.get(scenario, b"PRIVATE_HTTP_ERROR"), {"Location": url + "/other"})
    ]
    with pytest.raises(ReviewClientError) as error:
        client = ReviewAPIClient(url)
        (client.image if scenario == "image_size" else client.get)(str(uuid4()))
    assert error.value.status == (status if status != 200 else None)
    assert "PRIVATE_" not in str(error.value) and len(state.calls) == 1


def test_timeout_is_sanitized_without_retry(monkeypatch):
    from vireceipt.review_client import ReviewAPIClient, ReviewClientError

    calls = []

    def timeout(request, *, timeout):
        calls.append(timeout)
        raise TimeoutError("PRIVATE_NETWORK_ERROR")

    client = ReviewAPIClient("http://localhost:8000")
    monkeypatch.setattr(client, "_opener", SimpleNamespace(open=timeout))
    with pytest.raises(ReviewClientError) as error:
        client.get(str(uuid4()))
    assert calls == [10] and "PRIVATE_" not in str(error.value)
