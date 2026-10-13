from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from claims_assistant.schemas.receipt import Receipt


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    employee_id: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=40)
    expense_date: date | None = None
    purpose: str | None = Field(default=None, min_length=1, max_length=500)
    business_expense: bool | None = Field(default=None, strict=True)
    currency: str = Field(default="MYR", max_length=8)
    distance_km: Decimal | None = Field(default=None, gt=0, le=100000, decimal_places=3)
    route: str | None = Field(default=None, min_length=1, max_length=500)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    nights: int | None = Field(default=None, strict=True, gt=0, le=365)
    receipt: Receipt | None = None


class ValidationReport(BaseModel):
    valid: bool
    missing: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    policy_id: str | None = None
    policy_version: str | None = None


class Calculation(BaseModel):
    currency: str = "MYR"
    amount: Decimal
    requested_amount: Decimal
    cap: Decimal
    formula: str
    policy_id: str
    policy_version: str
    citation: dict[str, str]
