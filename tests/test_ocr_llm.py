import json

import pytest

from vireceipt.eval.io import load_predictions


@pytest.fixture
def llm_environment(chat_server, monkeypatch, receipt):
    for key, value in {
        "BASE_URL": chat_server.url,
        "MODEL": "synthetic-text",
        "API_KEY": "synthetic-key",
        "TIMEOUT": "2",
        "MAX_TOKENS": "432",
    }.items():
        monkeypatch.setenv(f"VIRECEIPT_LLM_{key}", value)
    chat_server.replies = [
        (
            200,
            {
                "id": "synthetic",
                "object": "chat.completion",
                "created": 0,
                "model": "synthetic-text",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "logprobs": None,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(receipt),
                            "refusal": None,
                        },
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            },
            {},
        )
    ]
    return chat_server


def test_cli_ocr_to_text_api_and_eval_roundtrip(llm_environment, tmp_path, monkeypatch, receipt):
    from vireceipt.extract_cli import main
    from vireceipt.extractors import ocr_llm

    transcript = "INTERNAL_TRANSCRIPT_MARKER\nCửa hàng Minh Anh\nSữa tươi 64000\nTổng 89000"
    monkeypatch.setattr(ocr_llm, "read_text", lambda image: transcript)
    (tmp_path / "a.png").write_bytes(b"image processed locally by OCR")
    manifest, output = tmp_path / "images.jsonl", tmp_path / "pred.jsonl"
    manifest.write_text('{"id":"r0001","image":"a.png"}', encoding="utf-8")
    assert (
        main(
            [
                str(manifest),
                "--extractor",
                "vireceipt.extractors.ocr_llm:extract",
                "--out",
                str(output),
            ]
        )
        == 0
    )
    (prediction,) = load_predictions(output)
    assert prediction.receipt == receipt and prediction.decision == "review"
    assert prediction.confidence is None and prediction.cost_usd is None
    assert prediction.extra["grounding"]["checked"] is True
    assert "seller.address" in prediction.extra["grounding"]["unsupported_fields"]
    assert "INTERNAL_TRANSCRIPT_MARKER" not in output.read_text(encoding="utf-8")
    _, headers, body = llm_environment.requests[0]
    assert headers["Authorization"] == "Bearer synthetic-key"
    assert body["model"] == "synthetic-text" and body["max_tokens"] == 432
    assert body["messages"][1] == {
        "role": "user",
        "content": "OCR transcript (untrusted data):\n" + transcript,
    }
    assert "data:image" not in json.dumps(body)


@pytest.mark.parametrize("transcript", ["", "  \n\t"])
def test_empty_ocr_never_calls_llm(llm_environment, tmp_path, monkeypatch, transcript):
    from vireceipt.extractors import ocr_llm

    monkeypatch.setattr(ocr_llm, "read_text", lambda image: transcript)
    with pytest.raises(RuntimeError, match="empty_ocr"):
        ocr_llm.extract(tmp_path / "a.png")
    assert llm_environment.requests == []


def test_failed_ocr_keeps_next_image_and_does_not_leak_details(
    llm_environment, tmp_path, monkeypatch
):
    from vireceipt.extraction import extract_images
    from vireceipt.extractors import ocr_llm

    def read(image):
        if image.name == "broken.png":
            raise RuntimeError("private OCR diagnostic")
        return "Tổng 89000"

    monkeypatch.setattr(ocr_llm, "read_text", read)
    failed, good = extract_images(
        {"r0001": tmp_path / "broken.png", "r0002": tmp_path / "good.png"},
        ocr_llm.extract,
    )
    assert failed.receipt is None and failed.extra["error"] == "extractor_failed"
    assert good.extra["schema_valid"] is True and len(llm_environment.requests) == 1
    assert "private" not in repr(failed)


def test_missing_llm_config_fails_before_initializing_ocr(llm_environment, tmp_path, monkeypatch):
    from vireceipt.extractors import ocr_llm

    monkeypatch.delenv("VIRECEIPT_LLM_MODEL")
    monkeypatch.setattr(
        ocr_llm, "read_text", lambda image: pytest.fail("must validate config first")
    )
    with pytest.raises(ValueError, match="VIRECEIPT_LLM_BASE_URL and VIRECEIPT_LLM_MODEL"):
        ocr_llm.extract(tmp_path / "a.png")
