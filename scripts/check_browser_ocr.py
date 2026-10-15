"""Real browser OCR + HTTPS Vercel adapter + disposable PostgreSQL integration check.

Requires Playwright/Chromium, OpenSSL, and CLAIMS_TEST_DATABASE_URL. The OCR engine is real;
only the hosted text model is replaced with a local OpenAI-compatible protocol stub.
"""

import base64
import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import psycopg
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from psycopg import sql

from claims_assistant.tools.extract_receipt import text_fields

ROOT = Path(__file__).resolve().parents[1]
TODAY = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat()


def main() -> None:
    app_mode = os.getenv("CLAIMS_OCR_TEST_APP_MODE", "private")
    if app_mode not in {"private", "public"}:
        raise SystemExit("CLAIMS_OCR_TEST_APP_MODE must be private or public")
    database_url = os.environ.get("CLAIMS_TEST_DATABASE_URL")
    if not database_url:
        raise SystemExit("Set CLAIMS_TEST_DATABASE_URL to a disposable PostgreSQL database")
    schema = "browser_ocr_" + uuid4().hex
    with psycopg.connect(database_url) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    parsed = urlsplit(database_url)
    query = dict(parse_qsl(parsed.query))
    query["options"] = "-csearch_path=" + schema
    isolated_url = urlunsplit(parsed._replace(query=urlencode(query)))
    provider_calls = []
    provider_failure = [False]

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            assert self.path == "/v1/chat/completions"
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert self.headers["Authorization"] == "Bearer test-provider-key"
            assert payload["model"] == "test-text-only-model"
            assert payload["response_format"] == {"type": "json_object"}
            text = payload["messages"][1]["content"]
            assert isinstance(text, str) and "data:image/" not in text
            provider_calls.append(text)
            if provider_failure[0]:
                status, body = 429, {"error": {"message": "fictional quota test"}}
            else:
                status = 200
                body = {"choices": [{"message": {"content": json.dumps(text_fields(text))}}]}
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    server = None
    try:
        with tempfile.TemporaryDirectory(prefix="browser-ocr-check-") as directory:
            temporary = Path(directory)
            cert, key = temporary / "cert.pem", temporary / "key.pem"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=localhost",
                    "-addext",
                    "subjectAltName=IP:127.0.0.1,DNS:localhost",
                    "-keyout",
                    str(key),
                    "-out",
                    str(cert),
                ],
                check=True,
                capture_output=True,
            )
            public = subprocess.check_output(
                ["openssl", "x509", "-in", str(cert), "-pubkey", "-noout"]
            )
            der = subprocess.run(
                ["openssl", "pkey", "-pubin", "-outform", "DER"],
                input=public,
                capture_output=True,
                check=True,
            ).stdout
            spki = base64.b64encode(hashlib.sha256(der).digest()).decode()
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            origin = f"https://127.0.0.1:{port}"
            env = {
                **os.environ,
                "CLAIMS_APP_MODE": app_mode,
                "CLAIMS_API_TOKEN": "browser-ocr-test-token" if app_mode == "private" else "",
                "CLAIMS_DATABASE_URL": isolated_url,
                "CLAIMS_RUNTIME_DIR": directory,
                "CLAIMS_ROOT": str(ROOT),
                "CLAIMS_LLM_MODE": "openai",
                "CLAIMS_LLM_BASE_URL": f"http://127.0.0.1:{provider.server_port}/v1",
                "CLAIMS_LLM_MODEL": "test-text-only-model",
                "CLAIMS_LLM_API_KEY": "test-provider-key",
                "CLAIMS_RECEIPT_IMAGE_BACKEND": "browser",
                "VERCEL_URL": "127.0.0.1",
            }
            program = (
                "import sys, uvicorn; "
                "from claims_assistant.interfaces.vercel import create_vercel_app; "
                "uvicorn.run(create_vercel_app(), host='127.0.0.1', port=int(sys.argv[1]), "
                "ssl_certfile=sys.argv[2], ssl_keyfile=sys.argv[3], log_level='warning')"
            )
            server = subprocess.Popen(
                [sys.executable, "-c", program, str(port), str(cert), str(key)],
                cwd=ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            headers = (
                {"Authorization": "Bearer browser-ocr-test-token"} if app_mode == "private" else {}
            )
            with httpx.Client(
                verify=ssl.create_default_context(cafile=str(cert)), trust_env=False
            ) as client:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("HTTPS Vercel-adapter test server exited")
                    try:
                        if client.get(origin + "/api/health", headers=headers).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("HTTPS Vercel-adapter readiness failed")
                health = client.get(origin + "/api/health", headers=headers).json()
                assert health["receipt_image_backend"] == "browser"
                assert health["llm_timeout_seconds"] == 10

            sample, blank, corrupt = (
                temporary / "receipt.png",
                temporary / "blank.png",
                temporary / "bad.png",
            )
            font = ImageFont.truetype("DejaVuSansMono.ttf", 44)
            receipt_text = (
                f"Merchant: Fictional Browser Cafe\nDate: {TODAY}\nTotal: RM45.00\n"
                "Currency: MYR\nReceipt: OCR-TEST-001"
            )
            with Image.new("RGB", (1280, 650), "white") as image:
                ImageDraw.Draw(image).multiline_text(
                    (40, 50), receipt_text, font=font, fill="black", spacing=24
                )
                image.save(sample)
                image.save(temporary / "receipt.jpg", quality=95)
            with Image.new("RGB", (800, 500), "white") as image:
                image.save(blank)
            corrupt.write_bytes(b"not a PNG")
            oversized = temporary / "oversized.png"
            animated = temporary / "animated.png"
            with Image.new("RGB", (4001, 5000), "white") as image:
                image.save(oversized)
            with Image.new("RGB", (32, 32), "white") as first:
                with Image.new("RGB", (32, 32), "black") as second:
                    first.save(animated, save_all=True, append_images=[second], duration=100)
            errors, requests = [], []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=os.getenv("CLAIMS_BROWSER_EXECUTABLE"),
                    args=["--ignore-certificate-errors-spki-list=" + spki],
                    headless=True,
                )
                context = browser.new_context(viewport={"width": 1280, "height": 1000})
                context.on("request", lambda request: requests.append(request))
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith(origin + "/")
                        else route.abort()
                    ),
                )
                page = context.new_page()
                page.set_default_timeout(45000)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(origin, wait_until="networkidle")
                if app_mode == "private":
                    assert page.locator("#chooseReceipt").is_disabled()
                    page.fill("#token", "browser-ocr-test-token")
                    page.click("#connect")
                else:
                    assert page.locator("#credentials").is_hidden()
                page.wait_for_function("!document.querySelector('#chooseReceipt').disabled")
                page.fill("#employee", "OCR001")
                page.select_option("#category", "meal")
                page.fill("#amount", "45")
                page.fill("#purpose", "Fictional business lunch")
                page.check("#business")
                page.locator("#claimForm button[type=submit]").click()
                page.wait_for_function("!document.querySelector('#chooseReceipt').disabled")

                def upload(path):
                    with page.expect_file_chooser() as chosen:
                        page.click("#chooseReceipt")
                    chosen.value.set_files(path)
                    page.wait_for_function("document.body.getAttribute('aria-busy') === 'false'")

                context.route("**/assets/ocr/6.0.1/worker.min.js", lambda route: route.abort())
                upload(sample)
                assert "Browser OCR could not read" in page.locator("#error").inner_text()
                assert len(provider_calls) == 0
                context.unroute("**/assets/ocr/6.0.1/worker.min.js")
                page.click("#clearImage")
                upload(sample)
                page.wait_for_selector("#receipt-merchant")
                assert page.locator("#receipt-merchant").input_value() == "Fictional Browser Cafe"
                assert page.locator("#receipt-total").input_value() == "45.00"
                assert page.locator("#receipt-expense_date").input_value() == TODAY
                assert page.locator("#receipt-currency").input_value() == "MYR"
                assert page.locator("#receipt-receipt_number").input_value() == "OCR-TEST-001"
                assert page.locator("#save").is_disabled()
                page.click("#confirmEvidence")
                page.wait_for_function(
                    "document.querySelector('#claimAmount').textContent === 'RM 30.00'"
                )
                assert page.locator("#save").is_enabled()

                before = len(provider_calls)
                upload(blank)
                assert "No readable receipt text" in page.locator("#error").inner_text()
                assert len(provider_calls) == before and page.locator("#save").is_disabled()
                page.click("#clearImage")
                assert page.locator("#save").is_enabled()
                for invalid, expected in [
                    (oversized, "20 million pixels"),
                    (animated, "single-frame"),
                ]:
                    upload(invalid)
                    assert expected in page.locator("#error").inner_text()
                    assert len(provider_calls) == before and page.locator("#save").is_disabled()
                    page.click("#clearImage")
                upload(corrupt)
                assert "valid PNG or JPEG" in page.locator("#error").inner_text()
                assert len(provider_calls) == before and page.locator("#save").is_disabled()
                page.click("#clearImage")

                provider_failure[0] = True
                upload(sample)
                assert "HTTP 429" in page.locator("#conversation").inner_text()
                assert page.locator("#save").is_disabled()
                assert page.locator("#receiptText").input_value()
                provider_failure[0] = False
                page.click("#extract")
                page.wait_for_function("!document.querySelector('#confirmEvidence').disabled")
                page.click("#confirmEvidence")
                page.wait_for_function("!document.querySelector('#save').disabled")
                page.click("#save")
                page.wait_for_function(
                    "document.querySelector('#status').textContent === 'Draft saved'"
                )
                page.reload(wait_until="networkidle")
                if app_mode == "private":
                    page.fill("#token", "browser-ocr-test-token")
                    page.click("#connect")
                page.wait_for_function(
                    "document.querySelector('#status').textContent === 'Draft saved'"
                )
                session_id = page.evaluate("localStorage.getItem('claimSession')")
                cookies = {cookie["name"]: cookie["value"] for cookie in context.cookies()}
                with httpx.Client(
                    verify=ssl.create_default_context(cafile=str(cert)),
                    trust_env=False,
                    cookies=cookies,
                ) as client:
                    persisted = client.get(
                        origin + "/api/sessions/" + session_id, headers=headers
                    ).json()
                    evidence = persisted["claim"]["receipt"]
                    assert evidence["extraction_method"] == "browser_ocr_text"
                    assert evidence["confirmed"] is True
                    assert (
                        evidence["evidence_hash"]
                        == hashlib.sha256(provider_calls[-1].encode()).hexdigest()
                    )
                    draft = client.get(
                        origin + "/api/drafts/" + persisted["draft_id"], headers=headers
                    ).json()
                    assert draft["submitted"] is False and draft["status"] == "draft"
                if app_mode == "public":
                    other = browser.new_context()
                    other_page = other.new_page()
                    other_page.goto(origin, wait_until="networkidle")
                    # Use Chromium's certificate-pinned connection, as for the UI,
                    # rather than Playwright's separate Node HTTP client.
                    for path in [
                        "/api/sessions/" + session_id,
                        "/api/drafts/" + persisted["draft_id"],
                    ]:
                        assert (
                            other_page.evaluate("async path => (await fetch(path)).status", path)
                            == 404
                        )
                    other.close()
                page.click("#new")
                page.wait_for_function("!document.querySelector('#chooseReceipt').disabled")
                upload(temporary / "receipt.jpg")
                assert page.locator("#receipt-merchant").input_value() == "Fictional Browser Cafe"
                assert page.locator("#receipt-total").input_value() == "45.00"
                assert all(request.url.startswith(origin + "/") for request in requests)
                chat_payloads = [
                    json.loads(request.post_data)
                    for request in requests
                    if request.method == "POST" and request.url.endswith("/api/chat")
                ]
                scans = [body for body in chat_payloads if "receipt_ocr_text" in body]
                assert len(scans) >= 4
                assert not any("receipt_image" in body for body in chat_payloads)
                assert not errors, errors
                browser.close()
            print(
                json.dumps(
                    {
                        "real_tesseract_png_jpeg": "passed",
                        "app_mode": app_mode,
                        "public_visitor_isolation": "passed" if app_mode == "public" else "not run",
                        "model_transport": "text only",
                        "external_browser_requests": 0,
                        "blank_and_corrupt_images": "blocked",
                        "oversized_and_animated_images": "blocked",
                        "worker_failure_and_retry": "passed",
                        "provider_failure_and_retry": "passed",
                        "meal_cap": "30.00",
                        "explicit_review_and_save": "passed",
                        "postgres_resume": "passed",
                        "vercel_https_adapter": "passed",
                        "browser_errors": errors,
                    }
                )
            )
    finally:
        if server:
            server.terminate()
            server.wait(timeout=15)
        provider.shutdown()
        provider.server_close()
        with psycopg.connect(database_url) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    main()
