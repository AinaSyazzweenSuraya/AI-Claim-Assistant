"""Optional browser regression check; see docs/review-findings.md for setup."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
artifacts = root / "evaluations/results/browser"
artifacts.mkdir(parents=True, exist_ok=True)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
url = f"http://127.0.0.1:{port}"
today = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat()
errors = []
with tempfile.TemporaryDirectory(prefix="claims-ui-check-") as directory:
    sample_image = Path(directory) / "fictional-transaction.png"
    with Image.new("RGB", (640, 240), "white") as receipt:
        ImageDraw.Draw(receipt).text(
            (20, 20), f"Fictional Payee\n{today}\nRM45.00\nReference UI001", fill="black"
        )
        receipt.save(sample_image)
    env = os.environ.copy()
    env.update(
        CLAIMS_RUNTIME_DIR=directory,
        CLAIMS_LLM_MODE="demo",
        CLAIMS_RECEIPT_IMAGE_BACKEND="vision",
        CLAIMS_APP_MODE="demo",
        CLAIMS_API_TOKEN="",
        CLAIMS_DATABASE_URL="",
    )
    cli = [sys.executable, "-c", "from claims_assistant.interfaces.cli import main; main()"]
    subprocess.run([*cli, "ingest"], cwd=root, env=env, check=True, capture_output=True)
    server = subprocess.Popen(
        [*cli, "web", "--port", str(port)],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(trust_env=False) as client:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Test server exited before startup")
                try:
                    if client.get(url + "/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Server readiness failed")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=os.getenv("CLAIMS_BROWSER_EXECUTABLE"), headless=True
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.emulate_media(reduced_motion="reduce")
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url, wait_until="networkidle")
            assert page.evaluate("document.characterSet") == "UTF-8"
            assert (
                page.locator(".welcome").evaluate("element => getComputedStyle(element).whiteSpace")
                == "normal"
            )
            assert "We’ll check the policy" in page.locator(".intro").inner_text()
            assert "Development policy · Fictional rates" in page.locator(".notice").inner_text()
            assert page.locator("#step1").inner_text() == "01 · Add details"
            assert page.locator("#step2").inner_text() == "02 · Check evidence"
            assert page.locator("#step3").inner_text() == "03 · Review & save"
            assert page.locator("#claimAmount").inner_text() == "Not calculated yet"
            assert page.locator("#save").is_disabled()
            contrast = page.evaluate("""() => {
              const rgb = value => (value.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
              const luminance = value => rgb(value).map(c => {
                c /= 255;
                return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
              }).reduce((sum, c, i) => sum + c * [.2126, .7152, .0722][i], 0);
              const selectors = ['body', 'label[for=employee]', '#employee', '#mode',
                '#receiptHint', '.section-kicker', '#claimForm > .primary', '#chooseReceipt'];
              return selectors.map(selector => {
                const element = document.querySelector(selector);
                const foreground = luminance(getComputedStyle(element).color);
                let parent = element;
                let backgrounds = [];
                while (parent) {
                  const style = getComputedStyle(parent);
                  backgrounds = style.backgroundImage.match(/rgb\\([^)]*\\)/g) || [];
                  if (backgrounds.length) break;
                  if (style.backgroundColor !== 'rgba(0, 0, 0, 0)') {
                    backgrounds = [style.backgroundColor]; break;
                  }
                  parent = parent.parentElement;
                }
                const ratios = backgrounds.map(value => {
                  const background = luminance(value);
                  return (Math.max(foreground, background) + .05) /
                    (Math.min(foreground, background) + .05);
                });
                return {selector, ratio: Math.min(...ratios)};
              });
            }""")
            assert all(item["ratio"] >= 4.5 for item in contrast), contrast
            assert page.locator("#chooseReceipt").is_enabled()
            with page.expect_file_chooser() as chooser:
                page.click("#chooseReceipt")
            chooser.value.set_files([])
            page.click("#new")
            page.wait_for_function("document.querySelector('#issues li') !== null")
            assert "Employee ID" in page.locator("#issues").inner_text()
            assert "Business expense confirmation" in page.locator("#issues").inner_text()
            assert "employee_id" not in page.locator("#issues").inner_text()
            assert "business_expense" not in page.locator("#issues").inner_text()
            page.screenshot(path=str(artifacts / "empty.png"), full_page=True)
            page.fill("#employee", "UI001")
            page.fill("#distance", "25")
            page.fill("#route", "KL to PJ")
            page.fill("#purpose", "Client meeting at Café Example")
            page.check("#business")
            held_requests = []
            page.route("**/api/chat", lambda route: held_requests.append(route))
            page.locator("#claimForm button[type=submit]").click()
            page.wait_for_function("document.querySelector('#chooseReceipt').disabled === true")
            assert "current request" in page.locator("#uploadHint").inner_text()
            assert page.locator("#receiptFile").is_disabled()
            assert held_requests
            held_requests[0].fulfill(status=503, json={"detail": "Temporary test failure"})
            page.wait_for_function("document.querySelector('#chooseReceipt').disabled === false")
            page.unroute("**/api/chat")
            # A rejected or interrupted request must show its error beside the chat,
            # preserve the edited fields, and never look like a completed turn.
            failures = [
                (
                    403,
                    "application/json",
                    '{"detail":"Cross-origin requests are disabled"}',
                    "Cross-origin requests are disabled",
                ),
                (503, "text/html", "<html>Service unavailable</html>", "503"),
                (200, "application/json", "{}", "incomplete reply"),
            ]
            for status, content_type, body, expected_error in failures:
                page.route(
                    "**/api/chat",
                    lambda route, request, status=status, content_type=content_type, body=body: (
                        route.fulfill(status=status, content_type=content_type, body=body)
                    ),
                )
                page.locator("#claimForm button[type=submit]").click()
                page.wait_for_function(
                    "document.querySelector('body').getAttribute('aria-busy') === 'false'"
                )
                assert expected_error in page.locator("#chatError").inner_text()
                assert "Reply unavailable" in page.locator(".bubble.failed").last.inner_text()
                assert page.locator("#employee").input_value() == "UI001"
                assert page.locator("#distance").input_value() == "25"
                assert page.locator("#claimAmount").inner_text() == "Not calculated yet"
                assert page.locator("#save").is_disabled()
                page.unroute("**/api/chat")
            page.route("**/api/chat", lambda route: route.abort())
            page.locator("#claimForm button[type=submit]").click()
            page.wait_for_function(
                "document.querySelector('#chatError').textContent.includes('Unable to reach')"
            )
            page.fill("#message", "I drove 25 km today")
            page.locator("#chatForm button").click()
            page.wait_for_function(
                "document.querySelector('#message').value === 'I drove 25 km today'"
            )
            page.unroute("**/api/chat")
            page.route(
                "**/api/chat",
                lambda route: route.fulfill(
                    status=401,
                    content_type="application/json",
                    body='{"detail":"A valid service token is required"}',
                ),
            )
            page.locator("#claimForm button[type=submit]").click()
            page.wait_for_function(
                "document.querySelector('#chatError').textContent.includes('access token')"
            )
            page.wait_for_function("document.querySelector('#employee').disabled === true")
            assert page.locator("#credentials").is_visible()
            assert page.locator("#chatForm button").is_disabled()
            page.unroute("**/api/chat")
            page.click("#connect")
            page.wait_for_function("document.querySelector('#employee').disabled === false")
            assert page.locator("#employee").input_value() == "UI001"
            assert page.locator("#distance").input_value() == "25"
            page.locator("#claimForm button[type=submit]").click()
            page.wait_for_function(
                "document.querySelector('#status').textContent === 'Ready for your review'"
            )
            assert page.locator("#claimAmount").inner_text() == "RM 15.00"
            page.fill("#distance", "50")
            assert page.locator("#save").is_disabled()
            assert "details changed" in page.locator("#reviewHint").inner_text().lower()
            page.locator("#claimForm button[type=submit]").click()
            page.wait_for_function(
                "document.querySelector('#claimAmount').textContent === 'RM 30.00'"
            )
            page.click("#save")
            page.wait_for_function(
                "document.querySelector('#status').textContent === 'Draft saved'"
            )
            with page.expect_download() as event:
                page.click("#download")
            event.value.save_as(str(artifacts / "claim-draft.json"))
            saved = json.loads(
                Path(str(artifacts / "claim-draft.json")).read_text(encoding="utf-8")
            )
            assert saved["calculation"]["amount"] == "30.00"
            assert "Café" in saved["claim"]["purpose"]
            assert saved["submitted"] is False
            page.reload(wait_until="networkidle")
            page.wait_for_function(
                "document.querySelector('#status').textContent === 'Draft saved'"
            )
            assert "Saved as a draft" in page.locator("#issues").inner_text()
            assert page.locator("#chooseReceipt").is_disabled()
            assert page.locator("#receiptFile").is_disabled()
            assert "Click New claim" in page.locator("#uploadHint").inner_text()
            page.click("#new")
            page.wait_for_function("document.querySelector('#employee').value === ''")
            assert page.locator("#chooseReceipt").is_enabled()
            assert page.locator("#expenseDate").input_value() == today
            assert page.locator("#receiptText").input_value() == ""
            assert "Café" not in page.locator("#conversation").inner_text()
            page.fill("#employee", "UI001")
            page.select_option("#category", "meal")
            page.fill("#amount", "45")
            page.fill("#purpose", "Business lunch")
            page.check("#business")
            page.locator("#claimForm button[type=submit]").click()
            page.wait_for_function(
                "document.querySelector('#issues').textContent.includes('Supporting receipt')"
            )
            page.fill(
                "#receiptText",
                f"Merchant: Café UI Example\nDate: {today}\nTotal: RM45.00\nReceipt: UI001",
            )
            page.click("#extract")
            page.wait_for_selector("#receipt-merchant")
            assert page.locator("#receipt-merchant").input_value() == "Café UI Example"
            assert "Review and confirm receipt details" in page.locator("#issues").inner_text()
            page.fill("#purpose", "Business lunch with the new client")
            page.click("#confirmEvidence")
            page.wait_for_function(
                "document.querySelector('#status').textContent === 'Ready for your review'"
            )
            assert page.locator("#claimAmount").inner_text() == "RM 30.00"
            assert page.locator("#purpose").input_value() == "Business lunch with the new client"
            assert page.locator("#save").is_disabled()
            page.locator("#claimForm button[type=submit]").click()
            page.wait_for_function("document.querySelector('#save').disabled === false")
            with page.expect_file_chooser() as chooser:
                page.click("#chooseReceipt")
            chooser.value.set_files(sample_image)
            page.wait_for_function(
                "document.querySelector('#conversation').textContent"
                ".includes('Use labeled receipt text in demo mode')"
            )
            assert page.locator("#receiptPreview").is_visible()
            assert page.locator("#save").is_disabled()
            assert "new image has not been extracted" in page.locator("#reviewHint").inner_text()
            page.click("#clearImage")
            assert page.locator("#receiptPreview").is_hidden()
            assert page.locator("#receiptFile").input_value() == ""
            page.locator("#claimForm button[type=submit]").click()
            page.wait_for_function("document.querySelector('#save').disabled === false")
            page.fill("#receiptText", f"Merchant: New Cafe\nDate: {today}\nTotal: RM45.00")
            assert page.locator("#save").is_disabled()
            page.fill("#message", "confirm")
            page.locator("#chatForm button[type=submit]").click()
            assert "pending changes" in page.locator("#error").inner_text()
            assert page.locator("#status").text_content() == "Ready for your review"
            page.fill("#receiptText", "")
            assert page.locator("#save").is_enabled()
            page.locator("#claimForm button[type=submit]").click()
            page.wait_for_function("document.querySelector('#save').disabled === false")
            assert "â" not in page.locator("body").inner_text()
            assert "Ã" not in page.locator("body").inner_text()
            assert "Â" not in page.locator("body").inner_text()
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(
                path=str(artifacts / "desktop.png"), full_page=True, animations="disabled"
            )
            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(
                path=str(artifacts / "mobile.png"), full_page=True, animations="disabled"
            )
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            login = browser.new_page()
            login.on("pageerror", lambda error: errors.append(str(error)))

            def authenticate(route):
                if route.request.headers.get("authorization") == "Bearer browser-test-token":
                    route.continue_()
                else:
                    route.fulfill(status=401, json={"detail": "A valid service token is required"})

            login.route("**/api/health", authenticate)
            login.goto(url, wait_until="networkidle")
            assert login.locator("#credentials").is_visible()
            assert login.locator("#employee").is_disabled()
            assert login.locator("#chatForm button").is_disabled()
            assert login.locator("#chooseReceipt").is_disabled()
            assert "assistant connects" in login.locator("#uploadHint").inner_text()
            assert login.locator("#retryConnection").is_visible()
            login.click("#retryConnection")
            login.wait_for_function(
                "document.querySelector('body').getAttribute('aria-busy') === 'false'"
            )
            assert login.locator("#chooseReceipt").is_disabled()
            login.set_viewport_size({"width": 320, "height": 720})
            assert login.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            login.fill("#token", "wrong-token")
            login.click("#connect")
            login.wait_for_function(
                "document.querySelector('#chatError').textContent.includes('not accepted')"
            )
            assert login.locator("#employee").is_disabled()
            login.fill("#token", "  browser-test-token  ")
            login.click("#connect")
            login.wait_for_function("document.querySelector('#employee').disabled === false")
            assert login.locator("#chatError").inner_text() == ""
            assert login.locator("#mode").inner_text() == "Demo mode"
            assert login.locator("#chooseReceipt").is_enabled()
            assert login.locator("#retryConnection").is_hidden()
            assert login.evaluate("localStorage.getItem('claimSession')") is None
            assert not errors, errors
            browser.close()
        print(
            json.dumps(
                {
                    "browser_errors": errors,
                    "unicode": "correct",
                    "text_contrast": "AA checked for key controls and labels",
                    "field_labels": "readable",
                    "mileage_save_export": "30.00",
                    "meal_cap": "30.00",
                    "reset_and_resume": "passed",
                    "pending_edits": "protected",
                    "failed_requests_and_auth_recovery": "passed",
                    "image_preview_and_failed_scan_guard": "passed",
                    "native_file_picker_and_disabled_reasons": "passed",
                    "mobile_overflow": False,
                }
            )
        )
    finally:
        if errors:
            print("Browser errors:", errors)
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
