import base64
import json

import pytest

from vireceipt.eval.io import load_predictions

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5VQAAAAASUVORK5CYII="
)


@pytest.fixture
def vlm_environment(chat_server, monkeypatch):
    for key, value in {
        "BASE_URL": chat_server.url,
        "MODEL": "synthetic-vision",
        "API_KEY": "synthetic-secret",
        "TIMEOUT": "2",
        "MAX_TOKENS": "321",
    }.items():
        monkeypatch.setenv(f"VIRECEIPT_VLM_{key}", value)
    return chat_server


def answer(content):
    return {
        "id": "synthetic",
        "object": "chat.completion",
        "created": 0,
        "model": "synthetic-vision",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content, "refusal": None},
                "logprobs": None,
            }
        ],
        "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9},
    }


def test_cli_image_http_prediction_roundtrip(vlm_environment, tmp_path, receipt):
    from vireceipt.extract_cli import main

    (tmp_path / "a.png").write_bytes(PNG)
    manifest, output = tmp_path / "images.jsonl", tmp_path / "pred.jsonl"
    manifest.write_text('{"id":"r0001","image":"a.png"}\n', encoding="utf-8")
    vlm_environment.replies = [(200, answer(json.dumps(receipt)), {})]
    assert (
        main(
            [
                str(manifest),
                "--extractor",
                "vireceipt.extractors.chat_vlm:extract",
                "--out",
                str(output),
            ]
        )
        == 0
    )
    (prediction,) = load_predictions(output)
    assert prediction.receipt == receipt and prediction.extra["schema_valid"] is True
    assert prediction.decision == "review" and prediction.latency_ms > 0
    assert prediction.confidence is None and prediction.cost_usd is None
    _, _, body = vlm_environment.requests[0]
    assert body["model"] == "synthetic-vision" and body["max_tokens"] == 321
    schema = json.loads(body["messages"][0]["content"].split("JSON Schema:\n")[1])
    assert schema["properties"]["currency"] == {"const": "VND"}
    uri = body["messages"][1]["content"][0]["image_url"]["url"]
    assert uri.startswith("data:image/png;base64,") and base64.b64decode(uri.split(",")[1]) == PNG


def test_api_failure_does_not_stop_later_images(vlm_environment, tmp_path):
    from vireceipt.extraction import extract_images, write_predictions
    from vireceipt.extractors.chat_vlm import extract

    image = tmp_path / "a.png"
    image.write_bytes(PNG)
    vlm_environment.replies = [(429, b"private diagnostic", {}), (200, answer("not JSON"), {})]
    predictions = extract_images({"r0001": image, "r0002": image}, extract)
    output = tmp_path / "pred.jsonl"
    write_predictions(predictions, output)
    failed, invalid = load_predictions(output)
    assert failed.receipt is None and failed.extra["error"] == "extractor_failed"
    assert invalid.receipt == "not JSON" and invalid.extra["schema_valid"] is False
    assert len(vlm_environment.requests) == 2 and "private" not in output.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("name,payload", [("a.png", b"garbage"), ("a.jpg", PNG), ("a.txt", PNG)])
def test_invalid_image_is_refused_before_http(vlm_environment, tmp_path, name, payload):
    from vireceipt.extractors.chat_vlm import extract

    image = tmp_path / name
    image.write_bytes(payload)
    with pytest.raises(ValueError, match="invalid_image"):
        extract(image)
    assert vlm_environment.requests == []


def test_large_image_is_refused_before_http(vlm_environment, tmp_path):
    from vireceipt.extractors.chat_vlm import extract

    image = tmp_path / "large.png"
    with image.open("wb") as stream:
        stream.write(PNG)
        stream.truncate(10 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="invalid_image"):
        extract(image)
    assert vlm_environment.requests == []


def test_missing_model_configuration_is_explicit(vlm_environment, tmp_path, monkeypatch):
    from vireceipt.extractors.chat_vlm import extract

    image = tmp_path / "a.png"
    image.write_bytes(PNG)
    monkeypatch.delenv("VIRECEIPT_VLM_MODEL")
    with pytest.raises(ValueError, match="VIRECEIPT_VLM_BASE_URL and VIRECEIPT_VLM_MODEL"):
        extract(image)
    assert vlm_environment.requests == []
