# Evaluation plan

Run pytest for precise invariants and scripts/run_evaluations.py for complete fixed-clock flows.
The JSONL cases cover mileage rounding/caps, meal and lodging limits, missing information,
unsupported expense/currency, personal expense, expired/future dates, receipt review/mismatch,
tool failures, accurate policy citations, and saved-draft behavior. Each case runs isolated from
real runtime data. The runner reports pass/fail for each assertion and exits nonzero on failures.

Acceptance: all deterministic cases pass; no amount is produced for invalid claims; every ready
draft cites the applicable policy ID/version/section/source; saving requires a separate explicit
confirmation; receipt reuse and stale revisions cannot commit. Test source/rule numeric alignment
and stale-index behavior. Protocol mocks test malformed models and tools, not live AI quality.

For Ollama, separately run representative natural-language requests with the installed model,
compare extracted fields to truth, and record model tag, hardware, time, field accuracy, tool-call
success, hallucinated fields, and policy citation correctness. Include prompt injection attempts
in receipts and requests. Target zero unsupported approvals/saves and zero invented amounts.
Evaluate vision against manually labeled fictional images before enabling it for real receipts.
Provider and OCR quality depend on the selected model; deterministic evaluations do not prove them.

The optional Florence path has mocked integration tests for image decoding, pixel/byte limits,
EXIF orientation, native model loading options, OCR task/output limits, hash preservation,
required-field extraction/review, retrieved citations, and complete draft saving. These prove
control flow, not real OCR quality. Separately run `claims ocr PATH` on manually labeled
receipt photos and transaction screenshots; record model checkpoint, package versions,
CPU/GPU, elapsed time, exact merchant/payee/date/total/currency/reference accuracy, and missing
or invented values. Include blur, cropped totals, multiple dates/currencies, and printed
instruction attacks. Every OCR-extracted record must require explicit user confirmation.

Browser OCR: run `scripts/check_browser_ocr.py` with Playwright/Chromium, OpenSSL, DejaVu
Sans Mono, and disposable PostgreSQL. It uses real self-hosted Tesseract.js on fictional
PNG/JPEG images and the HTTPS Vercel adapter; a local OpenAI-compatible stub checks that
the provider receives text only. Check exact merchant/date/amount/currency/reference,
no external browser requests or image API payloads, blank/corrupt images, provider rate-limit
retry from retained OCR text, pending-image save guards, separate confirmations, RM30 cap,
PostgreSQL restoration, and persisted text-hash metadata. Unit tests additionally cover
source exclusivity, bounded text, asset hashes, duplicates, and server-image rejection.
These checks prove integration on generated clear English receipts. Live Groq output,
real staff-image quality, free-tier capacity, and the user's actual Vercel deployment remain
separate acceptance checks. See [the browser OCR guide](browser-ocr.md).

Public access: test two independent cookie jars for session creation, read/update isolation,
draft save/export isolation, blocked legacy records, cookie attributes, identity spoofing,
cross-origin rejection, and persistence after a Vercel/PostgreSQL cold start. Existing
private-token tests must still pass. Run `CLAIMS_UI_TEST_APP_MODE=public` with
`scripts/check_web_ui.py` for automatic connection, real browser cookies, reload/export,
and separate browser contexts. Run `CLAIMS_OCR_TEST_APP_MODE=public` with
`scripts/check_browser_ocr.py` for no-token HTTPS/Vercel/PostgreSQL OCR integration.
