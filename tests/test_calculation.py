import json
from decimal import Decimal

import pytest
from conftest import TODAY, mileage, receipt_claim

from claims_assistant.services.calculation import calculate
from claims_assistant.services.policy_rules import PolicyRules


@pytest.mark.parametrize(
    "distance,expected", [("25", "15.00"), ("1.025", "0.62"), ("1000", "300.00")]
)
def test_mileage_decimal_rounding_and_cap(settings, distance, expected):
    result = calculate(mileage(distance_km=distance), PolicyRules(settings.root), TODAY)
    assert result.amount == Decimal(expected)
    assert result.citation["section"] == "Mileage"
    assert result.policy_id == "DEMO-ALLOWANCE"
    assert result.policy_version == "1.0"


@pytest.mark.parametrize(
    "category,amount,nights,expected",
    [
        ("meal", "45.00", None, "30.00"),
        ("parking", "60.00", None, "50.00"),
        ("lodging", "400.00", 2, "360.00"),
        ("lodging", "100.00", 2, "100.00"),
    ],
)
def test_receipt_actual_amount_and_caps(settings, category, amount, nights, expected):
    claim = receipt_claim(category, amount, **({"nights": nights} if nights else {}))
    result = calculate(claim, PolicyRules(settings.root), TODAY)
    assert result.amount == Decimal(expected)
    assert result.requested_amount == Decimal(amount)


def test_invalid_claim_never_calculates(settings):
    with pytest.raises(ValueError, match="not valid"):
        calculate(mileage(route=None), PolicyRules(settings.root), TODAY)


def test_sample_policy_numbers_align_with_rules(settings):
    text = (settings.root / "data/policies/claim_policy.md").read_text()
    rule = json.loads((settings.root / "data/rules/claim_rules.json").read_text())
    for category, values in rule["categories"].items():
        section = text.split("## " + values["section"] + "\n", 1)[1].split("\n## ", 1)[0]
        for key in ["rate", "cap", "cap_per_night"]:
            if key in values:
                assert "RM" + values[key] in section, (category, key)


def test_invalid_policy_rate_is_rejected(settings):
    path = settings.root / "data/rules/claim_rules.json"
    rule = json.loads(path.read_text())
    rule["categories"]["mileage"]["rate"] = "-0.60"
    path.write_text(json.dumps(rule))
    with pytest.raises(ValueError, match="positive finite"):
        PolicyRules(settings.root)
