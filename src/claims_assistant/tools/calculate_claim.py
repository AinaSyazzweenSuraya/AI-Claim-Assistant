from datetime import date

from claims_assistant.schemas.claim import Claim
from claims_assistant.schemas.tool_result import ToolResult
from claims_assistant.services.calculation import calculate
from claims_assistant.services.policy_rules import PolicyRules


def calculate_claim(claim: Claim, policies: PolicyRules, today: date) -> ToolResult:
    return ToolResult.success(calculate(claim, policies, today))
