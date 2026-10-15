import hmac
import re
import secrets
from hashlib import sha256
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from claims_assistant.agent.runner import Assistant
from claims_assistant.agent.state import AgentResponse, AgentState
from claims_assistant.config import Settings
from claims_assistant.rag.ingest import source_digest
from claims_assistant.rag.vector_store import VectorStore
from claims_assistant.storage.repository import ConflictError

VISITOR_COOKIE = "claims_visitor"


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    message: str = Field(default="", max_length=4000)
    fields: dict | None = None
    receipt_text: str | None = Field(default=None, max_length=20000)
    receipt_image: str | None = Field(default=None, max_length=7_000_000)
    receipt_ocr_text: str | None = Field(default=None, min_length=1, max_length=20000)
    receipt_fields: dict | None = None
    confirm_receipt: bool = False
    confirm: bool = False


def create_app(settings: Settings | None = None, *, public_https: bool = False) -> FastAPI:
    settings = settings or Settings()
    assistant = Assistant(settings)
    app = FastAPI(title="Allowance Assistant", version="0.1.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.mount(
        "/assets/ocr",
        StaticFiles(directory=Path(__file__).with_name("static") / "ocr"),
        name="browser-ocr",
    )

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if (
            settings.app_mode != "public"
            and settings.api_token
            and not hmac.compare_digest(authorization or "", "Bearer " + settings.api_token)
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
        # Vercel terminates HTTPS before forwarding to the Python function.
        # Its public origin remains HTTPS even if the ASGI scope says HTTP.
        # Keep the actual request host and do not trust arbitrary forwarded headers.
        public_url = request.base_url.replace(scheme="https") if public_https else request.base_url
        if origin and origin != str(public_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin requests are disabled"}, status_code=403)
        # An anonymous browser capability, not an employee identity. Only its hash
        # is persisted; knowing a session/draft UUID never grants public access.
        visitor = None
        request.state.owner_hash = None
        if settings.app_mode == "public" and (
            request.url.path == "/" or request.url.path.startswith("/api/")
        ):
            visitor = request.cookies.get(VISITOR_COOKIE, "")
            if not re.fullmatch(r"[A-Za-z0-9_-]{43}", visitor):
                visitor = secrets.token_urlsafe(32)
            request.state.owner_hash = sha256(visitor.encode("ascii")).hexdigest()
        response = await call_next(request)
        if visitor is not None and visitor != request.cookies.get(VISITOR_COOKIE):
            response.set_cookie(
                VISITOR_COOKIE,
                visitor,
                max_age=60 * 60 * 24 * 30,
                httponly=True,
                secure=public_https or request.url.scheme == "https",
                samesite="strict",
            )
        response.headers["Cache-Control"] = (
            "public, max-age=86400"
            if request.url.path.startswith("/assets/ocr/6.0.1/")
            else "no-store"
        )
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
        return {
            "status": "ok",
            "app_mode": settings.app_mode,
            "llm_mode": settings.llm_mode,
            "llm_model": settings.llm_model,
            "llm_timeout_seconds": settings.llm_timeout,
            "fictional_policy": True,
            "receipt_image_backend": settings.receipt_image_backend,
        }

    @app.post("/api/sessions", response_model=AgentState, dependencies=[Depends(authorize)])
    def create_session(request: Request):
        return assistant.repository.create(request.state.owner_hash)

    @app.get(
        "/api/sessions/{session_id}", response_model=AgentState, dependencies=[Depends(authorize)]
    )
    def session(session_id: UUID, request: Request):
        try:
            return assistant.repository.load(str(session_id), request.state.owner_hash)
        except KeyError:
            raise HTTPException(404, "Session not found") from None

    @app.post("/api/chat", response_model=AgentResponse, dependencies=[Depends(authorize)])
    def chat(body: ChatRequest, request: Request):
        if (body.confirm or body.message.strip().casefold() == "confirm") and (
            body.session_id is None or body.expected_revision is None
        ):
            raise HTTPException(422, "Confirmation requires session_id and expected_revision")
        options = body.model_dump(exclude={"session_id"})
        try:
            return assistant.respond(
                session_id=str(body.session_id) if body.session_id else None,
                owner_hash=request.state.owner_hash,
                **options,
            )
        except KeyError:
            raise HTTPException(404, "Session not found") from None
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/api/drafts/{draft_id}", dependencies=[Depends(authorize)])
    def draft(draft_id: UUID, request: Request):
        try:
            return assistant.repository.draft(str(draft_id), request.state.owner_hash)
        except KeyError:
            raise HTTPException(404, "Draft not found") from None

    return app
