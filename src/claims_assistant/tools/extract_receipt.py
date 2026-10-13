import base64
import hashlib
import re

from claims_assistant.agent.instructions import load
from claims_assistant.config import Settings
from claims_assistant.llm.client import ModelClient
from claims_assistant.schemas.receipt import Receipt
from claims_assistant.schemas.tool_result import ToolResult


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
    if fields["currency"] is None and re.search(r"^total\s*:\s*(RM|MYR)\s*\d", text, re.I | re.M):
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
            return ToolResult.error("VISION_UNAVAILABLE", "Use labeled receipt text in demo mode")
        if len(image_base64) > 7_000_000:
            raise ValueError("Image exceeds 5 MiB")
        raw = base64.b64decode(image_base64, validate=True)
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("Image exceeds 5 MiB")
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif raw.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        else:
            raise ValueError("Only PNG and JPEG are supported")
        fields = ModelClient(settings).receipt(
            load(settings.root, "receipt_extraction.md"),
            [
                {"type": "text", "text": "Extract the receipt fields. Do not guess."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_base64}"}},
            ],
        )
        method = "model_image"
    receipt = Receipt(
        **fields,
        evidence_hash=hashlib.sha256(raw).hexdigest(),
        extraction_method=method,
        confirmed=False,
    )
    return ToolResult.success(receipt)
