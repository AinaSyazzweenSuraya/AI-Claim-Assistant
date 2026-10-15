# Requirements and acceptance criteria

Scope: standalone, single-user allowance preparation in MYR. Fictional policy DEMO-ALLOWANCE
v1.0, effective 2026-01-01. No Spring Boot integration, external submission, payment, or approval.

Categories: mileage, meal, parking, lodging. Common fields: employee ID, category, expense date,
purpose, explicit business assertion. Mileage: route and positive kilometres. Receipt expenses:
positive amount, merchant/date/total/currency evidence, user-confirmed evidence. Lodging: nights.
Negative, malformed, excessive-precision amounts and non-integer nights are rejected.

Users may enter structured fields or conversational requests, review evidence, correct fields,
resume a session, start a new claim, and export a saved draft. Missing fields prompt a focused
list. Unsupported categories/currencies and out-of-policy expenses block readiness.

A successful draft uses the unique applicable rule version, valid recent evidence, an exact
Decimal calculation, citations, and explicit confirmation of the displayed revision. Session
and draft are committed atomically. Repeated confirmation does not create another draft.
Changing claim or evidence requires review again. Saved drafts are immutable in this version.

The default workflow must run without credentials or network model calls. Ollama provides
optional local AI with no per-request payment; real provider runs are evaluated separately.
Model or policy failures must be visible and must not save a draft.

Browser image OCR must work on Vercel with a text-only model: the browser reads one PNG/JPEG,
downloads OCR assets from this app, and sends only bounded OCR text to the API. No OCR API
fee, vision model, local computer server, or Python OCR runtime is required for that path.
Provider/hosting free-tier limits still apply. Show scan progress, preserve scanned text
for model retries, and block saving after a failed replacement until retried or canceled.
Require separate review/confirmation of proposed fields. Support English printed receipts;
state that OCR text hashes are not verified image hashes or authenticity evidence.
