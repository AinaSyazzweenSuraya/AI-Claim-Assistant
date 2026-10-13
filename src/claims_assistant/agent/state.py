from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from claims_assistant.schemas.claim import Calculation, Claim, ValidationReport


class AgentState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    revision: int = 0
    status: Literal["collecting", "invalid", "ready", "saved"] = "collecting"
    claim: Claim = Field(default_factory=Claim)
    validation: ValidationReport | None = None
    calculation: Calculation | None = None
    citations: list[dict] = Field(default_factory=list)
    history: list[dict[str, str]] = Field(default_factory=list)
    draft_id: str | None = None


class AgentResponse(BaseModel):
    state: AgentState
    message: str
    tools: list[dict] = Field(default_factory=list)
