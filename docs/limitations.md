# Limitations

- Fictional single-version sample policy, MYR only; no production policy approval.
- Public mode isolates anonymous browser workspaces using a 30-day visitor cookie, not
  employee identities. Clearing/expiring cookies or changing browser/domain loses access;
  shared devices share a workspace. Private shared-token access does not isolate employees.
  No SSO, role authorization, application-level database encryption, organizational
  audit/retention automation, account recovery, or production rate limiting. Public users
  share model/hosting quotas; use fictional data for testing.
- Saves local drafts only. No Spring Boot connection, claim submission, approval, or payment.
- Demo parser is limited and is not an LLM. Ollama must be installed/running and its model downloaded.
  Use plain decimal numbers without thousands separators in demo chat; use the structured
  form for requests the parser cannot interpret. Invalid numbers must be corrected before review.
- Default local model is text-only. Images can use browser Tesseract OCR plus a text LLM,
  a compatible vision model, or optional local Florence OCR. Florence packages/weights are downloaded separately;
  no PDF processing, receipt authenticity checks, or accounting line-item/tax parsing.
- Native Florence runs locally and is not hosted by this Vercel function. Its real OCR accuracy
  requires testing on staff images. A transaction screenshot does not establish eligibility.
- Browser OCR ships English data for clear printed PNG/JPEG receipts only; handwriting,
  other scripts, complex layouts, blur, and glare may fail. It needs a modern browser and
  initial asset downloads; it uses the visitor's CPU/RAM. The two-minute scan deadline is
  separate from the Vercel model timeout. OCR text goes to the app/text provider; original
  images stay in the browser. Text hashes and canonical fingerprints are duplicate
  heuristics, not verified image provenance. Browser mode requires no OCR API fee, but
  Vercel, database, and text-provider free-tier limits still apply.
- Policy retrieval is lexical hashing, so paraphrases may retrieve poorly. Rates always come from JSON.
- One expense/receipt per draft; no multi-currency, advances, per diem, travel segments, or partial dates.
- Duplicate checks cover saved local drafts only. Different legitimate receipts with identical visible
  merchant/date/total/number can be flagged; a human must resolve such cases.
- Business-purpose truth is a user assertion. A model cannot determine whether a trip really qualifies.
- Data persists in SQLite/PostgreSQL history and drafts until you delete it; expiring a
  visitor cookie does not delete records. Raw uploads are not retained.
- Installed wheels need CLAIMS_ROOT pointing to a checkout containing prompts and data.
- Vercel requires external PostgreSQL storage and public or private app mode. It cannot
  run local Ollama. A live cloud database/deployment must be checked after configuration.
