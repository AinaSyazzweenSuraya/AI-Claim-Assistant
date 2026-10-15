# Try the assistant as a user

Public website access was checked on 15 October 2026 (Asia/Kuala_Lumpur): 146 tests,
17 workflow cases, and real browser OCR/save/export checks passed with PostgreSQL and the
HTTPS Vercel adapter. Public mode opens without Connect; each browser has a separate
workspace. Refresh should restore your claim. A second browser/incognito window should
start empty and cannot read/update/export the first browser's records, even with its UUIDs.
Export drafts before clearing site data; this is anonymous access, not an employee account.
Your actual deployed site and live Groq key still need checking after redeployment.

The standalone demo workflow was rechecked on 13 October 2026 (Asia/Kuala_Lumpur):
79 automated tests including PostgreSQL, 17 evaluation cases, and desktop/mobile browser
checks passed. The earlier 18 live HTTP user-flow checks also passed with temporary storage.
See [the repository review](review-findings.md) for the latest checks and Windows update steps.

These checks demonstrate the demo parser, claim tools, validation, calculations, receipt
review, confirmation, API, and SQLite persistence. They do not demonstrate live Ollama or
vision-model quality. Ollama is not installed in this environment.
All rates and receipts below are fictional. Saved drafts are local, not approved or submitted.

## Start a clean practice session

Run these commands from the repository in a Bash terminal:

```bash
uv sync --frozen --extra dev
export CLAIMS_LLM_MODE=demo
export CLAIMS_RUNTIME_DIR="$(mktemp -d -t claims-practice-XXXXXX)"
uv run claims ingest
uv run claims chat
```

The temporary directory keeps practice drafts separate from `runtime/claims.db`. Keep its
path if you want to resume them; operating-system cleanup may delete temporary files later.
For the browser interface instead, run `uv run claims web` in the same configured terminal.
Use the browser form and action buttons corresponding to the CLI steps below.

Keep the web-server terminal running and open its printed address on the same computer.
Click **Choose .txt or image** to open the native file picker. The text-extraction button
requires pasted text. A message below the upload button explains when an active request,
connection failure, or saved draft disables uploads. Use **Retry connection** after resolving
connection errors, or **New claim** to add evidence after saving a draft. Uploading a file
does not prove model extraction worked; review the proposed fields before confirming evidence.

For receipt photos on Vercel with a text-only Groq model, select
`CLAIMS_RECEIPT_IMAGE_BACKEND=browser` and follow [the browser OCR walkthrough](browser-ocr.md).
It reads the image on your device and sends only scanned text for field extraction.
Florence remains a separate local option. Model/provider failures and incorrect OCR must
never be treated as confirmed evidence or a successful draft.

These examples use 2026-10-13. If testing later, replace every claim and receipt date with
the same recent date. Dates more than 30 days old are intentionally rejected.
Enter `new` between scenarios to clear the current claim.

## 1. Prepare and save business mileage

Imagine you travelled from Kuala Lumpur to Petaling Jaya for a client meeting.
Enter each line separately and review the response before continuing:

```text
I drove 25 km from KL to PJ on 2026-10-13 for a client meeting
employee_id=EMP001
business
```

Expected:

- The first response asks for employee_id and business_expense.
- Supplying the employee ID leaves the business assertion missing.
- `business` produces a ready draft for RM15.00: 25 km × RM0.60.
- The response cites DEMO-ALLOWANCE v1.0, Mileage, and the policy file.
- No draft ID exists yet. `/show` displays the current state with draft_id=null.

Then enter:

```text
confirm
/show
```

Expected: status=saved, a draft UUID, and RM15.00. It has not been approved or submitted.
In the browser, use Confirm & save draft, then Export JSON. Export should contain
`submitted: false`, the claim details, calculation, and policy citations.

## 2. Meal receipt and maximum allowance

