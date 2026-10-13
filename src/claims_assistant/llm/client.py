import json
from urllib.parse import urlsplit

import httpx

from claims_assistant.config import Settings


class ModelError(RuntimeError):
    pass


class ModelClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        url = urlsplit(settings.llm_base_url)
        if url.username or url.password:
            raise ValueError("Do not embed credentials in model URLs")
        if url.scheme != "https" and not (
            url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError("Model endpoints require HTTPS except on loopback")
        if settings.llm_mode == "openai" and not settings.llm_api_key:
            raise ValueError("OpenAI-compatible hosted mode requires CLAIMS_LLM_API_KEY")

    def completion(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 1000,
        }
        if tools:
            payload["tools"] = tools
        else:
            payload["response_format"] = {"type": "json_object"}
        headers = {}
        if self.settings.llm_api_key:
            headers["Authorization"] = "Bearer " + self.settings.llm_api_key
        try:
            # Do not route private loopback requests through the cloud egress proxy.
            local = urlsplit(self.settings.llm_base_url).hostname in {
                "127.0.0.1",
                "localhost",
                "::1",
            }
            with httpx.Client(timeout=self.settings.llm_timeout, trust_env=not local) as client:
                response = client.post(
                    self.settings.llm_base_url.rstrip("/") + "/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
                if not isinstance(message, dict) or not isinstance(
                    message.get("tool_calls") or [], list
                ):
                    raise ValueError("Malformed model message")
                return message
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            # Provider response bodies may include personal data or credentials.
            raise ModelError(
                "Model request failed; check endpoint, model, and service logs"
            ) from exc

    def receipt(self, instructions: str, content: str | list[dict]) -> dict:
        message = self.completion(
            [{"role": "system", "content": instructions}, {"role": "user", "content": content}]
        )
        try:
            data = json.loads(message.get("content") or "")
            allowed = {"merchant", "expense_date", "total", "currency", "receipt_number"}
            if not isinstance(data, dict) or set(data) - allowed:
                raise ValueError("Unexpected receipt fields")
            return data
        except (ValueError, TypeError) as exc:
            raise ModelError("Model returned malformed receipt data") from exc
