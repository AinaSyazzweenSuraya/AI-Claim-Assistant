from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from claims_assistant.schemas.claim import Calculation, Claim
from claims_assistant.services.policy_rules import PolicyRules
from claims_assistant.services.validation import validate


def calculate(claim: Claim, policies: PolicyRules, today: date | None = None) -> Calculation:
    report = validate(claim, policies, today)
    if not report.valid:
        raise ValueError("Claim is not valid: " + ", ".join(report.missing + report.errors))
    rule = policies.applicable(claim.expense_date)
    category = rule["categories"][claim.category]
    if claim.category == "mileage":
        raw = claim.distance_km * Decimal(category["rate"])
        cap = Decimal(category["cap"])
        formula = f"{claim.distance_km} km × RM{category['rate']}/km; cap RM{cap:.2f}"
    elif claim.category == "lodging":
        raw = claim.amount
        cap = Decimal(category["cap_per_night"]) * claim.nights
        formula = f"Receipt RM{raw:.2f}; {claim.nights} nights × RM{category['cap_per_night']} cap"
    else:
        raw = claim.amount
        cap = Decimal(category["cap"])
        formula = f"Receipt RM{raw:.2f}; cap RM{cap:.2f}"
    return Calculation(
        amount=min(raw, cap).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        requested_amount=raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        cap=cap,
        formula=formula,
        policy_id=rule["id"],
        policy_version=rule["version"],
        citation=policies.citation(rule, claim.category),
    )
