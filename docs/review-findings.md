# Repository and interface review

Reviewed on 13 October 2026. Scope: all 79 files tracked at the start of the review,
including documentation, prompts, fictional policy/sample data, dependencies, deployment
configuration, application code, tests, and evaluation cases. Generated runtime data and
private `.env` files were excluded. Python syntax, JSON/JSONL/TOML validity, UTF-8 decoding,
and explicit text-file encodings were checked across the repository.

## Findings and repairs

| Area | Finding | Repair and verification |
| --- | --- | --- |
| Entire browser page | Typographic apostrophes and middle dots could appear as garbled characters when decoded with a Windows legacy encoding. | Keep explicit UTF-8 reads and HTTP charset; use HTML entities for static typography throughout the header, steps, placeholders, chat introduction, and footer. Check actual browser text and simulated Windows decoding. |
| Browser draft review | Pasting new receipt text did not block saving; confirming evidence could overwrite unapplied expense edits. | Track pending expense edits, receipt corrections, and new receipt text separately. Preserve edits across unrelated actions and block button/chat confirmation until changes are applied and reviewed. |
| Browser startup | A delayed restored session could overwrite input entered during connection. | Disable editing while connection/session restoration is in progress. |
| Windows date handling | Windows may lack system IANA timezone files needed by `Asia/Kuala_Lumpur`. | Add the `tzdata` dependency; test a real assistant turn in a subprocess with system timezone lookup disabled. |
| Demo input parsing | Negative distance could become positive; `2.5 nights` could become five nights; unsupported comma-separated numbers could be partially interpreted. | Preserve signed/fractional values for schema rejection and avoid partial-number matches. Test rejected input without calculations or saved drafts. |
| Receipt extraction | Conflicting or malformed explicit currency labels could fall back to MYR. | Infer MYR from an RM total only when no explicit currency label exists. Ambiguous currency stays missing. |
| Saved session recovery | Starting a new claim with invalid fields could restore the old saved claim with a collecting status. | Preserve the original saved status, calculation, and draft snapshot on failure. |
| Policy search tool | Non-text model queries could crash retrieval instead of returning a tool error. | Validate query type, nonempty text, and the documented 1,000-character limit before retrieval. |
| Configuration and tests | Some text-file operations relied on platform default encoding. | Declare UTF-8 for dotenv loading and remaining test fixtures. |

Schemas, Decimal calculations, policy/rule alignment, retrieval citations, draft confirmation,
SQLite/PostgreSQL persistence, revision conflicts, duplicate-receipt rollback, provider protocol
handling, and Vercel startup configuration were reviewed and exercised by the checks below.

## Verification

- 79 automated tests passed, including four integration tests against disposable PostgreSQL 17.
  Without `CLAIMS_TEST_DATABASE_URL`, 75 tests pass and four PostgreSQL tests are skipped.
- All 17 fixed-date claim workflow evaluations passed.
- Chromium checks passed for header/notice/step text, readable missing-field labels,
  mileage calculation/edit/save/export, Unicode user data, session restoration/reset,
  receipt review and meal cap, pending edits, and mobile overflow. No JavaScript errors.
- Frozen dependency installation, Ruff lint/format checks, policy ingestion, package build,
  and a CLI prepare/confirm/export smoke check passed.

To repeat the browser check with an installed Chromium browser:

```bash
uv run --with playwright playwright install chromium
uv run --with playwright python scripts/check_web_ui.py
```

The script starts its own loopback server on an unused port and uses temporary draft storage.
Screenshots and a fictional exported draft go under `evaluations/results/browser/`, which is
Git-ignored. `CLAIMS_BROWSER_EXECUTABLE` optionally selects an existing Chromium executable.

Live Ollama/vision quality and the user's actual Vercel deployment/hosted database remain
unverified. See [limitations](limitations.md) and [deployment checks](vercel-deployment.md).

## Apply the update in PyCharm on Windows

Stop the running app with **Ctrl+C**. From the `AI-Claim-Assistant` project directory:

```powershell
git pull
uv sync --frozen --extra dev
uv run claims ingest
uv run claims web
```

Open the address printed by the new server and refresh with **Ctrl+F5**. Updating files alone
does not reload an already running Python process. If using Vercel, wait for a successful new
deployment or redeploy the latest `main` commit, then refresh that deployment URL.
