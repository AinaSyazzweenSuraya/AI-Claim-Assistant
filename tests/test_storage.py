import pytest
from conftest import TODAY

from claims_assistant.services.policy_rules import PolicyRules
from claims_assistant.storage.repository import ConflictError
from claims_assistant.tools.save_draft import save_draft


def test_duplicate_race_rolls_back_session_and_draft(assistant, settings):
    fields = {
        "employee_id": "DEMO001",
        "category": "meal",
        "expense_date": str(TODAY),
        "purpose": "Client lunch",
        "business_expense": True,
        "amount": "25.00",
    }
    receipt = "Merchant: Demo Cafe\nDate: 2026-10-13\nTotal: RM25.00"
    states = []
    for _ in range(2):
        extracted = assistant.respond(fields=fields, receipt_text=receipt)
        reviewed = assistant.respond(
            session_id=extracted.state.session_id,
            expected_revision=extracted.state.revision,
            confirm_receipt=True,
        )
        states.append(reviewed.state)
    rules = PolicyRules(settings.root)
    proposals = [save_draft(s, rules, assistant.repository, TODAY, True).data for s in states]
    for state, proposal in zip(states, proposals, strict=True):
        state.status, state.draft_id = "saved", proposal["id"]
    assistant.repository.commit(states[0], states[0].revision, proposals[0])
    with pytest.raises(ConflictError, match="Duplicate"):
        assistant.repository.commit(states[1], states[1].revision, proposals[1])
    stored = assistant.repository.load(states[1].session_id)
    assert stored.status == "ready" and stored.draft_id is None
    assert stored.revision == states[1].revision
    with pytest.raises(KeyError):
        assistant.repository.draft(proposals[1]["id"])
