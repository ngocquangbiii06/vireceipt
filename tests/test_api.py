import io
from datetime import date
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from PIL import Image

from vireceipt.extraction import ExtractionResult

TODAY = date(2026, 10, 23)


@pytest.fixture
def png():
    stream = io.BytesIO()
    Image.new("RGB", (2, 3), "blue").save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def api_client(receipt):
    from vireceipt.api import create_app

    state = SimpleNamespace(calls=[], result=ExtractionResult(receipt), failed=False)

    def backend(image):
        state.calls.append((image, image.read_bytes()))
        if state.failed:
            raise RuntimeError("SECRET_BACKEND_ERROR")
        return state.result

    with TestClient(create_app(backend, today=TODAY)) as client:
        yield client, state


def test_health_and_extraction_preserve_contract_and_clean_temporary_image(
    api_client, png, receipt
):
    client, state = api_client
    assert client.get("/healthz").json() == {"status": "ok"}
    assert state.calls == []
    response = client.post(
        "/v1/extract?receipt_id=r0001", content=png, headers={"Content-Type": "image/png"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "r0001" and body["receipt"] == receipt and body["decision"] == "review"
    assert body["schema_valid"] and body["confidence"] is None and body["cost_usd"] is None
    path, payload = state.calls[0]
    assert path.suffix == ".png" and payload == png
    assert not path.exists() and not path.parent.exists()


def test_backend_errors_are_sanitized_and_later_requests_still_run(api_client, png):
    client, state = api_client
    url, headers = "/v1/extract?receipt_id=r0001", {"Content-Type": "image/png"}
    state.result = ExtractionResult("malformed JSON")
    response = client.post(url, content=png, headers=headers)
    assert response.status_code == 200 and response.json()["receipt"] == "malformed JSON"
    assert response.json()["schema_valid"] is False
    state.failed = True
    response = client.post(url, content=png, headers=headers)
    assert response.status_code == 502 and response.json()["error"] == "extractor_failed"
    assert "SECRET_BACKEND_ERROR" not in response.text
    state.failed = False
    state.result = ExtractionResult({}, confidence=True)
    response = client.post(url, content=png, headers=headers)
    assert response.status_code == 502 and response.json()["error"] == "invalid_result"
    state.result = ExtractionResult(None)
    assert client.post(url, content=png, headers=headers).status_code == 200
    assert all(not path.parent.exists() for path, _ in state.calls)


def test_grounding_is_flattened_and_eval_readable_without_transcript(
    api_client, png, receipt, tmp_path
):
    from vireceipt.eval.io import load_predictions

    client, state = api_client
    state.result = ExtractionResult(receipt, ocr_text="INTERNAL_TRANSCRIPT_MARKER")
    response = client.post(
        "/v1/extract?receipt_id=r0001", content=png, headers={"Content-Type": "image/png"}
    )
    assert response.json()["grounding"]["checked"]
    assert "INTERNAL_TRANSCRIPT_MARKER" not in response.text
    output = tmp_path / "prediction.jsonl"
    output.write_text(response.text + "\n", encoding="utf-8")
    (prediction,) = load_predictions(output)
    assert prediction.decision == "review" and prediction.extra["grounding"]["checked"]


@pytest.mark.parametrize(
    "scenario,status",
    [
        ("id", 422),
        ("unicode_id", 422),
        ("newline_id", 422),
        ("empty", 422),
        ("mime", 415),
        ("broken", 422),
        ("length", 413),
        ("stream", 413),
        ("bad_length", 400),
    ],
)
def test_invalid_requests_do_not_call_backend(api_client, png, scenario, status):
    from vireceipt.api_images import MAX_BYTES

    client, state = api_client
    record_id, payload, headers = "r0001", png, {"Content-Type": "image/png"}
    if scenario.endswith("id"):
        record_id = {"id": "r1", "unicode_id": "r٠٠٠١", "newline_id": "r0001\n"}[scenario]
    elif scenario == "empty":
        payload = b""
    elif scenario == "mime":
        headers["Content-Type"] = "application/json"
    elif scenario == "broken":
        payload = b"not an image"
    elif scenario == "length":
        headers["Content-Length"] = str(MAX_BYTES + 1)
    elif scenario == "stream":
        payload, headers["Content-Length"] = b"x" * (MAX_BYTES + 1), "0"
    else:
        headers["Content-Length"] = "invalid"
    response = client.post(
        "/v1/extract", params={"receipt_id": record_id}, content=payload, headers=headers
    )
    assert response.status_code == status and state.calls == []


def test_server_requires_explicit_known_backend(monkeypatch):
    from vireceipt.api import create_app

    for value in ("", "arbitrary.module:call"):
        monkeypatch.setenv("VIRECEIPT_API_BACKEND", value)
        with pytest.raises(ValueError, match="VIRECEIPT_API_BACKEND"):
            create_app()
