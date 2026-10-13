import json
import re
import shlex
from datetime import date, datetime
from zoneinfo import ZoneInfo

from claims_assistant.agent.instructions import load
from claims_assistant.agent.state import AgentResponse
from claims_assistant.agent.tool_registry import ToolRegistry
from claims_assistant.config import Settings
from claims_assistant.llm.client import ModelClient, ModelError
from claims_assistant.schemas.claim import Calculation, Claim, ValidationReport
from claims_assistant.schemas.receipt import Receipt
from claims_assistant.schemas.tool_result import ToolResult
from claims_assistant.storage.repository import ConflictError, Repository


def demo_patch(message: str, today: date) -> dict:
    """A limited, transparent parser for offline workflow testing."""
    if message.lstrip().startswith("{"):
        data = json.loads(message)
        if not isinstance(data, dict):
            raise ValueError("Claim fields must be a JSON object")
        return data
    patch = {}
    if "=" in message:
        for token in shlex.split(message):
            if "=" not in token:
                raise ValueError("Use key=value fields; quote multiword values")
            key, value = token.split("=", 1)
            try:
                patch[key] = json.loads(value)
            except ValueError:
                patch[key] = value
        return patch
    text = message.casefold()
    for category in ["mileage", "meal", "parking", "lodging"]:
        if re.search(rf"\b{category}\b", text):
            patch["category"] = category
            break
    distance = re.search(r"\b(\d+(?:\.\d+)?)\s*km\b", text)
    if distance:
        patch.update(category="mileage", distance_km=distance[1])
    amount = re.search(r"\b(?:rm|myr)\s*(\d+(?:\.\d+)?)\b", text)
    if amount:
        patch["amount"] = amount[1]
    expense = re.search(r"\b\d{4}-\d{2}-\d{2}\b", message)
    if expense:
        patch["expense_date"] = expense[0]
    elif re.search(r"\btoday\b", text):
        patch["expense_date"] = today.isoformat()
    employee = re.search(r"\bemployee\s+([\w-]+)", message, re.I)
    if employee:
        patch["employee_id"] = employee[1]
    route = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+?)(?=\s+(?:on|for)\b|$)", message, re.I)
    if route:
        patch["route"] = f"{route[1]} to {route[2]}"
    purpose = re.search(r"\bfor\s+(.+)$", message, re.I)
    if purpose:
        patch["purpose"] = purpose[1]
    nights = re.search(r"\b(\d+)\s+nights?\b", text)
    if nights:
        patch["nights"] = int(nights[1])
    if text.strip() == "business":
        patch["business_expense"] = True
    elif text.strip() == "personal":
        patch["business_expense"] = False
    return patch


