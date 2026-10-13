import hmac
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from claims_assistant.agent.runner import Assistant
from claims_assistant.agent.state import AgentResponse, AgentState
from claims_assistant.config import Settings
from claims_assistant.rag.ingest import source_digest
from claims_assistant.rag.vector_store import VectorStore
from claims_assistant.storage.repository import ConflictError


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    message: str = Field(default="", max_length=4000)
    fields: dict | None = None
    receipt_text: str | None = Field(default=None, max_length=20000)
    receipt_image: str | None = Field(default=None, max_length=7_000_000)
    receipt_fields: dict | None = None
    confirm_receipt: bool = False
    confirm: bool = False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    assistant = Assistant(settings)
    app = FastAPI(title="Allowance Assistant", version="0.1.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if settings.api_token and not hmac.compare_digest(
            authorization or "", "Bearer " + settings.api_token
        ):
            raise HTTPException(401, "A valid service token is required")

    @app.middleware("http")
    async def protect_local_app(request, call_next):
        from fastapi.responses import JSONResponse

        # The demo is single-user and loopback-only. This is not employee SSO.
        if (
            settings.app_mode == "demo"
            and request.client
            and request.client.host not in {"127.0.0.1", "::1", "localhost"}
        ):
            return JSONResponse({"detail": "Demo mode is loopback-only"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin requests are disabled"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home():
        return Path(__file__).with_name("web.html").read_text(encoding="utf-8")

    @app.get("/api/health", dependencies=[Depends(authorize)])
    def health():
        try:
            index = VectorStore(settings.runtime / "vector_index/policies.json").read()
            if index["source_digest"] != source_digest(settings.root):
                raise ValueError("Stale policy index")
        except (ValueError, OSError, KeyError):
            raise HTTPException(503, "Run claims ingest to refresh policy search") from None
        return {"status": "ok", "llm_mode": settings.llm_mode, "fictional_policy": True}

    @app.post("/api/sessions", response_model=AgentState, dependencies=[Depends(authorize)])
    def create_session():
        return assistant.repository.create()

    @app.get(
        "/api/sessions/{session_id}", response_model=AgentState, dependencies=[Depends(authorize)]
    )
    def session(session_id: UUID):
        try:
            return assistant.repository.load(str(session_id))
        except KeyError:
            raise HTTPException(404, "Session not found") from None

    @app.post("/api/chat", response_model=AgentResponse, dependencies=[Depends(authorize)])
    def chat(body: ChatRequest):
        if (body.confirm or body.message.strip().casefold() == "confirm") and (
            body.session_id is None or body.expected_revision is None
        ):
            raise HTTPException(422, "Confirmation requires session_id and expected_revision")
        options = body.model_dump(exclude={"session_id"})
        try:
            return assistant.respond(
                session_id=str(body.session_id) if body.session_id else None, **options
            )
        except KeyError:
            raise HTTPException(404, "Session not found") from None
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/api/drafts/{draft_id}", dependencies=[Depends(authorize)])
    def draft(draft_id: UUID):
        try:
            return assistant.repository.draft(str(draft_id))
        except KeyError:
            raise HTTPException(404, "Draft not found") from None

    return app
