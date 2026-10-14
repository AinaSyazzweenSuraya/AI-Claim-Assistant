import base64
import hashlib
import re

from claims_assistant.agent.instructions import load
from claims_assistant.config import Settings
from claims_assistant.llm.client import ModelClient
from claims_assistant.schemas.receipt import Receipt
from claims_assistant.schemas.tool_result import ToolResult
from claims_assistant.vision.florence import OcrError, scan_receipt
from claims_assistant.vision.images import receipt_image


def text_fields(text: str) -> dict:
    fields = {}
    patterns = {
        "merchant": r"^merchant\s*:\s*(.+)$",
        "expense_date": r"^date\s*:\s*(\d{4}-\d{2}-\d{2})\s*$",
        "total": r"^total\s*:\s*(?:RM\s*|MYR\s*)?(\d+(?:\.\d{1,2})?)\s*(?:MYR|RM)?\s*$",
        "currency": r"^currency\s*:\s*([A-Z]{3})\s*$",
        "receipt_number": r"^(?:receipt|receipt number)\s*:\s*(.+)$",
    }
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text, re.I | re.M)
        fields[key] = matches[0].strip() if len(matches) == 1 else None
    explicit_currency = re.search(r"^currency\s*:", text, re.I | re.M)
    if not explicit_currency and re.search(r"^total\s*:\s*(RM|MYR)\s*\d", text, re.I | re.M):
        fields["currency"] = "MYR"
    if fields["currency"]:
        fields["currency"] = fields["currency"].upper()
    return fields


def extract_receipt(
    settings: Settings, text: str | None = None, image_base64: str | None = None
) -> ToolResult:
    if bool(text) == bool(image_base64):
        raise ValueError("Provide exactly one of text or image_base64")
    if text:
        if len(text) > 20000:
            raise ValueError("Receipt text exceeds 20,000 characters")
        raw = text.encode()
        fields = (
            text_fields(text)
            if settings.llm_mode == "demo"
            else ModelClient(settings).receipt(load(settings.root, "receipt_extraction.md"), text)
        )
        method = "text" if settings.llm_mode == "demo" else "model_text"
    else:
        if settings.llm_mode == "demo":
            if settings.receipt_image_backend == "florence":
                return ToolResult.error(
                    "TEXT_MODEL_REQUIRED",
                    "Florence reads image text; enable Ollama or a hosted "
                    "text model to extract the receipt fields",
                )
            return ToolResult.error("VISION_UNAVAILABLE", "Use labeled receipt text in demo mode")
        if len(image_base64) > 7_000_000:
            raise ValueError("Image exceeds 5 MiB")
        raw = base64.b64decode(image_base64, validate=True)
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("Image exceeds 5 MiB")
        if settings.receipt_image_backend == "florence":
            try:
                content = scan_receipt(settings, raw)
            except OcrError as exc:
                return ToolResult.error("OCR_UNAVAILABLE", str(exc))
            method = "florence_ocr_text"
        else:
            with receipt_image(raw):
                pass  # Reject corrupt or oversized images before any model request.
            mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
            content = [
                {"type": "text", "text": "Extract the receipt fields. Do not guess."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_base64}"}},
            ]
            method = "model_image"
        fields = ModelClient(settings).receipt(
            load(settings.root, "receipt_extraction.md"), content
        )
    receipt = Receipt(
        **fields,
        evidence_hash=hashlib.sha256(raw).hexdigest(),
        extraction_method=method,
        confirmed=False,
    )
    return ToolResult.success(receipt)
