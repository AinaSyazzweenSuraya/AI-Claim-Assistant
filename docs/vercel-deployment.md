# Deploy the standalone app on Vercel

The repository includes a native FastAPI entry point (`app.py`), a Vercel framework
configuration, and PostgreSQL storage. Local development still defaults to SQLite.
The policy index is rebuilt in `/tmp` on each cold start; claim sessions and drafts are
stored in PostgreSQL. Vercel's temporary filesystem cannot preserve a local SQLite database.
Existing local SQLite drafts are not automatically migrated to the hosted database.

## Required environment variables

In Vercel, open your project → Settings → Environment Variables. Set the following for
Production and, if you use preview deployments, Preview. Set them before the first deploy.

| Name | Value | Purpose |
| --- | --- | --- |
| `CLAIMS_APP_MODE` | `public` | Let visitors connect without entering a token |
| `CLAIMS_DATABASE_URL` | Your PostgreSQL connection URL | Persist sessions and drafts |
| `CLAIMS_LLM_MODE` | `demo` initially | Run the tested workflow without an AI provider key |

For the public website, **remove `CLAIMS_API_TOKEN`** and redeploy the latest code.
Keep your database URL and model-provider key private in Vercel; public access does not
remove those settings. Each browser receives an anonymous HttpOnly, Secure, SameSite=Strict
cookie. Session/chat/draft endpoints check its hashed owner value against PostgreSQL.
Other visitors cannot access a claim simply by knowing its UUID. Browser cookies must be
enabled. Clearing/expiring the 30-day cookie, using another browser/domain, or closing an
incognito session loses access; export a copy first. Shared browsers share a workspace.
Existing records without public ownership are inaccessible to public visitors.
This is anonymous testing access, not employee login or account recovery. Everyone uses
your provider/hosting quotas; production rate limiting and retention cleanup are not included.

For restricted access instead, use `CLAIMS_APP_MODE=private` and set `CLAIMS_API_TOKEN`.
Generate your access token locally, for example with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`, and paste it directly into
Vercel's secure environment-variable field. Do not commit it or send it in chat.
When the deployed browser asks for a service token, enter the same value. It stays in
browser memory, so you must enter it again after a reload.

For PostgreSQL, create a database through a service such as Neon (a free tier may be
available), or through Vercel Marketplace. Copy its PostgreSQL connection string into
`CLAIMS_DATABASE_URL`. Vercel integrations may provide `DATABASE_URL` automatically;
the assistant explicitly reads `CLAIMS_DATABASE_URL`, so configure that name too.
Use a pooled connection URL when your provider offers one for serverless functions.
The database user needs permission to create sessions, session_owners, and drafts tables; they are
created automatically at startup. Hosted connections verify TLS certificates and hostnames.

Database URLs contain credentials. Enter them only in environment settings. Do not put
them in `vercel.json`, GitHub, screenshots, or messages. Use a separate database for
preview deployments when those should not share production claims.

## Optional hosted AI variables

Demo mode has no AI key requirement and uses a limited parser, not an LLM. Vercel cannot
run an Ollama daemon or download/run a local model inside its functions.
To enable real AI, use an external HTTPS OpenAI-compatible model endpoint:

| Name | Value |
| --- | --- |
| `CLAIMS_LLM_MODE` | `openai` |
| `CLAIMS_LLM_BASE_URL` | Provider's HTTPS API base URL, including its `/v1` path if required |
| `CLAIMS_LLM_MODEL` | Model identifier supported by that provider |
| `CLAIMS_LLM_API_KEY` | Provider key entered securely in Vercel |

Choose a provider/model that supports tool calls. Free-tier hosted services may be an option,
subject to their limits; having a Vercel account does not supply a model key. For receipt
images, browser OCR works with a text model; direct server-image extraction requires a vision
model. Provider quality and credentials are not verified
by the local deployment tests. Model requests are capped at 10 seconds per round on Vercel,
and the app has at most four tool rounds. A slow or unavailable provider reports a failure.

For free OCR on Vercel, set **`CLAIMS_RECEIPT_IMAGE_BACKEND=browser`**. The user's browser
runs the included Tesseract.js worker and sends only scanned text to the API/text model.
No hosted vision model or local Ollama/Florence server is needed. For Groq, use
`CLAIMS_LLM_MODE=openai`, `CLAIMS_LLM_BASE_URL=https://api.groq.com/openai/v1`, an available
text model such as `openai/gpt-oss-20b`, and your securely configured Groq key. Free-tier
quotas apply; there is no OCR API fee. See [browser OCR setup](browser-ocr.md).

