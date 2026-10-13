from datetime import date

from claims_assistant.schemas.claim import Claim
from claims_assistant.schemas.tool_result import ToolResult
from claims_assistant.services.policy_rules import PolicyRules
from claims_assistant.services.validation import validate


def validate_claim(claim: Claim, policies: PolicyRules, today: date) -> ToolResult:
    return ToolResult.success(validate(claim, policies, today))
