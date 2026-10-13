from datetime import date

import pytest
from conftest import TODAY

from claims_assistant.agent.state import AgentState
from claims_assistant.agent.tool_registry import ToolRegistry
from claims_assistant.rag.ingest import ingest
from claims_assistant.rag.retrieval import retrieve
from claims_assistant.tools.extract_receipt import extract_receipt


def test_tool_error_envelopes(assistant, settings):
    registry = ToolRegistry(settings, AgentState(), assistant.repository, TODAY)
    assert registry.call("unknown", {}).code == "UNKNOWN_TOOL"
    assert registry.call("update_claim", {"amount": "-1"}).code == "INVALID_INPUT"
    assert registry.call("update_claim", {"receipt": {}}).code == "INVALID_INPUT"
    assert registry.call("calculate_claim", {}).ok is False
    assert registry.call("validate_claim", {}).data["valid"] is False
    assert registry.call("save_draft", {}, user_confirmed=False).code == "CONFIRMATION_REQUIRED"


def test_receipt_text_extraction_does_not_confirm(settings):
    result = extract_receipt(settings, text="Merchant: Demo\nDate: 2026-10-13\nTotal: RM25.00")
    assert result.ok
    assert result.data["total"] == "25.00"
    assert result.data["currency"] == "MYR"
    assert result.data["confirmed"] is False


def test_ambiguous_receipt_does_not_guess(settings):
    result = extract_receipt(settings, text="Merchant: Demo\nTotal: RM25\nTotal: RM30")
    assert result.data["total"] is None
    assert result.data["expense_date"] is None


def test_unsupported_vision_is_explicit(settings):
    assert extract_receipt(settings, image_base64="abc").code == "VISION_UNAVAILABLE"


def test_retrieval_citations_effective_date_and_staleness(settings):
    matches = retrieve(settings, "mileage rate", TODAY)
    assert matches[0]["section"] == "Mileage"
    assert matches[0]["source"] == "data/policies/claim_policy.md"
    assert matches[0]["policy_id"] == "DEMO-ALLOWANCE" and matches[0]["version"] == "1.0"
    assert retrieve(settings, "mileage", date(2025, 12, 31)) == []
    path = settings.root / "data/policies/claim_policy.md"
    path.write_text(path.read_text() + "\nChanged policy\n")
    with pytest.raises(ValueError, match="stale"):
        retrieve(settings, "mileage", TODAY)
    ingest(settings)
    assert retrieve(settings, "mileage", TODAY)
