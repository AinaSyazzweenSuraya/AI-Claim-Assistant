import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


def receipt_image(raw: bytes) -> Image.Image:
    """Decode one bounded PNG/JPEG and normalize its orientation in memory."""
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds 5 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise ValueError("Only PNG and JPEG receipts are supported")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Receipt image exceeds 20 million pixels")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Use a single receipt image")
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                return ImageOps.exif_transpose(image).convert("RGB")
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("Receipt image is invalid or too large; use a clear PNG or JPEG") from exc
