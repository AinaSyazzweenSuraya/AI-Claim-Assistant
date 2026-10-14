import base64
import io
import json
from html import unescape
from pathlib import Path

import httpx
from conftest import mileage
from fastapi.testclient import TestClient
from PIL import Image

from claims_assistant.interfaces.web import create_app


def client(settings):
    return TestClient(
        create_app(settings), base_url="http://localhost", client=("127.0.0.1", 50000)
    )


def test_api_complete_draft_and_revision_conflict(settings):
    with client(settings) as web:
        assert web.get("/").status_code == 200
        assert web.get("/api/health").json()["status"] == "ok"
        response = web.post(
            "/api/chat", json={"fields": mileage().model_dump(mode="json", exclude={"receipt"})}
        )
        state = response.json()["state"]
        assert state["status"] == "ready"
        saved = web.post(
            "/api/chat",
            json={
                "session_id": state["session_id"],
                "expected_revision": state["revision"],
                "confirm": True,
            },
        )
        draft_id = saved.json()["state"]["draft_id"]
        assert web.get("/api/drafts/" + draft_id).json()["calculation"]["amount"] == "15.00"
        assert (
            web.post(
                "/api/chat",
                json={
                    "session_id": state["session_id"],
                    "expected_revision": state["revision"],
                    "confirm": True,
                },
            ).status_code
            == 409
        )
        assert web.post("/api/chat", json={"confirm": True}).status_code == 422


def test_private_api_authentication(settings):
    settings.app_mode, settings.api_token = "private", "test-only-token"
    with client(settings) as web:
        assert web.get("/api/health").status_code == 401
        assert web.get("/api/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert (
            web.get("/api/health", headers={"Authorization": "Bearer test-only-token"}).status_code
            == 200
        )


def test_authenticated_health_reports_active_model_without_keys(settings):
    settings.app_mode, settings.api_token = "private", "test-only-token"
    settings.llm_mode, settings.llm_api_key = "openai", "fake-model-key"
    settings.llm_model = "test-vision-model"
    settings.llm_timeout = 10
    with client(settings) as web:
        assert web.get("/api/health").status_code == 401
        response = web.get("/api/health", headers={"Authorization": "Bearer test-only-token"})
        health = response.json()
        assert health["llm_model"] == "test-vision-model"
        assert health["llm_mode"] == "openai" and health["receipt_image_backend"] == "vision"
        assert health["llm_timeout_seconds"] == 10
        assert "fake-model-key" not in response.text and "test-only-token" not in response.text


def test_image_api_reports_provider_failure_and_recovers_without_confirming_evidence(
    settings, monkeypatch
):
    settings.llm_mode, settings.llm_api_key = "openai", "fake-model-key"
    settings.llm_base_url = "https://provider.example/v1"
    settings.llm_model = "test-vision-model"
    provider_status = 429
    stream = io.BytesIO()
    with Image.new("RGB", (32, 48), "white") as image:
        image.save(stream, format="PNG")
    encoded_image = base64.b64encode(stream.getvalue()).decode()
    real_client = httpx.Client

    def respond(request):
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert payload["model"] == "test-vision-model"
        assert payload["response_format"] == {"type": "json_object"}
        content = payload["messages"][1]["content"]
        assert content[1]["image_url"]["url"] == "data:image/png;base64," + encoded_image
        if provider_status != 200:
            return httpx.Response(
                provider_status, json={"error": {"message": "SECRET-KEY private-receipt-data"}}
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "merchant": "Fictional Cafe",
                                    "expense_date": "2026-10-14",
                                    "total": "45.00",
                                    "currency": "MYR",
                                    "receipt_number": "TEST-IMAGE-001",
                                }
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    with client(settings) as web:
        response = web.post("/api/chat", json={"receipt_image": encoded_image})
        assert response.status_code == 200
        failed = response.json()
        assert "HTTP 429" in failed["message"]
        assert "private-receipt-data" not in response.text and "SECRET-KEY" not in response.text
        assert failed["state"]["claim"]["receipt"] is None
        assert failed["state"]["calculation"] is None and failed["state"]["draft_id"] is None
        assert any(
            tool["tool"] == "extract_receipt" and not tool["result"]["ok"]
            for tool in failed["tools"]
        )
        provider_status = 200
        recovered = web.post(
            "/api/chat",
            json={
                "receipt_image": encoded_image,
                "session_id": failed["state"]["session_id"],
                "expected_revision": failed["state"]["revision"],
            },
        ).json()
        receipt = recovered["state"]["claim"]["receipt"]
        assert receipt["merchant"] == "Fictional Cafe" and receipt["total"] == "45.00"
        assert receipt["extraction_method"] == "model_image" and receipt["confirmed"] is False
        assert recovered["state"]["calculation"] is None and recovered["state"]["draft_id"] is None


def test_cross_origin_and_unknown_session(settings):
    with client(settings) as web:
        assert (
            web.post("/api/sessions", headers={"Origin": "https://untrusted.example"}).status_code
            == 403
        )
        assert web.get("/api/sessions/00000000-0000-0000-0000-000000000000").status_code == 404
        assert web.post("/api/chat", json={"unknown": "field"}).status_code == 422


def test_health_reports_missing_index(settings):
    (settings.runtime / "vector_index/policies.json").unlink()
    with client(settings) as web:
        assert web.get("/api/health").status_code == 503


def test_public_https_accepts_same_origin_after_proxy_termination(settings):
    settings.app_mode, settings.api_token = "private", "test-only-token"
    settings.allowed_hosts = ["claims-test.vercel.app"]
    with TestClient(
        create_app(settings, public_https=True), base_url="http://claims-test.vercel.app"
    ) as web:
        headers = {"Authorization": "Bearer test-only-token"}
        assert web.get("/api/health", headers=headers).status_code == 200
        headers["Origin"] = "https://claims-test.vercel.app"
        response = web.post(
            "/api/chat",
            headers=headers,
            json={"fields": mileage().model_dump(mode="json", exclude={"receipt"})},
        )
        assert response.status_code == 200
        assert response.json()["state"]["calculation"]["amount"] == "15.00"
        for origin in ["https://untrusted.example", "http://claims-test.vercel.app"]:
            headers["Origin"] = origin
            assert web.post("/api/sessions", headers=headers).status_code == 403


def test_local_origin_policy_does_not_trust_forwarded_headers(settings):
    with client(settings) as web:
        assert web.post("/api/sessions", headers={"Origin": "http://localhost"}).status_code == 200
        assert (
            web.post(
                "/api/sessions",
                headers={"Origin": "https://localhost", "X-Forwarded-Proto": "https"},
            ).status_code
            == 403
        )


def test_windows_default_encoding_does_not_corrupt_the_page(settings, monkeypatch):
    original = Path.read_text

    def windows_read_text(path, encoding=None, errors=None):
        return original(path, encoding=encoding or "cp1252", errors=errors)

    monkeypatch.setattr(Path, "read_text", windows_read_text)
    with client(settings) as web:
        response = web.get("/")
        assert response.status_code == 200
        assert "charset=utf-8" in response.headers["content-type"]
        assert "We’ll check the policy" in unescape(response.text)
        assert "01 · Add details" in unescape(response.text)
        assert "Development policy · Fictional rates" in unescape(response.text)
        assert "â€™" not in response.text
        # Static HTML is also safe if a Windows tool reads it with a legacy encoding.
        template = Path(__file__).parents[1] / "src/claims_assistant/interfaces/web.html"
        assert template.read_text(encoding="cp1252") == template.read_text(encoding="utf-8")
