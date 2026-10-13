import json
from datetime import date
from decimal import Decimal
from pathlib import Path


class PolicyRules:
    def __init__(self, root: Path):
        self.root = root
        manifest = json.loads((root / "data/policies/policy_manifest.json").read_text())
        self.versions = []
        for item in manifest["policies"]:
            rule_path = (root / "data/rules" / item["rules_file"]).resolve()
            if not rule_path.is_relative_to((root / "data/rules").resolve()):
                raise ValueError("Rules file must stay in data/rules")
            rule = json.loads(rule_path.read_text())
            for key in ["id", "version", "effective_from", "effective_to"]:
                if rule[key] != item[key]:
                    raise ValueError(f"Manifest/rules mismatch: {key}")
            date.fromisoformat(rule["effective_from"])
            if rule["effective_to"] and date.fromisoformat(
                rule["effective_to"]
            ) < date.fromisoformat(rule["effective_from"]):
                raise ValueError("Invalid policy effective interval")
            if rule["currency"] != "MYR" or rule["rounding"] != "ROUND_HALF_UP":
                raise ValueError("Unsupported policy currency or rounding")
            if type(rule["deadline_days"]) is not int or rule["deadline_days"] < 0:
                raise ValueError("Invalid policy deadline")
            if set(rule["categories"]) != {"mileage", "meal", "parking", "lodging"}:
                raise ValueError("Unsupported policy categories")
            for category, spec in rule["categories"].items():
                keys = (
                    ["rate", "cap"]
                    if category == "mileage"
                    else ["cap_per_night"]
                    if category == "lodging"
                    else ["cap"]
                )
                for key in keys:
                    number = Decimal(spec[key])
                    if not number.is_finite() or number <= 0:
                        raise ValueError("Policy rates and caps must be positive finite decimals")
                if spec["receipt_required"] != (category != "mileage"):
                    raise ValueError("Unsupported receipt requirement")
            self.versions.append(rule)

    def applicable(self, expense_date: date) -> dict:
        matches = [
            r
            for r in self.versions
            if date.fromisoformat(r["effective_from"]) <= expense_date
            and (r["effective_to"] is None or expense_date <= date.fromisoformat(r["effective_to"]))
        ]
        if len(matches) != 1:
            raise ValueError("No unique applicable policy version for this expense date")
        return matches[0]

    def citation(self, rule: dict, category: str) -> dict[str, str]:
        return {
            "policy_id": rule["id"],
            "version": rule["version"],
            "effective_from": rule["effective_from"],
            "source": "data/policies/claim_policy.md",
            "section": rule["categories"][category]["section"],
        }
