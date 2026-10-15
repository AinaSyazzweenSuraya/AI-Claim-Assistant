from hashlib import sha256

from conftest import mileage
from fastapi.testclient import TestClient

from claims_assistant.agent.runner import Assistant
from claims_assistant.interfaces.web import VISITOR_COOKIE, create_app
from claims_assistant.storage.database import connect


def public_client(settings):
    settings.app_mode = "public"
    return TestClient(
        create_app(settings, public_https=True),
        base_url="https://localhost",
        client=("198.51.100.20", 50000),
    )


def test_public_no_token_save_export_and_separate_visitors(settings):
    # A leftover private-mode token must not gate explicit public access.
    settings.api_token = "unused-private-test-token"
    with public_client(settings) as owner, public_client(settings) as other:
        health = owner.get("/api/health")
        assert health.status_code == 200 and health.json()["app_mode"] == "public"
        assert owner.get("/").status_code == 200
        created = owner.post(
            "/api/chat", json={"fields": mileage().model_dump(mode="json", exclude={"receipt"})}
        )
        state = created.json()["state"]
        assert state["status"] == "ready"
        session_url = "/api/sessions/" + state["session_id"]
        assert other.get(session_url).status_code == 404
        confirmation = {
            "session_id": state["session_id"],
            "expected_revision": state["revision"],
            "confirm": True,
        }
        assert other.post("/api/chat", json=confirmation).status_code == 404
        assert (
            other.post(
                "/api/chat", json={"session_id": state["session_id"], "message": "new"}
            ).status_code
            == 404
        )
        assert owner.get(session_url).json() == state
        saved = owner.post("/api/chat", json=confirmation).json()["state"]
        assert saved["status"] == "saved"
        draft_url = "/api/drafts/" + saved["draft_id"]
        exported = owner.get(draft_url).json()
        assert exported["calculation"]["amount"] == "15.00" and not exported["submitted"]
        assert other.get(draft_url).status_code == 404
        other_session = other.post("/api/sessions").json()["session_id"]
        assert owner.get("/api/sessions/" + other_session).status_code == 404
        assert other.get("/api/sessions/" + other_session).status_code == 200
        assert owner.cookies[VISITOR_COOKIE] != other.cookies[VISITOR_COOKIE]


def test_public_cookie_is_persistent_httponly_and_only_hash_is_stored(settings):
    with public_client(settings) as web:
        response = web.get("/")
        cookie = response.headers["set-cookie"]
        for attribute in ["HttpOnly", "Secure", "SameSite=strict", "Max-Age=2592000", "Path=/"]:
            assert attribute in cookie
        visitor = web.cookies[VISITOR_COOKIE]
        session = web.post("/api/sessions").json()
        assert visitor not in str(session) and "owner_hash" not in session
        assert "set-cookie" not in web.get("/api/health").headers
        with connect(settings.runtime / "claims.db") as database:
            row = database.execute(
                "SELECT owner_hash FROM session_owners WHERE session_id=?",
                (session["session_id"],),
            ).fetchone()
        assert row["owner_hash"] == sha256(visitor.encode()).hexdigest()
    with public_client(settings) as restarted:
        restarted.cookies.set(VISITOR_COOKIE, visitor)
        assert restarted.get("/api/sessions/" + session["session_id"]).json() == session
        restarted.cookies.clear()
        assert restarted.get("/api/sessions/" + session["session_id"]).status_code == 404


def test_public_cannot_claim_legacy_unowned_records(settings):
    assistant = Assistant(settings)
    legacy = assistant.respond(fields=mileage().model_dump(mode="json", exclude={"receipt"})).state
    saved = assistant.respond(
        session_id=legacy.session_id, expected_revision=legacy.revision, confirm=True
    ).state
    with public_client(settings) as web:
        assert web.get("/api/sessions/" + legacy.session_id).status_code == 404
        assert web.get("/api/drafts/" + saved.draft_id).status_code == 404
        assert (
            web.post(
                "/api/chat",
                json={"session_id": legacy.session_id, "message": "new"},
            ).status_code
            == 404
        )
    assert assistant.repository.load(saved.session_id).status == "saved"


def test_public_cookie_validation_and_origin_checks(settings):
    with public_client(settings) as web:
        web.cookies.set(VISITOR_COOKIE, "invalid-cookie")
        response = web.get("/api/health")
        assert len(response.cookies[VISITOR_COOKIE]) == 43
        web.cookies.clear()
        blocked = web.post("/api/sessions", headers={"Origin": "https://elsewhere.example"})
        assert blocked.status_code == 403 and "set-cookie" not in blocked.headers
        assert web.post("/api/sessions", headers={"Origin": "https://localhost"}).status_code == 200


def test_public_identity_cannot_be_overridden_in_chat_json(settings):
    with public_client(settings) as web:
        assert web.post("/api/chat", json={"owner_hash": "attacker"}).status_code == 422
