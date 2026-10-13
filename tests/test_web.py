from html import unescape
from pathlib import Path

from conftest import mileage
from fastapi.testclient import TestClient

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
