from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from claims_assistant.interfaces.vercel import create_vercel_app
from claims_assistant.storage.database import connect


def test_vercel_requires_auth_and_persistent_database(settings, monkeypatch):
    monkeypatch.setattr("claims_assistant.interfaces.vercel.Settings", lambda **_: settings)
    with pytest.raises(ValueError, match="private"):
        create_vercel_app()
    settings.app_mode, settings.api_token = "private", "test-only-token"
    with pytest.raises(ValueError, match="persistent storage"):
        create_vercel_app()
    settings.database_url = SecretStr("postgresql://example.invalid/claims")
    settings.llm_mode = "ollama"
    with pytest.raises(ValueError, match="cannot run local Ollama"):
        create_vercel_app()


def test_remote_postgres_enforces_tls_verification(tmp_path, monkeypatch):
    raw = Mock()
    open_connection = Mock(return_value=raw)
    monkeypatch.setattr("claims_assistant.storage.database.psycopg.connect", open_connection)
    # Even weaker TLS preferences in a supplied URL cannot turn verification off.
    connection = connect(
        tmp_path / "unused.db", "postgresql://example.invalid/claims?sslmode=disable"
    )
    options = open_connection.call_args.kwargs
    assert options["sslmode"] == "verify-full" and options["sslrootcert"]
    connection.close()


def test_vercel_adapter_sets_https_public_origin(settings, monkeypatch):
    settings.app_mode, settings.api_token = "private", "test-only-token"
    settings.database_url = SecretStr("postgresql://example.invalid/claims")
    monkeypatch.setattr("claims_assistant.interfaces.vercel.Settings", lambda **_: settings)
    factory = Mock()
    monkeypatch.setattr("claims_assistant.interfaces.vercel.create_app", factory)
    assert create_vercel_app() is factory.return_value
    factory.assert_called_once_with(settings, public_https=True)


def test_vercel_public_mode_requires_database_but_no_token(settings, monkeypatch):
    settings.app_mode, settings.api_token = "public", ""
    monkeypatch.setattr("claims_assistant.interfaces.vercel.Settings", lambda **_: settings)
    with pytest.raises(ValueError, match="persistent storage"):
        create_vercel_app()
    settings.database_url = SecretStr("postgresql://example.invalid/claims")
    factory = Mock()
    monkeypatch.setattr("claims_assistant.interfaces.vercel.create_app", factory)
    assert create_vercel_app() is factory.return_value
    factory.assert_called_once_with(settings, public_https=True)


def test_vercel_rejects_local_florence_before_loading_models(settings, monkeypatch):
    settings.app_mode, settings.api_token = "private", "test-only-token"
    settings.database_url = SecretStr("postgresql://example.invalid/claims")
    settings.receipt_image_backend = "florence"
    monkeypatch.setattr("claims_assistant.interfaces.vercel.Settings", lambda **_: settings)
    factory = Mock()
    monkeypatch.setattr("claims_assistant.interfaces.vercel.create_app", factory)
    with pytest.raises(ValueError, match="Local Florence OCR"):
        create_vercel_app()
    factory.assert_not_called()
