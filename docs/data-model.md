# Data model

Claim: employee_id, category, expense_date, purpose, business_expense, currency=MYR,
distance_km/route or amount/receipt, and optional nights. Decimal values serialize as strings
to avoid floating-point changes. Dates are ISO YYYY-MM-DD. Receipt: merchant, expense_date,
total, currency, receipt_number, evidence_hash, confirmed, extraction_method.
For transaction screenshots, merchant represents the visible payee and receipt_number the
visible transaction reference. Local Florence sets extraction_method=florence_ocr_text.
Browser OCR sets extraction_method=browser_ocr_text and evidence_hash to the SHA-256 of the
received UTF-8 OCR text. The client-supplied text is not verified against the image; this
hash must not be described as an original-image hash or proof of the OCR engine used.
Vision/Florence evidence hashes use original image bytes; ordinary text uses UTF-8 text.
Image pixels and raw OCR text are not stored
automatically. The browser image preview is temporary and is not restored with a session.

AgentState: session UUID, revision, status, Claim, validation report, calculation, policy
citations, bounded last-20-message history, optional draft UUID. Draft: UUID, session UUID,
status=draft, claim snapshot, calculation snapshot, citations, submitted=false.

SQLite sessions store ID, revision, JSON payload. Drafts store ID, foreign-key session ID,
unique raw evidence hash and canonical merchant/date/total/currency/number fingerprint,
JSON payload, and UTC created_at. No raw image/text uploads are stored automatically.
Canonical hashes are duplicate heuristics, not proof of receipt identity or authenticity.

Public browser ownership uses a separate session_owners table: session_id (primary/foreign
key) and owner_hash (SHA-256 of a random 256-bit visitor cookie). Session creation and owner
binding commit together. Ownership is checked before loading or modifying a session, or
exporting its drafts. Owner secrets/hashes are excluded from state and exports. Startup
adds this table without changing existing records; unowned records remain inaccessible in
public mode. Private shared-token mode retains access to all records.

On Vercel the same tables and JSON payloads are stored in PostgreSQL, selected using
CLAIMS_DATABASE_URL. Revision checks, unique evidence constraints, and atomic draft/session
transactions work across function instances. Database URLs are secret configuration and
are never included in API state or draft exports.

Policy manifest: ID/version, inclusive effective_from/effective_to, document paths, rules file.
Rules contain aligned metadata, currency, deadline, rounding, per-category rates and caps.
Exactly one version must apply to an expense date; missing/overlapping versions are rejected.
