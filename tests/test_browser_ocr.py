import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from conftest import TODAY
from fastapi.testclient import TestClient

from claims_assistant.interfaces.web import create_app
from claims_assistant.llm.client import ModelClient
from claims_assistant.tools.extract_receipt import extract_receipt

TEXT = f"Merchant: Browser Cafe\nDate: {TODAY}\nTotal: RM45.00\nCurrency: MYR\nReceipt: OCR001"


def test_browser_ocr_hashes_received_text_and_requires_review(settings):
    settings.receipt_image_backend = "browser"
    result = extract_receipt(settings, ocr_text=TEXT)
    receipt = result.data
    assert receipt["extraction_method"] == "browser_ocr_text"
    assert receipt["total"] == "45.00" and receipt["confirmed"] is False
    assert receipt["evidence_hash"] == hashlib.sha256(TEXT.encode()).hexdigest()


def test_browser_ocr_uses_text_model_without_sending_images(settings, monkeypatch):
    settings.llm_mode, settings.receipt_image_backend = "openai", "browser"
    settings.llm_api_key = "test-key"
    model = Mock(return_value={"merchant": "Browser Cafe", "total": "45.00"})
    monkeypatch.setattr(ModelClient, "receipt", model)
    result = extract_receipt(settings, ocr_text=TEXT)
    assert model.call_args.args[1] == TEXT
    assert result.data["extraction_method"] == "browser_ocr_text"
    assert result.data["confirmed"] is False


@pytest.mark.parametrize("text", ["", "  \n ", "x" * 20001])
def test_invalid_ocr_text_never_calls_model(settings, monkeypatch, text):
    model = Mock()
    monkeypatch.setattr(ModelClient, "receipt", model)
    with pytest.raises(ValueError):
        extract_receipt(settings, ocr_text=text)
    model.assert_not_called()


def test_browser_backend_rejects_server_side_image_requests(settings):
    settings.receipt_image_backend = "browser"
    result = extract_receipt(settings, image_base64="not-an-image")
    assert result.code == "BROWSER_OCR_REQUIRED" and not result.ok


def test_browser_ocr_api_full_claim_and_duplicate_detection(settings):
    settings.receipt_image_backend = "browser"
    with TestClient(
        create_app(settings), base_url="http://localhost", client=("127.0.0.1", 50000)
    ) as client:
        fields = {
            "employee_id": "OCR001",
            "category": "meal",
            "expense_date": str(TODAY),
            "purpose": "Client lunch",
            "business_expense": True,
            "amount": "45.00",
        }
        extracted = client.post(
            "/api/chat", json={"fields": fields, "receipt_ocr_text": TEXT}
        ).json()
        assert extracted["state"]["claim"]["receipt"]["confirmed"] is False
        assert extracted["state"]["calculation"] is None

        def follow(response, **options):
            return client.post(
                "/api/chat",
                json={
                    "session_id": response["state"]["session_id"],
                    "expected_revision": response["state"]["revision"],
                    **options,
                },
            ).json()

        reviewed = follow(extracted, confirm_receipt=True)
        assert reviewed["state"]["calculation"]["amount"] == "30.00"
        assert reviewed["state"]["calculation"]["citation"]["section"] == "Meal"
        saved = follow(reviewed, confirm=True)
        assert saved["state"]["status"] == "saved"
        draft = client.get("/api/drafts/" + saved["state"]["draft_id"]).json()
        assert draft["submitted"] is False
        duplicate = client.post(
            "/api/chat", json={"fields": fields, "receipt_ocr_text": TEXT}
        ).json()
        duplicate = follow(duplicate, confirm_receipt=True)
        duplicate = follow(duplicate, confirm=True)
        assert duplicate["state"]["draft_id"] is None
        assert "already used" in duplicate["message"]


@pytest.mark.parametrize(
    "options",
    [
        {"receipt_text": TEXT},
        {"receipt_image": "abcd"},
        {"confirm_receipt": True},
    ],
)
def test_ocr_source_and_confirmation_must_be_separate(assistant, options):
    response = assistant.respond(receipt_ocr_text=TEXT, **options)
    assert response.state.claim.receipt is None
    assert response.state.draft_id is None


def test_browser_assets_are_self_hosted_and_hash_verified(settings):
    root = Path(__file__).parents[1] / "src/claims_assistant/interfaces/static/ocr/6.0.1"
    manifest = json.loads((root / "manifest.json").read_text())
    with TestClient(
        create_app(settings), base_url="http://localhost", client=("127.0.0.1", 50000)
    ) as client:
        for name, expected in manifest["files"].items():
            response = client.get("/assets/ocr/6.0.1/" + name)
            assert response.status_code == 200
            assert hashlib.sha256(response.content).hexdigest() == expected
            assert "public" in response.headers["cache-control"]
        helper = client.get("/assets/ocr/browser-ocr.js")
        assert helper.status_code == 200 and "createWorker" in helper.text
        assert "javascript" in helper.headers["content-type"]
        assert client.get("/assets/ocr/missing.js").status_code == 404
        assert client.get("/assets/ocr/../web.html").status_code == 404
