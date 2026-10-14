import json

import httpx
import pytest

from claims_assistant.llm.client import ModelClient, ModelError


@pytest.mark.parametrize("tool_calls", [[], None])
def test_local_provider_protocol(settings, monkeypatch, tool_calls):
    requests = []
    real_client = httpx.Client

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "{}", "tool_calls": tool_calls}}]}
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    settings.llm_mode = "ollama"
    result = ModelClient(settings).completion([{"role": "user", "content": "hello"}])
    assert result["content"] == "{}"
    assert requests[0].url.path == "/v1/chat/completions"
    assert "authorization" not in requests[0].headers
    assert json.loads(requests[0].content)["model"] == "llama3.2:3b"


def test_insecure_remote_endpoint_rejected(settings):
    settings.llm_base_url = "http://untrusted.example/v1"
    with pytest.raises(ValueError, match="HTTPS"):
        ModelClient(settings)


def test_bad_provider_response_is_sanitized(settings, monkeypatch):
    real_client = httpx.Client

    def respond(request):
        return httpx.Response(401, text="sensitive response never shown")

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    with pytest.raises(ModelError) as error:
        ModelClient(settings).completion([])
    assert "sensitive" not in str(error.value)


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (400, None, "check image, JSON, and tool support"),
        (401, None, "CLAIMS_LLM_API_KEY"),
        (402, None, "credits or billing"),
        (403, None, "denied access"),
        (404, None, "not found"),
        (413, None, "request size"),
        (422, None, "request format"),
        (429, None, "rate limit or quota"),
        (503, None, "provider is unavailable"),
        (418, None, "provider request failed"),
        (400, "model_decommissioned", "model has been retired"),
        (404, "model_not_found", "model is unavailable"),
        (400, "json_validate_failed", "valid JSON receipt fields"),
        (400, "tool_use_failed", "valid agent tool calls"),
        (400, "private-provider-code", "check image, JSON, and tool support"),
        (400, {"private": "private-provider-code"}, "check image, JSON, and tool support"),
    ],
)
def test_provider_failures_are_actionable_without_echoing_sensitive_data(
    settings, monkeypatch, status, code, expected
):
    real_client = httpx.Client

    def respond(request):
        return httpx.Response(
            status,
            json={
                "error": {"code": code, "message": "SECRET-KEY private-receipt-data"},
                "other": "SECRET-KEY private-receipt-data",
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    with pytest.raises(ModelError) as error:
        ModelClient(settings).completion([])
    message = str(error.value)
    assert expected in message and f"HTTP {status}" in message
    assert all(
        private not in message
        for private in ["SECRET-KEY", "private-receipt-data", "private-provider-code"]
    )


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (httpx.ReadTimeout, "timed out (timeout: 10 seconds)"),
        (httpx.ConnectError, "Could not connect"),
    ],
)
def test_transport_failures_distinguish_timeout_and_connection(
    settings, monkeypatch, failure, expected
):
    settings.llm_timeout = 10
    real_client = httpx.Client

    def respond(request):
        raise failure("SECRET-KEY private-receipt-data", request=request)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    with pytest.raises(ModelError) as error:
        ModelClient(settings).completion([])
    assert expected in str(error.value)
    assert "SECRET-KEY" not in str(error.value) and "private-receipt-data" not in str(error.value)


@pytest.mark.parametrize("body", [b"not-json SECRET-KEY", b"{}", b'{"choices": []}'])
def test_malformed_success_response_is_sanitized(settings, monkeypatch, body):
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)),
            **kwargs,
        ),
    )
    with pytest.raises(ModelError, match="invalid response") as error:
        ModelClient(settings).completion([])
    assert "SECRET-KEY" not in str(error.value)
