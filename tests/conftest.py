import shutil
from datetime import date
from pathlib import Path

import pytest

from claims_assistant.agent.runner import Assistant
from claims_assistant.config import Settings
from claims_assistant.rag.ingest import ingest
from claims_assistant.schemas.claim import Claim
from claims_assistant.schemas.receipt import Receipt

TODAY = date(2026, 10, 13)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    for name in ["data", "prompts"]:
        shutil.copytree(ROOT / name, root / name)
    config = Settings(root=root, runtime_dir=tmp_path / "runtime", _env_file=None)
    config.prepare()
    ingest(config)
    return config


@pytest.fixture
def assistant(settings):
    return Assistant(settings, today=TODAY)


def mileage(**updates) -> Claim:
    return Claim.model_validate(
        {
            "employee_id": "DEMO001",
            "category": "mileage",
            "expense_date": TODAY,
            "purpose": "Client visit",
            "business_expense": True,
            "distance_km": "25",
            "route": "KL to PJ",
            **updates,
        }
    )


def receipt_claim(category="meal", amount="25.00", **updates) -> Claim:
    receipt = Receipt(
        merchant="Fictional Cafe",
        expense_date=TODAY,
        total=amount,
        currency="MYR",
        evidence_hash="a" * 64,
        confirmed=True,
    )
    return Claim(
        employee_id="DEMO001",
        category=category,
        expense_date=TODAY,
        purpose="Client meeting",
        business_expense=True,
        amount=amount,
        receipt=receipt,
        **updates,
    )
