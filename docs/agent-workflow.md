# Workflow and states

1. Collect supplied fields; never invent a missing value. Explicit `business` or a checked
   form box supplies the business assertion. Personal expenses are rejected.
2. Propose receipt fields from text, browser OCR text, a supported vision model, or local Florence OCR followed
   by a text model. Show the extracted merchant/payee, date, total, currency, and reference.
   Corrections/replacements clear evidence confirmation. Confirmation is a separate action.
3. Validate category, required fields, date, deadline, currency, and evidence matches.
4. Retrieve applicable policy sections and calculate deterministically.
5. Show amount, formula, cap, claim details, missing fields, and citations.
6. Save only on `confirm`/confirm=true with the reviewed revision and no simultaneous edits.

States: `collecting` (missing fields), `invalid` (policy rejection or failed prerequisites),
`ready` (validated and calculated, awaiting review), `saved` (immutable local draft).
Errors never silently save partial changes. `new` clears the claim while retaining the session.
Updating an already saved claim requires `new`. A stale revision rejects the turn without mutation.
Current-day validation is repeated at save time; an expired draft cannot be saved later.

In browser OCR mode, scanning and progress occur on the client before the API turn. Failure
does not replace or confirm server evidence; the pending replacement blocks browser saving.
Successful scans send `receipt_ocr_text` for untrusted text-model extraction. A provider
failure retains scanned text for retry without another scan. Evidence and final draft
confirmations remain separate. No original image is uploaded in this mode.
