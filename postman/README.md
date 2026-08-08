# Postman API Test Suite

A Postman collection covering the full backend REST API, generated from the actual
FastAPI route/schema source (not hand-written or guessed), plus fixes verified by
running it against a live local backend. See `../CLAUDE.md` for overall project
context.

## What's here

| File                       | Purpose                                                                                                                                                                                                                                                |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `postman_collection.json`  | 82 requests across 12 folders. Every request has auth wiring, `pm.test` assertions (status, timing, schema, chaining), and a description with confirmed request/response shapes and error codes.                                                       |
| `postman_environment.json` | Variables the collection needs: `baseUrl`, `accessToken`/`refreshToken` (auto-populated by Login), `email`/`password` (auto-generated once by Register's pre-request script), resource IDs (`projectId`, `chatId`, ...), and file-upload placeholders. |

### Folder coverage

Health · Authentication · Projects · Chats · Messages · Documents · Document
Processing · AI Providers · Workflow Templates · Workflow Runs · Executions ·
**Cleanup**.

`Cleanup` is a dedicated final folder holding every destructive `DELETE`
request, run last and in dependency order (leaf resources → parents). This is
deliberate: earlier folders keep `{{projectId}}`/`{{chatId}}`/etc. alive so
later folders can still use them — deleting mid-run breaks the whole chain.

## Running it

### Postman desktop app

Import both JSON files (**File → Import**), select the environment in the
top-right dropdown, and run the collection with the Collection Runner. If
you've imported an older copy before, re-import to replace it — the app
doesn't auto-pick-up changes to files on disk.

### CLI (newman)

```bash
npm install -g newman newman-reporter-htmlextra

newman run postman_collection.json \
  -e postman_environment.json \
  --env-var "uploadedFile=/path/to/a/valid/file.txt" \
  --env-var "invalidUploadFile=/path/to/a/disallowed/file.exe" \
  --reporters cli,htmlextra \
  --reporter-htmlextra-export ./newman-report.html
```

Requires the backend running locally (`uvicorn app.main:app --reload`) with
Postgres/Redis up (`docker compose up -d`) and migrations applied
(`alembic upgrade head`).

`uploadedFile` / `invalidUploadFile` have no defaults on purpose — Postman
can't embed binary file contents in a portable JSON collection, so these must
point at real local files. Allowed upload extensions: `.pdf .docx .txt .md
.markdown .csv .json` (see `ALLOWED_EXTENSIONS` in `app/core/constants.py`);
`invalidUploadFile` should use anything outside that list, or a file over
10MB, to exercise the 400/413 negative test.

Expected result: **81/82 passing**. The one flake
(`Workflow Templates / Run Workflow (Streaming)`) is newman's SSE client
occasionally aborting a long-lived `text/event-stream` connection — verified
independently via `curl -N` that the endpoint itself responds correctly. Not
a collection or backend bug.

`Google Login` also fails without a real Google OAuth credential in the
environment — expected, not something a local run can produce.

## Design notes worth knowing

- **Auth chaining**: `Register`'s pre-request script generates `{{email}}`/`{{password}}`
  once and persists them to the environment, so `Login` (and the duplicate-email
  negative test) reuse the same user instead of each request minting its own
  random identity that nothing else can log in as.
- **Collection-level Bearer auth**: `{{accessToken}}` is inherited by every
  request; public endpoints (health, register, login, refresh) explicitly
  override with `"auth": {"type": "noauth"}`.
- **Some 2xx/4xx pairs are both accepted on purpose**: `Resume Workflow Run`
  (202 or 409) and `Cancel Workflow Run` (200 or 409) depend on whether a
  background Celery worker has already moved the run out of a resumable/
  cancelable state by the time the request executes — that's real,
  timing-dependent backend behavior, not test flakiness to paper over.
- **`Run Agent` uses a query param, not a path param**: `POST
/agent_runs/?workflow_id={{workflowId}}` — the route has no
  `{workflow_id}` path segment, so FastAPI resolves it from the query
  string. Confirmed against the running server, not guessed.

## Publishing as hosted API docs (Postman's "Publish Docs")

Postman can generate a public, browsable reference page (request/response
examples, no login required to view) from this collection. This requires a
Postman account and can't be done from a terminal/CI — someone with edit
access needs to click through it once:

1. Import `postman_collection.json` into the Postman app (or open it if
   already imported/synced).
2. Open the collection → **⋯ (More actions)** → **Publish docs** (or
   **Share** → **Via Postman** in newer versions).
3. Postman generates a page at
   `https://documenter.getpostman.com/view/<your-id>/<collection-slug>`.
   Optionally point a custom domain/subdomain at it from Postman's publish
   settings if you want it under `ai-automation-platform.com` instead.
4. Re-publish after collection changes — it's a snapshot, not live-synced,
   unless you connect it to a Postman workspace with auto-sync (paid tiers).

If you'd rather avoid a third-party-hosted page entirely, this `README.md` +
the JSON files in this folder (browsable directly on GitHub) is a reasonable
substitute and stays fully under your own control.

**This project doesn't use Postman's Publish Docs** — the `postman.`
subdomain below serves a hand-built static page instead, and visitors can
download the collection/environment files directly from it.

## No CI — this is a static page, deliberately

There is no automated pipeline running this collection. `postman.` is a
plain static HTML page (`static/postman-report.html`) with numbers that were
true the last time someone manually ran the suite and updated the page — not
a live dashboard. To refresh it after a real change to the API or the
collection:

```bash
newman run postman_collection.json -e postman_environment.json \
  --env-var "uploadedFile=..." --env-var "invalidUploadFile=..." \
  --reporters cli,htmlextra --reporter-htmlextra-export ./raw.html

python3 redact_report.py raw.html ../static/postman-detail-report.html
```

Then update the stat cards / folder-coverage numbers in
`static/postman-report.html` by hand to match, and re-copy the collection
files developers can download from the page:

```bash
cp postman_collection.json postman_environment.json ../static/postman/
```

## Published pages

Three subdomains proxy to this same backend; `app/web/docs_landing.py`
branches on the `Host` header nginx forwards to decide what to render (see
`deploy/nginx/ai-platform-backend.conf`):

- `docs.ai-automation-platform.com` — the API documentation landing page.
- `api.ai-automation-platform.com` — a minimal page linking to the other two.
- `postman.ai-automation-platform.com` — `static/postman-report.html`, the
  coverage/pass-rate summary. Links to `static/postman-detail-report.html`
  (full per-request run detail, at `/postman-detail-report`) and offers the
  collection/environment JSON files as direct downloads
  (`static/postman/postman_collection.json`,
  `static/postman/postman_environment.json`).

**The detail report must never be published unredacted** — `htmlextra`
records every request/response in full, including live Bearer JWTs and the
generated test password. Always run it through `postman/redact_report.py`
first (see above) — never copy a raw `htmlextra` export straight into
`static/`.
