"""Reproduce the pinned, self-hosted OCR assets; no npm install is needed at deployment."""

import base64
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

DESTINATION = (
    Path(__file__).resolve().parents[1] / "src/claims_assistant/interfaces/static/ocr/6.0.1"
)
PACKAGES = [
    (
        "https://registry.npmjs.org/tesseract.js/-/tesseract.js-6.0.1.tgz",
        "/sPvMvrCtgxnNRCjbTYbr7BRu0yfWDsMZQ2a/T5aN/L1t8wUQN6tTWv6p6FwzpoEBA0jrN2UD2SX4QQFRdoDbA==",
        {
            "dist/tesseract.min.js": "tesseract.min.js",
            "dist/worker.min.js": "worker.min.js",
            "dist/tesseract.min.js.LICENSE.txt": "tesseract.min.js.LICENSE.txt",
            "dist/worker.min.js.LICENSE.txt": "worker.min.js.LICENSE.txt",
            "LICENSE.md": "TESSERACT-JS-LICENSE.txt",
        },
    ),
    (
        "https://registry.npmjs.org/tesseract.js-core/-/tesseract.js-core-6.0.0.tgz",
        "1Qncm/9oKM7xgrQXZXNB+NRh19qiXGhxlrR8EwFbK5SaUbPZnS5OMtP/ghtqfd23hsr1ZvZbZjeuAGcMxd/ooA==",
        {
            "tesseract-core-lstm.wasm.js": "tesseract-core-lstm.wasm.js",
            "tesseract-core-simd-lstm.wasm.js": "tesseract-core-simd-lstm.wasm.js",
            "LICENSE": "TESSERACT-CORE-LICENSE.txt",
        },
    ),
    (
        "https://registry.npmjs.org/@tesseract.js-data/eng/-/eng-1.0.0.tgz",
        "mbTumm6KQPUHyzTPQaF3ObXYnx0SqqfV2nabqFVQBwD6Kl7PhGSLSzOlfFTWy0P3BjghaSKA2W9GB19Jk+ZcTg==",
        {
            "4.0.0_best_int/eng.traineddata.gz": "eng.traineddata.gz",
            "package.json": "ENG-PACKAGE.json",
        },
    ),
]


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    manifest = {"packages": [], "files": {}}
    for url, expected, files in PACKAGES:
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read()
        digest = base64.b64encode(hashlib.sha512(payload).digest()).decode()
        if digest != expected:
            raise ValueError("OCR package integrity check failed")
        manifest["packages"].append({"url": url, "integrity": "sha512-" + expected})
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for source, destination in files.items():
                # Only explicit files are read; archive paths are never extracted.
                content = archive.extractfile("package/" + source).read()
                (DESTINATION / destination).write_bytes(content)
                manifest["files"][destination] = hashlib.sha256(content).hexdigest()
    (DESTINATION / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Verified and wrote {len(manifest['files'])} OCR assets")


if __name__ == "__main__":
    main()
