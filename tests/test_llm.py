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
