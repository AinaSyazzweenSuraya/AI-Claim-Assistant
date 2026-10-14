"""Florence-2 OCR; the text LLM subsequently proposes receipt fields.

Uses Transformers' native Florence implementation and its documented converted
base checkpoint, without executing code downloaded from a model repository.
"""

import threading
from functools import lru_cache
from pathlib import Path

from claims_assistant.config import Settings
from claims_assistant.vision.images import receipt_image

MODEL_ID = "florence-community/Florence-2-base"
TASK = "<OCR>"
MAX_NEW_TOKENS = 1024
SCAN_LOCK = threading.Lock()


class OcrError(RuntimeError):
    """A scanner failure whose message contains no receipt or credential data."""


@lru_cache(maxsize=1)
def _load_model(cache_dir: Path, device: str):
    try:
        import torch
        from transformers import AutoProcessor, Florence2ForConditionalGeneration
    except (ImportError, OSError, RuntimeError) as exc:
        raise OcrError("Install Florence packages with uv sync --extra florence") from exc
    if device == "cuda" and not torch.cuda.is_available():
        raise OcrError("CUDA is unavailable; set CLAIMS_FLORENCE_DEVICE=cpu")
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        dtype = torch.float32 if device == "cpu" else torch.float16
        processor = AutoProcessor.from_pretrained(
            MODEL_ID, cache_dir=str(cache_dir), trust_remote_code=False
        )
        model = (
            Florence2ForConditionalGeneration.from_pretrained(
                MODEL_ID,
                cache_dir=str(cache_dir),
                dtype=dtype,
                trust_remote_code=False,
                use_safetensors=True,
            )
            .to(device)
            .eval()
        )
        return torch, processor, model
    except Exception as exc:
        raise OcrError(
            "Florence could not load. Check installed packages, available memory, "
            "and access to the Hugging Face model download."
        ) from exc


def scan_receipt(settings: Settings, raw: bytes) -> str:
    """Return untrusted OCR text; never confirm evidence or calculate an amount."""
    with receipt_image(raw) as image:
        with SCAN_LOCK:
            torch, processor, model = _load_model(
                settings.runtime / "models/florence", settings.florence_device
            )
            try:
                inputs = processor(text=TASK, images=image, return_tensors="pt").to(model.device)
                inputs["pixel_values"] = inputs["pixel_values"].to(dtype=model.dtype)
                with torch.inference_mode():
                    generated = model.generate(
                        **inputs, max_new_tokens=MAX_NEW_TOKENS, num_beams=3, do_sample=False
                    )
                if len(generated[0]) >= MAX_NEW_TOKENS:
                    raise OcrError(
                        "Receipt scan reached its text limit; use a shorter receipt image"
                    )
                text = processor.batch_decode(generated, skip_special_tokens=False)[0]
                parsed = processor.post_process_generation(text, task=TASK, image_size=image.size)
                text = parsed.get(TASK)
                if not isinstance(text, str) or not text.strip():
                    raise OcrError(
                        "No readable receipt text found; use a clearer image or paste text"
                    )
                if len(text) > 20000:
                    raise OcrError("Receipt scan exceeds 20,000 characters; use a shorter image")
                return text.strip()
            except OcrError:
                raise
            except Exception as exc:
                raise OcrError(
                    "Receipt scanning failed; retry with a clear single receipt image"
                ) from exc
