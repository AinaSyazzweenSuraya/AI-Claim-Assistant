# Tool contracts

All tools return `{ok: bool, data: object|null, code: string|null, message: string|null}`.
Validation issues are successful tool execution with `data.valid=false`; transport/input/tool
failures use `ok=false`. Common codes: INVALID_INPUT, UNKNOWN_TOOL, STORAGE_ERROR,
MODEL_UNAVAILABLE, VISION_UNAVAILABLE, CONFIRMATION_REQUIRED, REVIEW_CHANGED, DUPLICATE_RECEIPT.
Local scanning also returns OCR_UNAVAILABLE and TEXT_MODEL_REQUIRED when prerequisites fail.
Browser mode returns BROWSER_OCR_REQUIRED for direct server-image requests.

| Tool | Input | Successful output | Failure behavior |
| --- | --- | --- | --- |
| search_policy | query, expense date from state | section text and citation metadata | stale/missing index fails; no match returns [] |
| update_claim | partial Claim fields, excluding receipt | validated merged Claim | unknown fields/ranges reject update |
| extract_receipt | exactly one text, image_base64, or ocr_text | proposed Receipt, confirmed=false | empty/oversized text or multiple sources fail; ambiguous fields stay null |
| validate_claim | current Claim, rule store, current date | valid, missing, errors, policy ID/version | version problems appear as validation errors |
| calculate_claim | current valid Claim | amount, requested amount, cap, formula, citation | invalid claim never gets an amount |
| save_draft | ready state and server-side explicit confirmation | proposed local draft write | no confirmation, changed calculation, duplicate receipt block write |

Only update_claim and search_policy are offered to the model. Other tools are orchestrated by
the server. save_draft prepares data; the runner persists it atomically with the session.

`CLAIMS_RECEIPT_IMAGE_BACKEND=florence` runs local `<OCR>` followed by text-model field
extraction; `vision` uses the selected model's image interface. PNG/JPEG bytes are decoded
and verified, limited to 5 MiB/20 million pixels/single frame, and EXIF orientation is normalized
for local OCR. Empty/truncated scans fail instead of returning partial usable evidence.
Extraction metadata is `florence_ocr_text` for the local path. Duplicate hashes cover the
original image bytes, not the OCR text. No raw OCR text or image is automatically persisted.

`CLAIMS_RECEIPT_IMAGE_BACKEND=browser` performs Tesseract OCR on the client. `ocr_text` is
bounded to 20,000 nonblank characters and passed to the same text model (or limited demo
parser). Metadata is `browser_ocr_text`; the server hashes received text, not the original
image. Clients can alter that text, so the metadata is not trusted provenance. Direct images
are rejected with BROWSER_OCR_REQUIRED. No original image bytes are sent through this path.

API: POST /api/sessions, GET /api/sessions/{UUID}, POST /api/chat,
GET /api/drafts/{UUID}, GET /api/health. Chat supports message, fields, receipt_text,
receipt_image (base64 PNG/JPEG, ≤5 MiB), receipt_ocr_text (browser OCR text),
receipt_fields (visible corrections), confirm_receipt,
confirm, session_id, expected_revision. Receipt text is limited to 20,000 characters.
Confirmation requires a prior session and displayed revision. All API endpoints require the
configured bearer token in private mode (required) or local demo mode when set. Public mode
does not require/use that token: retain its HttpOnly visitor cookie for session/chat/draft
access. A missing or different owner receives the same 404 as an unknown record; clients
cannot set owner_hash in JSON. HTTP 401=authentication,
403=origin/loopback restriction, 404=unknown record, 409=revision/duplicate conflict,
422=malformed request, 503=policy-index readiness failure. Tool failures remain structured
in a normal chat response so the user can correct fields or retry a service after diagnosis.