`vision` remains an option for an available hosted vision model. The optional Florence-2
backend runs locally with a text LLM; its PyTorch runtime and weights are not hosted by this
function. Setting `florence` on Vercel fails startup with configuration guidance. See the
[local Florence guide](florence-receipts.md) for the free computer-based image-scanning flow.

## Import and deploy

1. In Vercel, choose Add New → Project and import `AinaSyazzweenSuraya/AI-Claim-Assistant`.
2. Use branch `main` and the repository root as Root Directory.
3. Select **FastAPI** if it is not detected. Keep the default install/build settings; Vercel
   reads `pyproject.toml` and `uv.lock`. Do not choose a static HTML framework.
   OCR assets are committed and included in `vercel.json`; no npm/Node build or optional
   Florence installation is needed for browser mode.
4. Add the required variables above. No Vercel deployment token is needed when deploying
   through your own dashboard.
5. Keep Vercel's system environment variables exposed: the app uses `VERCEL_URL`,
   `VERCEL_PROJECT_PRODUCTION_URL`, and `VERCEL_BRANCH_URL` to allow its deployment hosts.
6. Click Deploy. After changing environment variables, redeploy to apply them.
7. Open the deployment and run the checks below. Public mode connects automatically;
   private mode asks for your service token.

For a custom domain, also set `CLAIMS_ALLOWED_HOSTS` to a JSON array containing it,
for example `["claims.example.com"]`. Vercel deployment domains are appended automatically.
Use the HTTPS deployment URL. Cross-origin calls are disabled; the browser and API must
be served by the same app. Public mode separates anonymous browser workspaces. Private
mode uses one shared token with access to all records; neither mode provides employee SSO.

## Check the deployment

Follow [the user testing guide](user-testing.md), using current dates:

1. Prepare a 25 km business mileage claim with employee ID, route, purpose, and current date.
   Expect RM15.00 and a DEMO-ALLOWANCE v1.0 Mileage citation.
2. Confirm the draft. Export JSON and check `submitted=false`.
3. Refresh and confirm the same saved session is loaded. Only private mode asks for the
   token again. In public mode, open another browser/incognito window: it should start
   empty and receive HTTP 404 if it requests the first browser's session or draft UUID.
4. Prepare a RM45.00 meal with matching receipt evidence. Review evidence before confirming.
   Expect RM30.00. Missing evidence must prevent saving.
5. With real AI configured, additionally try a natural-language request and verify that
   the model proposes the correct fields. A successful health check alone does not test AI.
6. With `browser` OCR configured, upload a clear matching receipt image. Expect browser
   progress, scanned text in the textarea, and proposed fields for separate confirmation.
   The browser's `/api/chat` request must contain `receipt_ocr_text`, not `receipt_image`.
   Check a blank/corrupt image and provider failure as described in [the OCR guide](browser-ocr.md).

The included rules are fictional. The app creates drafts only; it does not approve or pay claims.

## Troubleshooting

- Startup says app mode is required: deploy current code and set `CLAIMS_APP_MODE=public`
  for open access, or `private` plus `CLAIMS_API_TOKEN` for restricted access.
- Public mode still shows Connect: redeploy after changing variables and reload the page.
  `CLAIMS_APP_MODE=demo` is loopback-only; `CLAIMS_LLM_MODE=demo` is a separate parser setting.
- Public session returns 404: use the original browser/domain with its visitor cookie.
  Old private records and records from a cleared/expired cookie are not publicly recoverable.
