import math

import pytest


def answer(content="{}", finish="stop", **message):
    return {
        "id": "synthetic-completion",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "logprobs": None,
                "message": {"role": "assistant", "content": content, "refusal": None, **message},
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
    }


def test_real_http_client_sends_explicit_model_and_returns_content(chat_server):
    from vireceipt.extractors.chat_api import ChatClient

    chat_server.replies = [(200, answer('{"total":1}'), {})]
    client = ChatClient(chat_server.url, "test-model", api_key="synthetic-secret", max_tokens=123)
    messages = [{"role": "user", "content": "JSON only"}]
    assert client.complete(messages) == '{"total":1}'
    path, headers, body = chat_server.requests[0]
    assert path == "/v1/chat/completions"
    assert headers["Authorization"] == "Bearer synthetic-secret"
    assert body == {
        "model": "test-model",
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 123,
        "stream": False,
    }
    assert "synthetic-secret" not in repr(client)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"choices": []},
        answer(finish="length"),
        answer(finish="content_filter"),
        answer(content=None),
        answer(refusal="refused"),
        answer(tool_calls=[{"id": "call-1"}]),
        b"not json",
        pytest.param(b"x" * (4 * 1024 * 1024 + 1), id="oversized-response"),
    ],
)
def test_bad_api_response_is_one_sanitized_failure(chat_server, response):
    from vireceipt.extractors.chat_api import ChatAPIError, ChatClient

    chat_server.replies = [(200, response, {})]
    with pytest.raises(ChatAPIError, match="^invalid_response$"):
        ChatClient(chat_server.url, "test-model").complete([])


@pytest.mark.parametrize("status", [401, 429, 500, 301, 302, 303, 307, 308])
def test_http_errors_do_not_retry_follow_redirect_or_disclose_body(chat_server, status):
    from vireceipt.extractors.chat_api import ChatAPIError, ChatClient

    chat_server.replies = [
        (status, b"secret diagnostic body", {"Location": chat_server.url + "/other"})
    ]
    with pytest.raises(ChatAPIError) as caught:
        ChatClient(chat_server.url, "test-model", api_key="synthetic-secret").complete([])
    assert "secret" not in str(caught.value) and len(chat_server.requests) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"base_url": "http://example.com/v1"},
        {"base_url": "https://user:secret@example.com/v1"},
        {"base_url": "https://example.com/v1?secret=value"},
        {"base_url": "https://example.com/v1#x"},
        {"model": ""},
        {"timeout": 0},
        {"timeout": math.inf},
        {"timeout": True},
        {"max_tokens": 0},
        {"max_tokens": True},
    ],
)
def test_invalid_configuration_is_rejected_before_network(changes):
    from vireceipt.extractors.chat_api import ChatClient

    with pytest.raises(ValueError):
        ChatClient(**({"base_url": "https://example.com/v1", "model": "test"} | changes))
