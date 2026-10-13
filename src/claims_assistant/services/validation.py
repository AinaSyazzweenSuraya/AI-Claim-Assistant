from datetime import date

from claims_assistant.schemas.claim import Claim, ValidationReport
from claims_assistant.services.policy_rules import PolicyRules


def validate(claim: Claim, policies: PolicyRules, today: date | None = None) -> ValidationReport:
    today = today or date.today()
    missing = [
        key
        for key in ["employee_id", "category", "expense_date", "purpose", "business_expense"]
        if getattr(claim, key) is None or getattr(claim, key) == ""
    ]
    errors = []
    rule = None
    if claim.business_expense is False:
        errors.append("Personal expenses and commuting are ineligible")
    if claim.currency != "MYR":
        errors.append("Only MYR is supported")
    if claim.expense_date:
        try:
            rule = policies.applicable(claim.expense_date)
        except ValueError as exc:
            errors.append(str(exc))
        if claim.expense_date > today:
            errors.append("Future expense dates are ineligible")
        if rule and (today - claim.expense_date).days > rule["deadline_days"]:
            errors.append(f"Expense is outside the {rule['deadline_days']}-day deadline")
    if claim.category and claim.category not in {"mileage", "meal", "parking", "lodging"}:
        errors.append("Unsupported category; use mileage, meal, parking, or lodging")
    if claim.category == "mileage":
        missing.extend(k for k in ["distance_km", "route"] if not getattr(claim, k))
        if claim.receipt or claim.amount or claim.nights:
            errors.append("Mileage must not include receipt, amount, or nights; start a new claim")
    elif claim.category in {"meal", "parking", "lodging"}:
        if claim.distance_km or claim.route:
            errors.append("Receipt claims must not include mileage fields; start a new claim")
        if claim.category != "lodging" and claim.nights:
            errors.append("Nights are only supported for lodging")
        if claim.amount is None:
            missing.append("amount")
        if claim.category == "lodging" and claim.nights is None:
            missing.append("nights")
        if claim.receipt is None:
            missing.append("receipt")
        else:
            receipt = claim.receipt
            missing.extend(
                f"receipt.{k}"
                for k in ["merchant", "expense_date", "total", "currency"]
                if getattr(receipt, k) is None or getattr(receipt, k) == ""
            )
            if not receipt.confirmed:
                missing.append("receipt.confirmed")
            if receipt.currency and receipt.currency != "MYR":
                errors.append("Receipt currency must be MYR")
            if receipt.expense_date and receipt.expense_date != claim.expense_date:
                errors.append("Receipt date must match the claim expense date")
            if receipt.total is not None and claim.amount != receipt.total:
                errors.append("Receipt total must match the claim amount")
    return ValidationReport(
        valid=not missing and not errors,
        missing=missing,
        errors=errors,
        policy_id=rule["id"] if rule else None,
        policy_version=rule["version"] if rule else None,
    )
