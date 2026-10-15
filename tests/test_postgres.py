import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from conftest import TODAY, mileage
from fastapi.testclient import TestClient
from psycopg import sql
from pydantic import SecretStr

from claims_assistant.agent.runner import Assistant
from claims_assistant.interfaces.vercel import create_vercel_app
from claims_assistant.interfaces.web import create_app
from claims_assistant.services.policy_rules import PolicyRules
from claims_assistant.storage.repository import ConflictError
from claims_assistant.tools.save_draft import save_draft


@pytest.fixture
def postgres_settings(settings):
    url = os.environ.get("CLAIMS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set CLAIMS_TEST_DATABASE_URL for PostgreSQL integration checks")
    schema = "claims_test_" + uuid4().hex
    with psycopg.connect(url) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query))
    query["options"] = "-csearch_path=" + schema
    settings.database_url = SecretStr(urlunsplit(parsed._replace(query=urlencode(query))))
    try:
        yield settings
    finally:
        with psycopg.connect(url) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_postgres_save_resume_and_revision(postgres_settings):
    assistant = Assistant(postgres_settings, today=TODAY)
    response = assistant.respond(fields=mileage().model_dump(mode="json", exclude={"receipt"}))
    saved = assistant.respond(
        session_id=response.state.session_id,
        expected_revision=response.state.revision,
        confirm=True,
    )
    assert saved.state.status == "saved"
    second_instance = Assistant(postgres_settings, today=TODAY)
    assert second_instance.repository.load(saved.state.session_id) == saved.state
    assert (
        second_instance.repository.draft(saved.state.draft_id)["calculation"]["amount"] == "15.00"
    )
    with pytest.raises(ConflictError):
        second_instance.respond(
            session_id=response.state.session_id,
            expected_revision=response.state.revision,
            confirm=True,
        )
    assert not (postgres_settings.runtime / "claims.db").exists()


def test_postgres_receipt_race_rolls_back(postgres_settings):
    assistant = Assistant(postgres_settings, today=TODAY)
    fields = {
        "employee_id": "DEMO001",
        "category": "meal",
        "expense_date": str(TODAY),
        "purpose": "Client lunch",
        "business_expense": True,
        "amount": "25.00",
    }
    states = []
    for _ in range(2):
        extracted = assistant.respond(
            fields=fields, receipt_text="Merchant: Postgres Cafe\nDate: 2026-10-13\nTotal: RM25.00"
        )
        reviewed = assistant.respond(
            session_id=extracted.state.session_id,
            expected_revision=extracted.state.revision,
            confirm_receipt=True,
        )
        states.append(reviewed.state)
    rules = PolicyRules(postgres_settings.root)
    proposals = [save_draft(s, rules, assistant.repository, TODAY, True).data for s in states]
    for state, proposal in zip(states, proposals, strict=True):
        state.status, state.draft_id = "saved", proposal["id"]
    assistant.repository.commit(states[0], states[0].revision, proposals[0])
    with pytest.raises(ConflictError, match="Duplicate"):
        assistant.repository.commit(states[1], states[1].revision, proposals[1])
    stored = assistant.repository.load(states[1].session_id)
    assert stored.status == "ready" and stored.draft_id is None


def test_postgres_api_private_flow(postgres_settings):
    postgres_settings.app_mode, postgres_settings.api_token = "private", "postgres-test-only"
    with TestClient(create_app(postgres_settings), base_url="https://localhost") as web:
        headers = {"Authorization": "Bearer postgres-test-only"}
        assert web.get("/api/health", headers=headers).status_code == 200
        response = web.post(
            "/api/chat",
            headers=headers,
            json={"fields": mileage().model_dump(mode="json", exclude={"receipt"})},
        )
        state = response.json()["state"]
        saved = web.post(
            "/api/chat",
            headers=headers,
            json={
                "session_id": state["session_id"],
                "expected_revision": state["revision"],
                "confirm": True,
            },
        )
        assert saved.json()["state"]["status"] == "saved"


def test_vercel_cold_start_uses_external_storage(postgres_settings, monkeypatch):
    postgres_settings.app_mode, postgres_settings.api_token = "private", "postgres-test-only"
    monkeypatch.setattr(
        "claims_assistant.interfaces.vercel.Settings", lambda **_: postgres_settings
    )
    monkeypatch.setenv("VERCEL_URL", "claims-test.vercel.app")
    first = create_vercel_app()
    with TestClient(first, base_url="https://claims-test.vercel.app") as client:
        assert client.get("/").status_code == 200
        headers = {
            "Authorization": "Bearer postgres-test-only",
            "Origin": "https://claims-test.vercel.app",
        }
        assert client.get("/api/health", headers=headers).status_code == 200
        created = client.post("/api/sessions", headers=headers).json()
    # Removing transient files must not remove the session in PostgreSQL.
    (postgres_settings.runtime / "vector_index/policies.json").unlink()
    second = create_vercel_app()
    with TestClient(second, base_url="https://claims-test.vercel.app") as client:
        response = client.get("/api/sessions/" + created["session_id"], headers=headers)
        assert (
            response.status_code == 200 and response.json()["session_id"] == created["session_id"]
        )


def test_public_vercel_postgres_ownership_survives_cold_start(postgres_settings, monkeypatch):
    postgres_settings.app_mode, postgres_settings.api_token = "public", ""
    monkeypatch.setattr(
        "claims_assistant.interfaces.vercel.Settings", lambda **_: postgres_settings
    )
    monkeypatch.setenv("VERCEL_URL", "claims-test.vercel.app")
    url = "https://claims-test.vercel.app"
    with TestClient(create_vercel_app(), base_url=url) as owner:
        state = owner.post(
            "/api/chat", json={"fields": mileage().model_dump(mode="json", exclude={"receipt"})}
        ).json()["state"]
        saved = owner.post(
            "/api/chat",
            json={
                "session_id": state["session_id"],
                "expected_revision": state["revision"],
                "confirm": True,
            },
        ).json()["state"]
        visitor = owner.cookies["claims_visitor"]
    (postgres_settings.runtime / "vector_index/policies.json").unlink()
    second_app = create_vercel_app()
    with (
        TestClient(second_app, base_url=url) as resumed,
        TestClient(second_app, base_url=url) as other,
    ):
        resumed.cookies.set("claims_visitor", visitor)
        session_url = "/api/sessions/" + saved["session_id"]
        draft_url = "/api/drafts/" + saved["draft_id"]
        assert resumed.get(session_url).json()["status"] == "saved"
        assert resumed.get(draft_url).json()["calculation"]["amount"] == "15.00"
        assert other.get(session_url).status_code == 404
        assert other.get(draft_url).status_code == 404
        assert (
            other.post(
                "/api/chat", json={"session_id": saved["session_id"], "message": "new"}
            ).status_code
            == 404
        )
