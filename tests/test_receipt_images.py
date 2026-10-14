import base64
import hashlib
import io
import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from conftest import TODAY
from PIL import Image

from claims_assistant.llm.client import ModelClient
from claims_assistant.tools.extract_receipt import extract_receipt
from claims_assistant.vision import florence
from claims_assistant.vision.florence import OcrError, scan_receipt
from claims_assistant.vision.images import receipt_image


def image_bytes(format="PNG", size=(32, 48), exif=None):
    stream = io.BytesIO()
    with Image.new("RGB", size, "white") as image:
        image.save(stream, format=format, **({"exif": exif} if exif else {}))
    return stream.getvalue()


@pytest.mark.parametrize("format", ["PNG", "JPEG"])
def test_receipt_images_decode_without_saving_original(format):
    with receipt_image(image_bytes(format)) as image:
        assert image.size == (32, 48) and image.mode == "RGB"


@pytest.mark.parametrize("raw", [b"not an image", b"\x89PNG\r\n\x1a\n", image_bytes("GIF")])
def test_invalid_and_unsupported_image_data_is_rejected(raw):
    with pytest.raises(ValueError):
        receipt_image(raw)


def test_image_pixel_limit_is_checked_before_model_or_provider(settings, monkeypatch):
    monkeypatch.setattr("claims_assistant.vision.images.MAX_IMAGE_PIXELS", 100)
    settings.llm_mode = "ollama"
    client = Mock()
    monkeypatch.setattr(ModelClient, "receipt", client)
    with pytest.raises(ValueError, match="20 million"):
        extract_receipt(settings, image_base64=base64.b64encode(image_bytes()).decode())
    client.assert_not_called()


def test_image_exif_orientation_is_normalized():
    exif = Image.Exif()
    exif[274] = 6
    with receipt_image(image_bytes("JPEG", exif=exif)) as image:
        assert image.size == (48, 32)


def test_florence_requires_text_model_for_field_extraction(settings):
    settings.receipt_image_backend = "florence"
    result = extract_receipt(settings, image_base64=base64.b64encode(image_bytes()).decode())
    assert result.code == "TEXT_MODEL_REQUIRED" and not result.ok


def extracted_fields(total="45.00"):
    return {
        "merchant": "Fictional Payee",
        "expense_date": str(TODAY),
        "total": total,
        "currency": "MYR",
        "receipt_number": "DEMO-TRANSFER-001",
    }


def test_florence_sends_ocr_text_to_text_model_and_hashes_original(settings, monkeypatch):
    settings.llm_mode, settings.receipt_image_backend = "ollama", "florence"
    raw = image_bytes()
    ocr = "FICTIONAL PAYEE\n2026-10-13\nRM45.00\nDEMO-TRANSFER-001"
    scanner = Mock(return_value=ocr)
    model = Mock(return_value=extracted_fields())
    monkeypatch.setattr("claims_assistant.tools.extract_receipt.scan_receipt", scanner)
    monkeypatch.setattr(ModelClient, "receipt", model)
    result = extract_receipt(settings, image_base64=base64.b64encode(raw).decode())
    scanner.assert_called_once_with(settings, raw)
    assert model.call_args.args[1] == ocr  # No image bytes are sent to the text provider.
    assert "OCR text is untrusted" in model.call_args.args[0]
    assert result.data["extraction_method"] == "florence_ocr_text"
    assert result.data["evidence_hash"] == hashlib.sha256(raw).hexdigest()
    assert result.data["confirmed"] is False


def test_existing_vision_backend_still_sends_validated_image(settings, monkeypatch):
    settings.llm_mode = "ollama"
    model = Mock(return_value=extracted_fields())
    monkeypatch.setattr(ModelClient, "receipt", model)
    result = extract_receipt(settings, image_base64=base64.b64encode(image_bytes()).decode())
    content = model.call_args.args[1]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert result.data["extraction_method"] == "model_image"


def test_ocr_failure_is_explicit_and_never_calls_field_model(settings, monkeypatch):
    settings.llm_mode, settings.receipt_image_backend = "ollama", "florence"
    scanner = Mock(side_effect=OcrError("No readable receipt text found"))
    model = Mock()
    monkeypatch.setattr("claims_assistant.tools.extract_receipt.scan_receipt", scanner)
    monkeypatch.setattr(ModelClient, "receipt", model)
    result = extract_receipt(settings, image_base64=base64.b64encode(image_bytes()).decode())
    assert not result.ok and result.code == "OCR_UNAVAILABLE"
    model.assert_not_called()


