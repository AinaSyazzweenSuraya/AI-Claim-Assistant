# Data model

Claim: employee_id, category, expense_date, purpose, business_expense, currency=MYR,
distance_km/route or amount/receipt, and optional nights. Decimal values serialize as strings
to avoid floating-point changes. Dates are ISO YYYY-MM-DD. Receipt: merchant, expense_date,
total, currency, receipt_number, evidence_hash, confirmed, extraction_method.
For transaction screenshots, merchant represents the visible payee and receipt_number the
visible transaction reference. Local Florence sets extraction_method=florence_ocr_text.
Evidence hashes use the original image bytes; image pixels and raw OCR text are not stored
automatically. The browser image preview is temporary and is not restored with a session.

AgentState: session UUID, revision, status, Claim, validation report, calculation, policy
citations, bounded last-20-message history, optional draft UUID. Draft: UUID, session UUID,
status=draft, claim snapshot, calculation snapshot, citations, submitted=false.

SQLite sessions store ID, revision, JSON payload. Drafts store ID, foreign-key session ID,
unique raw evidence hash and canonical merchant/date/total/currency/number fingerprint,
JSON payload, and UTC created_at. No raw image/text uploads are stored automatically.
Canonical hashes are duplicate heuristics, not proof of receipt identity or authenticity.

On Vercel the same tables and JSON payloads are stored in PostgreSQL, selected using
CLAIMS_DATABASE_URL. Revision checks, unique evidence constraints, and atomic draft/session
transactions work across function instances. Database URLs are secret configuration and
are never included in API state or draft exports.

Policy manifest: ID/version, inclusive effective_from/effective_to, document paths, rules file.
Rules contain aligned metadata, currency, deadline, rounding, per-category rates and caps.
Exactly one version must apply to an expense date; missing/overlapping versions are rejected.
