# Limitations

- Fictional single-version sample policy, MYR only; no production policy approval.
- Single-user app. Shared service tokens do not isolate employee data. No SSO, role authorization,
  encrypted database, organizational audit/retention automation, or production rate limiting.
- Saves local drafts only. No Spring Boot connection, claim submission, approval, or payment.
- Demo parser is limited and is not an LLM. Ollama must be installed/running and its model downloaded.
- Default local model is text-only. Image extraction requires a compatible vision model; no bundled
  OCR engine, PDF processing, receipt authenticity checks, or accounting line-item/tax parsing.
- Policy retrieval is lexical hashing, so paraphrases may retrieve poorly. Rates always come from JSON.
- One expense/receipt per draft; no multi-currency, advances, per diem, travel segments, or partial dates.
- Duplicate checks cover saved local drafts only. Different legitimate receipts with identical visible
  merchant/date/total/number can be flagged; a human must resolve such cases.
- Business-purpose truth is a user assertion. A model cannot determine whether a trip really qualifies.
- Personal data persists in SQLite history and drafts until you delete it; raw uploads are not retained.
- Installed wheels need CLAIMS_ROOT pointing to a checkout containing prompts and data.