- Startup says persistent storage is required: set `CLAIMS_DATABASE_URL`, not only `DATABASE_URL`.
- Database connection failure: check URL, provider availability, connection limits, network
  permissions, TLS trust, and table-creation permissions. Do not turn TLS verification off.
- HTTP 400 Invalid host: check exposed Vercel system variables or `CLAIMS_ALLOWED_HOSTS`.
- HTTP 401 on /api/health or /api/chat in private mode: the assistant access token is missing or was not
  accepted. Open the exact Vercel project serving your website and copy the Production
  CLAIMS_API_TOKEN value into the website's token field, then click Connect. Enter only the
  token text. If the environment value changed, redeploy before connecting. A refreshed
  browser needs to connect again because the token is retained only in memory.
  The app disables claim actions until connection succeeds and shows rejected requests
  beside the chat. CLAIMS_LLM_API_KEY authenticates model requests, not website access.
- Cross-origin requests disabled on your own HTTPS deployment: update to the latest code.
  The Vercel adapter compares the public HTTPS origin even when the internal proxy forwards
  HTTP. Other hosts and origins remain blocked; forwarded headers alone cannot bypass this.
- Model unavailable: check provider endpoint, model ID, key, and tool-call support.
  After redeploying, retry extraction and use the specific error: HTTP 401 indicates a
  rejected model key; HTTP 403 denied access; HTTP 404 a missing endpoint/model; HTTP 400/422
  an unsupported request; HTTP 413 an oversized request; HTTP 429 a rate limit or quota;
  HTTP 5xx a provider failure. Known model-retirement and JSON/tool-generation errors are
  identified separately. A timeout message reports the configured timeout (capped at
  10 seconds on Vercel). Provider response bodies, keys, and receipt data are never included
  in these messages. The authenticated `/api/health` response includes `llm_model`,
  `llm_mode`, `receipt_image_backend`, and `llm_timeout_seconds` so you can verify the active
  deployment's configuration. Health does not test provider access or extraction quality.
- Browser OCR does not start: inspect `/assets/ocr/browser-ocr.js` and the versioned worker,
  core, and `eng.traineddata.gz` requests in browser DevTools. They must return HTTP 200
  from this deployment. Redeploy the latest code if assets are missing and use a browser
  with workers/WebAssembly enabled. No API key belongs in browser OCR files.
- Scanned text appears but extraction fails: OCR succeeded. Use the displayed model error
  to diagnose access/quota/format/timeout, then click **Extract text** to retry. Keep a
  text-only model on the `browser` path rather than switching it to direct vision.

## Local verification of the deployment adapter

The real browser OCR check starts this Vercel adapter over HTTPS with a disposable PostgreSQL
schema and a local text-provider protocol stub. See [verification commands](browser-ocr.md#verification).
It checks native PNG/JPEG scanning, self-hosted assets, text-only API payloads, rate-limit
recovery, separate confirmations, the RM30 meal cap, and PostgreSQL restoration. It does not
deploy to Vercel or verify the user's live Groq key.

The ordinary tests cover SQLite and cloud configuration. PostgreSQL integration tests run
only when `CLAIMS_TEST_DATABASE_URL` is set; they use isolated temporary schemas.
For a disposable local test database (requires Docker):

```bash
docker run --detach --rm --name claims-postgres-test --publish 127.0.0.1:55432:5432 \
  --env POSTGRES_HOST_AUTH_METHOD=trust --env POSTGRES_DB=claims postgres:17-alpine
docker exec claims-postgres-test pg_isready -U postgres -d claims
CLAIMS_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/claims uv run pytest -q
docker stop claims-postgres-test
```

That database has no password because it is an isolated loopback-only development fixture.
Do not use that authentication mode for a hosted database. The checks verify saved drafts
across app instances, revision conflicts, atomic duplicate-receipt rollback, and rebuilding
the temporary policy index without losing the stored session. They do not verify a live
Vercel deployment or your provider's actual database until you deploy and run the checks.
