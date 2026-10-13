# Allowance Assistant

A standalone Python claim-preparation assistant, inspired by an existing eClaim workflow.
It helps collect expense details, retrieve policy sections, check eligibility, calculate
MYR allowances, review receipt evidence, and save a local draft. It includes a CLI,
FastAPI API, and a browser interface. It does not connect to Spring Boot or submit claims.

**All included policies, employees, and receipts are fictional.** Replace and approve the
policy before real use. The assistant does not approve claims or verify receipt authenticity.

## Free model options

The default **demo** mode runs offline with a small deterministic parser. It exercises all
claim tools and storage, but is not an LLM. The structured expense form works without a model.

For real natural-language AI without per-request charges, use **Ollama** with a local model:

1. Install Ollama from its official site and start `ollama serve` if it is not already running.
2. Run `ollama pull llama3.2:3b` (approximately 2 GB; CPU inference is supported but slower).
3. Set these variables in your shell or `.env`, then restart this app:

```dotenv
CLAIMS_LLM_MODE=ollama
CLAIMS_LLM_BASE_URL=http://127.0.0.1:11434/v1
CLAIMS_LLM_MODEL=llama3.2:3b
```

No API key is needed for local Ollama. You supply the computer, RAM, electricity, and model
download; check the model license for your intended use. Text-only llama3.2:3b cannot read
receipt images. Use pasted receipt text, or select a compatible vision model separately
(e.g. a locally installed Ollama vision model supporting the OpenAI-compatible image format).
Image extraction is optional and must be evaluated on your receipts before use.

An optional HTTPS OpenAI-compatible endpoint is also supported with `CLAIMS_LLM_MODE=openai`,
`CLAIMS_LLM_BASE_URL`, `CLAIMS_LLM_MODEL`, and `CLAIMS_LLM_API_KEY`. Hosted providers may charge.
Model failures are reported; the app never silently switches from AI to demo mode.

## Install and run

Use Python 3.12+ and [uv](https://docs.astral.sh/uv/). From this repository:

```bash
uv sync --frozen --extra dev
uv run claims ingest
uv run claims chat
```

Optional configuration: copy `.env.example` to `.env`. The defaults need no credentials.
For the browser app and JSON API:

```bash
uv run claims web
```

To host the app on Vercel, follow [the Vercel deployment guide](docs/vercel-deployment.md).
Vercel uses PostgreSQL via `CLAIMS_DATABASE_URL`; local development defaults to SQLite.
The guide lists required variables and explains how to enable an external AI provider.

The CLI prints the bind address. The default server binds to loopback on port 8000.
API documentation is served at `/docs`. `/api/health` checks the local policy index; it does
not assert that an optional model is available. Live model readiness requires a successful
conversation. Never expose demo mode on a public network.

## Example mileage conversation

```text
employee_id=EMP001 category=mileage expense_date=2026-10-13 purpose="Client meeting" business_expense=true distance_km=25 route="KL to PJ"
confirm
```

Use a real recent expense date when trying this later. The fictional policy pays RM15.00
for 25 km (25 × RM0.60). The assistant shows the calculation and policy citation first.
An explicit `confirm` saves the reviewed draft to SQLite. `new` clears the current claim;
`/quit` exits, `/show` shows current data, and `claims chat --session UUID` resumes a session.

Demo mode accepts JSON and `key=value` fields with quoted multiword values. It also recognizes
simple requests such as `I drove 25 km from KL to PJ today for a client meeting`, then asks for
the missing employee and business assertion. Send `employee_id=EMP001` and `business`.
In Ollama mode the model calls tools to propose fields and search policy; validation,
calculations, evidence confirmation, and saving remain controlled by Python.

## Receipt example

```text
employee_id=EMP001 category=meal expense_date=2026-10-13 purpose="Client lunch" business_expense=true amount=25
/receipt data/samples/receipts/meal.txt
/evidence-confirm
confirm
```

Review extracted merchant, date, total, and currency before confirming evidence. Demo extraction
supports labeled text only (`Merchant:`, `Date: YYYY-MM-DD`, `Total: RM25.00`, optional
`Currency: MYR` and `Receipt: ID`). Unknown or ambiguous values remain missing.
The browser offers receipt corrections and JSON draft export. Images are not written to disk.

## API example

Send `POST /api/chat` with a message or explicit fields. The response contains `state`,
`message`, and tool results:

```json
{
  "fields": {
    "employee_id": "EMP001", "category": "mileage", "expense_date": "2026-10-13",
    "purpose": "Client meeting", "business_expense": true,
    "distance_km": "25", "route": "KL to PJ"
  }
}
```

To save, send `{ "session_id": "<returned UUID>", "expected_revision": 1, "confirm": true }`.
Use the actual returned revision. Each further turn includes the session ID and revision.
A stale revision gets HTTP 409. Edits with a confirmation action trigger a new review.
`GET /api/drafts/{id}` returns a saved draft. Session and draft UUIDs are identifiers, not
per-user access control. See [tool contracts](docs/tool-contracts.md).

## Policies and data

Policies live in `data/policies`, structured rates in `data/rules`. Manifest and rule metadata
must agree. The expense date chooses the rule version. The example covers mileage (RM0.60/km,
RM300 cap), meals (RM30 cap), parking (RM50 cap), and lodging (RM180/night cap).
The submission deadline is 30 days inclusive. Dates use Asia/Kuala_Lumpur for the current day.
Python `Decimal` and `ROUND_HALF_UP` determine amounts; retrieval never determines rates.

Run `uv run claims ingest` after policy changes. The retrieval index is offline lexical
feature hashing with cosine similarity, with version filtering and source citations. It is
not a learned semantic embedding index. Stale indexes fail visibly instead of serving old policy.
`runtime/` contains SQLite sessions/drafts and the generated policy index; it is Git-ignored.
Conversation history and extracted fields are personal data. Protect, back up, and delete
runtime data according to your retention policy. No raw uploads are retained automatically.

## Verification

For a hands-on walkthrough with example inputs and expected results, follow
[the user testing guide](docs/user-testing.md).
See the [repository review](docs/review-findings.md) for the complete interface checks,
Windows fixes, and update/restart instructions.

```bash
uv run pytest
uv run ruff check .
uv run python scripts/ingest_policies.py
uv run python scripts/run_evaluations.py
uv build
```

Evaluations use a fixed date and a temporary database, never your real drafts. Results are
written under `evaluations/results`. Tests cover calculations, deadlines, evidence,
confirmation, persistence, concurrency, duplicate receipts, tool errors, retrieval, and API
access. Provider protocol tests use mocks and are distinct from a live local-model test.
The built package expects the policy and prompt files in this checkout; set `CLAIMS_ROOT`
to this repository if running an installed wheel elsewhere.

## Private deployment

This is a single-user development application. For access beyond loopback, set
`CLAIMS_APP_MODE=private`, a strong `CLAIMS_API_TOKEN`, and `CLAIMS_ALLOWED_HOSTS` (JSON array
of hostnames), then use a TLS reverse proxy. The API requires `Authorization: Bearer TOKEN`.
The browser accepts the token in memory; it does not persist it. The app disables cross-origin
requests. A shared token does not provide employee authorization or isolation. Multi-user use
requires identity integration, ownership checks, retention controls, and production hardening.

See [requirements](docs/requirements.md), [architecture](docs/architecture.md),
[workflow](docs/agent-workflow.md), [evaluation plan](docs/evaluation-plan.md), and
[limitations](docs/limitations.md).