```text
new
employee_id=EMP001 category=meal expense_date=2026-10-13 purpose="Client lunch" business_expense=true amount=45
/receipt data/samples/receipts/user-test-meal.txt
```

Expected: the initial claim asks for a receipt. Extraction proposes the merchant, date,
RM45.00 total, and MYR, but the claim still requires receipt confirmation.

Check those fields against the fictional receipt, then enter:

```text
/evidence-confirm
confirm
```

Expected: evidence confirmation produces a ready RM30.00 draft because the meal cap is
RM30.00. The separate `confirm` saves that draft. Before evidence confirmation, no amount
should be shown as ready for saving.

In the browser, select Meal, complete the form, and paste:

```text
Merchant: Fictional UAT Cafe
Date: 2026-10-13
Total: RM45.00
Currency: MYR
Receipt: USER-TEST-MEAL-001
```

Use Extract text, review fields, Confirm evidence, then Confirm & save draft.

## 3. Required information is missing

```text
new
employee_id=EMP001 category=mileage expense_date=2026-10-13 purpose="Client meeting" business_expense=true distance_km=25
confirm
```

Expected: the assistant requests route and does not calculate or save the incomplete claim.
Enter `route="KL to PJ"` to receive a ready RM15.00 draft; review it before confirming.

## 4. Receipt and claim amounts disagree

```text
new
employee_id=EMP001 category=meal expense_date=2026-10-13 purpose="Client lunch" business_expense=true amount=20
/receipt data/samples/receipts/user-test-meal.txt
/evidence-confirm
confirm
```

Expected: receipt total RM45.00 does not match the RM20 claim amount. The assistant reports
the mismatch, has no valid calculation, and saves nothing. In the browser, the save button
stays disabled. Correct the claim to the actual receipt total before requesting a new review.

## 5. Personal travel is ineligible

```text
new
employee_id=EMP001 category=mileage expense_date=2026-10-13 purpose="Personal shopping" business_expense=false distance_km=25 route="Home to mall"
confirm
```

Expected: personal expenses and normal commuting are ineligible. No amount or saved draft.

## 6. Limits and deadlines

| Action | Expected result |
| --- | --- |
| Prepare a complete business mileage claim for 1,000 km | RM300.00, applying the mileage cap |
| Use an expense date 31 days before today's date | Rejected as outside the deadline |
| Use tomorrow's date | Rejected as a future expense |
| Use category=entertainment | Unsupported category; no calculation/save |
| Use currency=USD | Only MYR is supported; no calculation/save |

Start a new claim for each check so fields from another category do not carry over.

## 7. Edits require another review

Prepare a ready 25 km mileage claim, then enter `distance_km=50`.
Expected: a new RM30.00 calculation, status=ready, and no saved draft until you confirm again.
In the browser, changing a form field disables saving until Check my claim applies the edit.
The API also blocks saving an edited claim and confirming it in the same turn; it requests
another review. A confirmation with an old expected_revision returns HTTP 409.

## 8. Duplicate evidence is blocked

After saving scenario 2, start a new meal claim with the same date and RM45.00 amount.
Extract the exact same receipt, confirm the evidence, and attempt to save.
Expected: "Receipt is already used in a saved local draft" and no new draft ID.
This check covers this assistant's saved drafts only.

## 9. Resume stored work

Copy the session UUID shown by the CLI, enter `/quit`, then run in the same terminal:

```bash
uv run claims chat --session YOUR_SESSION_UUID
```

Enter `/show`. Expected: the same claim, saved draft ID (if saved), and workflow status.
The live verification also stopped and restarted the server before loading a saved session;
SQLite preserved the same session and draft ID.

## What counts as success

A correct amount alone is insufficient. Check that missing or invalid information blocks
saving, the correct policy is cited, evidence is reviewed separately, saving requires your
confirmation, and the saved data matches what you reviewed. A saved draft is not approval.
After configuring a real local model, repeat these scenarios and additionally check that
paraphrased requests extract exactly the fields you supplied without inventing values.