class Assistant:
    def __init__(self, settings: Settings | None = None, today: date | None = None):
        self.settings = settings or Settings()
        self.settings.prepare()
        self.today = today
        self.repository = Repository(
            self.settings.runtime / "claims.db",
            self.settings.database_url.get_secret_value() if self.settings.database_url else None,
        )

    def _model_loop(self, registry: ToolRegistry, message: str, trace: list[dict]) -> None:
        messages = [
            {
                "role": "system",
                "content": load(self.settings.root)
                + "\nPropose fields using update_claim. Dates are ISO; decimal values are strings."
                + " Do not include business_expense: users affirm it using the explicit business"
                + " action. Do not reset existing fields unless the user asks."
                + "\nCurrent date: "
                + registry.today.isoformat()
                + "\nCurrent claim: "
                + registry.state.claim.model_dump_json(),
            },
            *registry.state.history[-10:],
            {"role": "user", "content": message},
        ]
        client = ModelClient(self.settings)
        for _ in range(4):
            response = client.completion(messages, ToolRegistry.model_tools())
            calls = response.get("tool_calls") or []
            if not calls:
                return
            if len(calls) > 4:
                raise ModelError("Model exceeded the tool-call limit")
            messages.append(
                {"role": "assistant", "content": response.get("content"), "tool_calls": calls}
            )
            for call in calls:
                try:
                    call_id = call["id"]
                    if not isinstance(call_id, str):
                        raise ValueError("Missing tool call ID")
                    name = call["function"]["name"]
                    arguments = json.loads(call["function"]["arguments"])
                    if name not in {"update_claim", "search_policy"} or not isinstance(
                        arguments, dict
                    ):
                        raise ValueError("Tool not available to the model")
                    if name == "update_claim":
                        arguments.pop("business_expense", None)
                    result = registry.call(name, arguments)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ModelError("Model returned invalid tool calls") from exc
                trace.append({"tool": name, "result": result.model_dump(mode="json")})
                if not result.ok:
                    raise ModelError("Model proposed invalid fields; use the structured form")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result.model_dump_json(),
                    }
                )
        raise ModelError("Model reached its turn limit; use the structured form")

    def respond(
        self,
        message: str = "",
        session_id: str | None = None,
        fields: dict | None = None,
        receipt_text: str | None = None,
        receipt_image: str | None = None,
        receipt_fields: dict | None = None,
        confirm_receipt: bool = False,
        confirm: bool = False,
        expected_revision: int | None = None,
    ) -> AgentResponse:
        today = self.today or datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()
        state = self.repository.load(session_id) if session_id else self.repository.create()
        previous_revision = state.revision
        if expected_revision is not None and previous_revision != expected_revision:
            raise ConflictError("Session changed; reload before retrying")
        original = state.model_copy(deep=True)
        trace = []
        registry = ToolRegistry(self.settings, state, self.repository, today)
        confirm = confirm or message.strip().casefold() == "confirm"
        new = message.strip().casefold() == "new"
        error = None
        draft = None
        policy_question = (
            fields is None
            and not confirm
            and not new
            and bool(re.match(r"^(what|how|explain|when|which)\b", message.strip(), re.I))
        )

        def invoke(name: str, arguments: dict, user_confirmed: bool = False) -> ToolResult:
            result = registry.call(name, arguments, user_confirmed)
            trace.append({"tool": name, "result": result.model_dump(mode="json")})
            return result

        if confirm and expected_revision is None:
            return AgentResponse(
                state=state, message="Reload and confirm the displayed revision of the draft."
            )
        if state.status == "saved" and not new:
            return AgentResponse(
                state=state,
                message=f"Local draft {state.draft_id} is saved. Send new for another claim.",
            )
        if new:
            state.claim, state.status = Claim(), "collecting"
            state.draft_id, state.calculation, state.validation = None, None, None
            state.citations, state.history = [], []

        # Extracting/replacing evidence and confirming it must be separate actions.
        if confirm_receipt and (receipt_text or receipt_image or receipt_fields):
            error = "Review the extracted or corrected receipt before confirming it."
        try:
            patch = fields
            if (
                patch is None
                and message
                and not policy_question
                and message.strip().casefold() not in {"confirm", "new"}
            ):
                if (
                    self.settings.llm_mode == "demo"
                    or message.lstrip().startswith("{")
                    or "=" in message
                    or message.strip().casefold() in {"business", "personal"}
                ):
                    patch = demo_patch(message, today)
                else:
                    self._model_loop(registry, message, trace)
            if patch and not error:
                result = invoke("update_claim", patch)
                if not result.ok:
                    error = result.message
            if not error and (receipt_text or receipt_image):
                result = invoke(
                    "extract_receipt", {"text": receipt_text, "image_base64": receipt_image}
                )
                if result.ok:
                    state.claim.receipt = Receipt.model_validate(result.data)
                    state.status, state.calculation = "collecting", None
                else:
                    error = result.message
            if receipt_fields and not error:
                allowed = {"merchant", "expense_date", "total", "currency", "receipt_number"}
                if not state.claim.receipt or set(receipt_fields) - allowed:
                    error = "Extract a receipt first; only visible receipt fields can be corrected."
                else:
                    state.claim.receipt = Receipt.model_validate(
                        {
                            **state.claim.receipt.model_dump(mode="json"),
                            **receipt_fields,
                            "confirmed": False,
                        }
                    )
                    state.status, state.calculation = "collecting", None
            if confirm_receipt and not error:
                if state.claim.receipt:
                    state.claim.receipt.confirmed = True
                else:
                    error = "Extract and review a receipt first."
        except (ValueError, ModelError) as exc:
            state = original.model_copy(deep=True)
            registry.state = state
            error = (
                str(exc)
                if isinstance(exc, ModelError)
                else "Invalid claim or receipt input; check field formats."
            )

        changed = state.claim != original.claim or new
        if error:
            # Tool failures cannot retain ready status or silently save partial changes.
            state = original.model_copy(deep=True)
            registry.state = state
            state.status, state.calculation = "collecting", None
            response_text = error
        else:
            validation = invoke("validate_claim", {})
            if not validation.ok:
                state.status, state.calculation = "invalid", None
                response_text = validation.message
            else:
                state.validation = ValidationReport.model_validate(validation.data)
                if not state.validation.valid:
                    state.calculation = None
                    state.status = "invalid" if state.validation.errors else "collecting"
                    details = []
                    if state.validation.missing:
                        details.append("Please provide: " + ", ".join(state.validation.missing))
                    details.extend(state.validation.errors)
                    response_text = ". ".join(details)
                else:
                    search = invoke("search_policy", {"query": state.claim.category + " allowance"})
                    calculation = invoke("calculate_claim", {})
                    if not search.ok or not calculation.ok:
                        state.status, state.calculation = "invalid", None
                        response_text = (search if not search.ok else calculation).message
                    else:
                        state.citations = search.data
                        state.calculation = Calculation.model_validate(calculation.data)
                        state.status = "ready"
                        if (
                            confirm
                            and not changed
                            and original.status == "ready"
                            and original.calculation == state.calculation
                        ):
                            saved = invoke("save_draft", {}, user_confirmed=True)
                            if saved.ok:
                                draft = saved.data
                                state.draft_id, state.status = draft["id"], "saved"
                                response_text = (
                                    f"Local draft {state.draft_id} saved. "
                                    "It has not been submitted or approved."
                                )
                            else:
                                state.status = "invalid"
                                response_text = saved.message
                        else:
                            calc = state.calculation
                            citation = calc.citation
                            response_text = (
                                f"Draft amount: RM{calc.amount:.2f}. {calc.formula}. "
                                f"Source: {citation['policy_id']} v{citation['version']}, "
                                f"{citation['section']} ({citation['source']}). "
                                "Review the details, then send confirm to save locally."
                            )
            if policy_question:
                answer = invoke("search_policy", {"query": message})
                if not answer.ok:
                    response_text = answer.message
                elif not answer.data:
                    response_text = (
                        "No applicable policy section matched. Please name the allowance."
                    )
                else:
                    state.citations = answer.data
                    response_text = "\n\n".join(
                        f"{item['text']}\nSource: {item['policy_id']} v{item['version']}, "
                        f"{item['section']} ({item['source']})."
                        for item in answer.data[:2]
                    )
        if message:
            state.history.append({"role": "user", "content": message[:4000]})
        state.history.append({"role": "assistant", "content": response_text})
        state.history = state.history[-20:]
        self.repository.commit(state, previous_revision, draft)
        return AgentResponse(state=state, message=response_text, tools=trace)
