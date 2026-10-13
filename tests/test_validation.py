from datetime import timedelta

import pytest
from conftest import TODAY, mileage, receipt_claim
from pydantic import ValidationError

from claims_assistant.schemas.claim import Claim
from claims_assistant.services.policy_rules import PolicyRules
from claims_assistant.services.validation import validate


@pytest.mark.parametrize("days,valid", [(0, True), (30, True), (31, False), (-1, False)])
def test_deadline_and_future_dates(settings, days, valid):
    report = validate(
        mileage(expense_date=TODAY - timedelta(days=days)), PolicyRules(settings.root), TODAY
    )
    assert report.valid is valid


def test_missing_fields_and_business_assertion(settings):
    report = validate(Claim(), PolicyRules(settings.root), TODAY)
    assert set(report.missing) == {
        "employee_id",
        "category",
        "expense_date",
        "purpose",
        "business_expense",
    }
    assert not report.valid


@pytest.mark.parametrize(
    "updates",
    [
        {"currency": "USD"},
        {"category": "entertainment"},
        {"business_expense": False},
        {"expense_date": "2025-12-31"},
    ],
)
def test_unsupported_or_ineligible_claims(settings, updates):
    report = validate(mileage(**updates), PolicyRules(settings.root), TODAY)
    assert not report.valid and report.errors


@pytest.mark.parametrize(
    "updates",
    [
        {"distance_km": "-1"},
        {"amount": "0"},
        {"amount": "1.001"},
        {"amount": "NaN"},
        {"nights": 1.5},
        {"nights": True},
        {"nights": 0},
        {"purpose": "  "},
        {"business_expense": "yes"},
    ],
)
def test_malformed_numbers_and_fields_rejected(updates):
    with pytest.raises(ValidationError):
        mileage(**updates)


def test_receipt_must_be_reviewed_and_match(settings):
    claim = receipt_claim()
    claim.receipt.confirmed = False
    report = validate(claim, PolicyRules(settings.root), TODAY)
    assert "receipt.confirmed" in report.missing
    claim.receipt.confirmed = True
    claim.receipt.total = "50.00"
    assert any(
        "total must match" in x for x in validate(claim, PolicyRules(settings.root), TODAY).errors
    )


def test_category_switch_cannot_reuse_incompatible_fields(settings):
    report = validate(mileage(category="meal", amount="25"), PolicyRules(settings.root), TODAY)
    assert any("mileage fields" in error for error in report.errors)
