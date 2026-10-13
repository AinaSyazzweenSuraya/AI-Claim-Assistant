from datetime import date

from pydantic import ValidationError

from claims_assistant.agent.state import AgentState
from claims_assistant.config import Settings
from claims_assistant.llm.client import ModelError
from claims_assistant.schemas.claim import Claim
from claims_assistant.schemas.tool_result import ToolResult
from claims_assistant.services.policy_rules import PolicyRules
from claims_assistant.storage.repository import Repository
from claims_assistant.tools.calculate_claim import calculate_claim
from claims_assistant.tools.extract_receipt import extract_receipt
from claims_assistant.tools.save_draft import save_draft
from claims_assistant.tools.search_policy import search_policy
from claims_assistant.tools.validate_claim import validate_claim

PATCH_FIELDS = set(Claim.model_fields) - {"receipt"}


class ToolRegistry:
    def __init__(self, settings: Settings, state: AgentState, repository: Repository, today: date):
        self.settings, self.state, self.repository, self.today = settings, state, repository, today
        self.policies = PolicyRules(settings.root)

    def call(self, name: str, arguments: dict, user_confirmed: bool = False) -> ToolResult:
        try:
            if name == "search_policy":
                return search_policy(
                    self.settings,
                    arguments["query"],
                    self.state.claim.expense_date or self.today,
                )
            if name == "update_claim":
                if set(arguments) - PATCH_FIELDS:
                    raise ValueError("Unknown or protected claim fields")
                if self.state.status == "saved":
                    raise ValueError("Saved claims are immutable; send new to start another")
                candidate = Claim.model_validate(
                    {**self.state.claim.model_dump(mode="json"), **arguments}
                )
                if candidate != self.state.claim:
                    self.state.claim = candidate
                    self.state.status = "collecting"
                    self.state.calculation = None
                    self.state.citations = []
                return ToolResult.success(candidate)
            if name == "extract_receipt":
                return extract_receipt(self.settings, **arguments)
            if name == "validate_claim":
                return validate_claim(self.state.claim, self.policies, self.today)
            if name == "calculate_claim":
                return calculate_claim(self.state.claim, self.policies, self.today)
            if name == "save_draft":
                return save_draft(
                    self.state, self.policies, self.repository, self.today, user_confirmed
                )
            return ToolResult.error("UNKNOWN_TOOL", "Tool is not registered")
        except ValidationError:
            return ToolResult.error("INVALID_INPUT", "Invalid field type, format, or allowed range")
        except (ValueError, KeyError, TypeError) as exc:
            return ToolResult.error("INVALID_INPUT", str(exc))
        except ModelError as exc:
            return ToolResult.error("MODEL_UNAVAILABLE", str(exc))
        except OSError:
            return ToolResult.error("STORAGE_ERROR", "Could not read policy or runtime files")

    @staticmethod
    def model_tools() -> list[dict]:
        properties = {
            k: v for k, v in Claim.model_json_schema()["properties"].items() if k in PATCH_FIELDS
        }
        # Evidence, confirmation, validation, calculations and saving are server-controlled.
        properties.pop("business_expense", None)
        return [
            {
                "type": "function",
                "function": {
                    "name": "update_claim",
                    "description": "Propose fields explicitly supplied by the user; never guess.",
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_policy",
                    "description": "Look up policy explanations with source citations.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "maxLength": 1000}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            },
        ]
