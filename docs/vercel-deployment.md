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
| `CLAIMS_APP_MODE` | `private` | Require authentication for API requests |
| `CLAIMS_API_TOKEN` | A strong secret you generate | Protect your single-user app |
| `CLAIMS_DATABASE_URL` | Your PostgreSQL connection URL | Persist sessions and drafts |
| `CLAIMS_LLM_MODE` | `demo` initially | Run the tested workflow without an AI provider key |

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
The database user needs permission to create the sessions and drafts tables; they are
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
subject to their limits; having a Vercel account does not supply a model key. Image extraction
also requires a compatible vision model. Provider quality and credentials are not verified
by the local deployment tests. Model requests are capped at 10 seconds per round on Vercel,
and the app has at most four tool rounds. A slow or unavailable provider reports a failure.

## Import and deploy

1. In Vercel, choose Add New → Project and import `AinaSyazzweenSuraya/AI-Claim-Assistant`.
2. Use branch `main` and the repository root as Root Directory.
3. Select **FastAPI** if it is not detected. Keep the default install/build settings; Vercel
   reads `pyproject.toml` and `uv.lock`. Do not choose a static HTML framework.
4. Add the required variables above. No Vercel deployment token is needed when deploying
   through your own dashboard.
5. Keep Vercel's system environment variables exposed: the app uses `VERCEL_URL`,
   `VERCEL_PROJECT_PRODUCTION_URL`, and `VERCEL_BRANCH_URL` to allow its deployment hosts.
6. Click Deploy. After changing environment variables, redeploy to apply them.
7. Open the deployment, enter your service token, and run the checks below.

For a custom domain, also set `CLAIMS_ALLOWED_HOSTS` to a JSON array containing it,
for example `["claims.example.com"]`. Vercel deployment domains are appended automatically.
Use the HTTPS deployment URL. Cross-origin calls are disabled; the browser and API must
be served by the same app. This remains a single-user application with one shared token,
not employee SSO or per-user record ownership.

## Check the deployment

Follow [the user testing guide](user-testing.md), using current dates:

1. Prepare a 25 km business mileage claim with employee ID, route, purpose, and current date.
   Expect RM15.00 and a DEMO-ALLOWANCE v1.0 Mileage citation.
2. Confirm the draft. Export JSON and check `submitted=false`.
3. Refresh, enter the token again, and confirm the same saved session is loaded.
4. Prepare a RM45.00 meal with matching receipt evidence. Review evidence before confirming.
   Expect RM30.00. Missing evidence must prevent saving.
5. With real AI configured, additionally try a natural-language request and verify that
   the model proposes the correct fields. A successful health check alone does not test AI.

The included rules are fictional. The app creates drafts only; it does not approve or pay claims.

## Troubleshooting

- Startup says private mode/token is required: check `CLAIMS_APP_MODE` and `CLAIMS_API_TOKEN`.
- Startup says persistent storage is required: set `CLAIMS_DATABASE_URL`, not only `DATABASE_URL`.
- Database connection failure: check URL, provider availability, connection limits, network
  permissions, TLS trust, and table-creation permissions. Do not turn TLS verification off.
- HTTP 400 Invalid host: check exposed Vercel system variables or `CLAIMS_ALLOWED_HOSTS`.
- HTTP 401: enter the configured service token; model keys are different from this token.
- Model unavailable: check provider endpoint, model ID, key, and tool-call support.

## Local verification of the deployment adapter

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
