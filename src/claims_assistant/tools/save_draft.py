from datetime import date
from uuid import uuid4

from claims_assistant.agent.state import AgentState
from claims_assistant.schemas.tool_result import ToolResult
from claims_assistant.services.calculation import calculate
from claims_assistant.services.policy_rules import PolicyRules
from claims_assistant.storage.repository import Repository


def save_draft(
    state: AgentState, policies: PolicyRules, repository: Repository, today: date, confirmed: bool
) -> ToolResult:
    # Return a proposed write; runner commits session and draft in one transaction.
    if not confirmed or state.status != "ready":
        return ToolResult.error("CONFIRMATION_REQUIRED", "Review a ready draft before confirming")
    calculation = calculate(state.claim, policies, today)
    if state.calculation != calculation:
        return ToolResult.error("REVIEW_CHANGED", "The calculation changed; review it again")
    receipt = state.claim.receipt
    if receipt and repository.receipt_used(receipt.evidence_hash, receipt.fingerprint()):
        return ToolResult.error(
            "DUPLICATE_RECEIPT", "Receipt is already used in a saved local draft"
        )
    draft = {
        "id": str(uuid4()),
        "session_id": state.session_id,
        "status": "draft",
        "claim": state.claim.model_dump(mode="json"),
        "calculation": calculation.model_dump(mode="json"),
        "policy_citations": state.citations,
        "submitted": False,
    }
    return ToolResult.success(draft)
