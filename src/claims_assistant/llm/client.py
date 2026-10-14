import json
from urllib.parse import urlsplit

import httpx

from claims_assistant.config import Settings


class ModelError(RuntimeError):
    pass


def _provider_error(response: httpx.Response) -> str:
    """Describe provider failures without exposing response bodies or credentials."""
    status = response.status_code
    known_codes = {
        "model_decommissioned": "The configured model has been retired; choose an available model",
        "model_not_found": "The configured model is unavailable or inaccessible to this API key",
        "json_validate_failed": "The provider could not generate valid JSON receipt fields",
        "tool_use_failed": "The provider could not generate valid agent tool calls",
    }
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
    except ValueError:
        code = None
    if isinstance(code, str) and code in known_codes:
        return f"{known_codes[code]} (HTTP {status})"
    messages = {
        400: "Model provider rejected the request; check image, JSON, and tool support",
        401: "Model provider rejected CLAIMS_LLM_API_KEY; check the provider key in Production",
        402: "Model provider requires credits or billing access for this request",
        403: "Model provider denied access; check API key permissions and model access",
        404: "Model endpoint or model was not found; check the base URL and exact model ID",
        413: "Model provider rejected the image or request size; try a smaller receipt image",
        422: "Model provider rejected the request format; check image, JSON, and tool support",
        429: "Model provider rate limit or quota reached; check usage before retrying",
    }
    message = messages.get(status)
    if message is None:
        message = (
            "Model provider is unavailable; check its service status before retrying"
            if status >= 500
            else "Model provider request failed; check provider settings"
        )
    return f"{message} (HTTP {status})"


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
        except httpx.TimeoutException as exc:
            raise ModelError(
                f"Model provider timed out (timeout: {self.settings.llm_timeout:g} seconds); "
                "try a smaller receipt image and check provider response time"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ModelError(_provider_error(exc.response)) from exc
        except httpx.HTTPError as exc:
            raise ModelError(
                "Could not connect to the model provider; "
                "check the endpoint and service availability"
            ) from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelError(
                "Model provider returned an invalid response; "
                "expected OpenAI-compatible chat output"
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
