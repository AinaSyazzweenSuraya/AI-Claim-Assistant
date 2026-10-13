import hashlib
import json
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    merchant: str | None = Field(default=None, min_length=1, max_length=200)
    expense_date: date | None = None
    total: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, max_length=8)
    receipt_number: str | None = Field(default=None, max_length=100)
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: bool = False
    extraction_method: str = "text"

    def fingerprint(self) -> str:
        # Canonical visible fields catch reformatted versions of the same receipt.
        payload = json.dumps(
            [
                (self.merchant or "").strip().casefold(),
                str(self.expense_date),
                f"{self.total:.2f}" if self.total is not None else None,
                self.currency,
                self.receipt_number,
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()