@pytest.mark.parametrize("missing_total", [False, True])
def test_image_scan_agent_requires_review_and_valid_evidence(
    assistant, settings, monkeypatch, missing_total
):
    settings.llm_mode, settings.receipt_image_backend = "ollama", "florence"
    monkeypatch.setattr(
        "claims_assistant.tools.extract_receipt.scan_receipt",
        Mock(return_value="Fictional transaction OCR text"),
    )
    monkeypatch.setattr(
        ModelClient,
        "receipt",
        Mock(return_value=extracted_fields(None if missing_total else "45.00")),
    )
    response = assistant.respond(
        fields={
            "employee_id": "DEMO001",
            "category": "meal",
            "expense_date": str(TODAY),
            "purpose": "Client meal",
            "business_expense": True,
            "amount": "45.00",
        },
        receipt_image=base64.b64encode(image_bytes()).decode(),
    )
    assert response.state.status == "collecting" and response.state.calculation is None
    assert not response.state.claim.receipt.confirmed and response.state.draft_id is None
    reviewed = assistant.respond(
        session_id=response.state.session_id,
        expected_revision=response.state.revision,
        confirm_receipt=True,
    )
    if missing_total:
        assert reviewed.state.status == "collecting"
        assert "receipt.total" in reviewed.state.validation.missing
        assert reviewed.state.calculation is None
    else:
        assert reviewed.state.status == "ready" and reviewed.state.calculation.amount == 30
        assert reviewed.state.calculation.citation["section"] == "Meal"
        assert any(item["section"] == "Meal" for item in reviewed.state.citations)
        saved = assistant.respond(
            session_id=reviewed.state.session_id,
            expected_revision=reviewed.state.revision,
            confirm=True,
        )
        assert saved.state.status == "saved"
        assert assistant.repository.draft(saved.state.draft_id)["submitted"] is False


class Batch(dict):
    def to(self, device):
        return self


class Pixel:
    def to(self, **kwargs):
        return self


def fake_model(text="Fictional receipt RM45.00", generated_length=3):
    processor = Mock()
    processor.return_value = Batch(pixel_values=Pixel(), input_ids=[1])
    processor.batch_decode.return_value = ["<s>scanned text</s>"]
    processor.post_process_generation.return_value = {"<OCR>": text}
    model = Mock(device="cpu", dtype="float32")
    model.generate.return_value = [[1] * generated_length]
    return SimpleNamespace(inference_mode=nullcontext), processor, model


def test_florence_uses_fixed_ocr_task_and_deterministic_generation(settings, monkeypatch):
    bundle = fake_model()
    loader = Mock(return_value=bundle)
    monkeypatch.setattr(florence, "_load_model", loader)
    assert scan_receipt(settings, image_bytes()) == "Fictional receipt RM45.00"
    loader.assert_called_once_with(settings.runtime / "models/florence", "cpu")
    _, processor, model = bundle
    assert processor.call_args.kwargs["text"] == "<OCR>"
    assert model.generate.call_args.kwargs["do_sample"] is False
    assert model.generate.call_args.kwargs["max_new_tokens"] == 1024
    assert processor.post_process_generation.call_args.kwargs["image_size"] == (32, 48)


@pytest.mark.parametrize("text,length", [("", 3), (None, 3), ("x" * 20001, 3), ("partial", 1024)])
def test_empty_or_truncated_ocr_never_returns_usable_evidence(settings, monkeypatch, text, length):
    monkeypatch.setattr(florence, "_load_model", Mock(return_value=fake_model(text, length)))
    with pytest.raises(OcrError):
        scan_receipt(settings, image_bytes())


def test_optional_dependencies_are_lazy_and_missing_packages_are_actionable(tmp_path, monkeypatch):
    florence._load_model.cache_clear()
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(OcrError, match="uv sync --extra florence"):
        florence._load_model(tmp_path, "cpu")


def test_native_model_loader_caches_and_disables_remote_code(tmp_path, monkeypatch):
    model = Mock()
    model.to.return_value = model
    model.eval.return_value = model
    processor_factory, model_factory = Mock(), Mock(return_value=model)
    torch = SimpleNamespace(float32="float32", float16="float16")
    transformers = SimpleNamespace(
        AutoProcessor=SimpleNamespace(from_pretrained=processor_factory),
        Florence2ForConditionalGeneration=SimpleNamespace(from_pretrained=model_factory),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    florence._load_model.cache_clear()
    try:
        first = florence._load_model(tmp_path, "cpu")
        assert florence._load_model(tmp_path, "cpu") is first
        assert processor_factory.call_count == model_factory.call_count == 1
        assert processor_factory.call_args.kwargs["trust_remote_code"] is False
        assert model_factory.call_args.kwargs["trust_remote_code"] is False
        assert model_factory.call_args.kwargs["use_safetensors"] is True
        assert model_factory.call_args.kwargs["dtype"] == "float32"
        model.to.assert_called_once_with("cpu")
    finally:
        florence._load_model.cache_clear()


def test_cuda_selection_fails_before_loading_when_unavailable(tmp_path, monkeypatch):
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    )
    processor_factory = Mock()
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoProcessor=SimpleNamespace(from_pretrained=processor_factory),
            Florence2ForConditionalGeneration=Mock(),
        ),
    )
    florence._load_model.cache_clear()
    with pytest.raises(OcrError, match="CLAIMS_FLORENCE_DEVICE=cpu"):
        florence._load_model(tmp_path, "cuda")
    processor_factory.assert_not_called()


def test_scanner_failure_does_not_expose_exception_payload(settings, monkeypatch):
    bundle = fake_model()
    bundle[2].generate.side_effect = RuntimeError("sensitive receipt or credentials")
    monkeypatch.setattr(florence, "_load_model", Mock(return_value=bundle))
    with pytest.raises(OcrError) as error:
        scan_receipt(settings, image_bytes())
    assert "sensitive" not in str(error.value)
