import os
from pathlib import Path
from urllib.parse import urlsplit

from claims_assistant.config import Settings
from claims_assistant.interfaces.web import create_app
from claims_assistant.rag.ingest import ingest


def create_vercel_app(root: Path | None = None):
    root = root or Path(__file__).resolve().parents[3]
    settings = Settings(root=root, runtime_dir=Path("/tmp/claims-assistant"))
    if settings.app_mode != "private" or not settings.api_token:
        raise ValueError("Vercel requires CLAIMS_APP_MODE=private and CLAIMS_API_TOKEN")
    if not settings.database_url:
        raise ValueError("Vercel requires persistent storage: set CLAIMS_DATABASE_URL")
    if settings.llm_mode == "ollama" and urlsplit(settings.llm_base_url).hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("Vercel cannot run local Ollama; use demo mode or an external HTTPS model")
    settings.llm_timeout = min(settings.llm_timeout, 10)
    hosts = list(settings.allowed_hosts)
    for name in ["VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_BRANCH_URL"]:
        if os.environ.get(name):
            hosts.append(os.environ[name])
    settings.allowed_hosts = list(set(hosts))
    settings.prepare()
    ingest(settings)  # Rebuild per cold start; user data lives in PostgreSQL.
    return create_app(settings)
