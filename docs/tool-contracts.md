# Tool contracts

All tools return `{ok: bool, data: object|null, code: string|null, message: string|null}`.
Validation issues are successful tool execution with `data.valid=false`; transport/input/tool
failures use `ok=false`. Common codes: INVALID_INPUT, UNKNOWN_TOOL, STORAGE_ERROR,
MODEL_UNAVAILABLE, VISION_UNAVAILABLE, CONFIRMATION_REQUIRED, REVIEW_CHANGED, DUPLICATE_RECEIPT.

| Tool | Input | Successful output | Failure behavior |
| --- | --- | --- | --- |
| search_policy | query, expense date from state | section text and citation metadata | stale/missing index fails; no match returns [] |
| update_claim | partial Claim fields, excluding receipt | validated merged Claim | unknown fields/ranges reject update |
| extract_receipt | exactly one text or image_base64 | proposed Receipt, confirmed=false | ambiguous fields stay null; unsupported vision fails |
| validate_claim | current Claim, rule store, current date | valid, missing, errors, policy ID/version | version problems appear as validation errors |
| calculate_claim | current valid Claim | amount, requested amount, cap, formula, citation | invalid claim never gets an amount |
| save_draft | ready state and server-side explicit confirmation | proposed local draft write | no confirmation, changed calculation, duplicate receipt block write |

Only update_claim and search_policy are offered to the model. Other tools are orchestrated by
the server. save_draft prepares data; the runner persists it atomically with the session.

API: POST /api/sessions, GET /api/sessions/{UUID}, POST /api/chat,
GET /api/drafts/{UUID}, GET /api/health. Chat supports message, fields, receipt_text,
receipt_image (base64 PNG/JPEG, ≤5 MiB), receipt_fields (visible corrections), confirm_receipt,
confirm, session_id, expected_revision. Receipt text is limited to 20,000 characters.
Confirmation requires a prior session and displayed revision. All API endpoints require the
configured bearer token when present. Private mode requires a token. HTTP 401=authentication,
403=origin/loopback restriction, 404=unknown record, 409=revision/duplicate conflict,
422=malformed request, 503=policy-index readiness failure. Tool failures remain structured
in a normal chat response so the user can correct fields or retry a service after diagnosis.
