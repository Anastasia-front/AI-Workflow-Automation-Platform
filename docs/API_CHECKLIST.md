# API Checklist

Use this checklist after significant changes to routes, dependencies, models,
migrations, auth, document processing, AI calls, or workflow execution.

Assumed local setup:

```bash
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```

Base URL:

```text
http://127.0.0.1:8000
```

## Setup

- ✔️ Confirm Postgres is running.
- ✔️ Confirm `.env` contains `DATABASE_URL`, JWT settings, and AI provider
  settings.
- ✔️ Apply migrations with `alembic upgrade head`.
- ✔️ Start the API server.
- ✔️ Open `/docs` and confirm OpenAPI loads.

## Authentication

- ✔️ Register a new user with `POST /auth/register`.
- ✔️ Confirm duplicate registration fails or is handled predictably.
- ✔️ Log in with valid credentials using `POST /auth/login`.
- ✔️ Save the returned bearer token.
- ✔️ Call `GET /auth/me` with the token and confirm the expected user is
  returned.
- ✔️ Call a protected endpoint without a token and confirm it is rejected.
- ✔️ Call a protected endpoint with an invalid token and confirm it is rejected.

Example:

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"123456"}'
```

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@test.com&password=123456"
```

## Projects

- ✔️ Create a project with `POST /projects/`.
- ✔️ List projects with `GET /projects/`.
- ✔️ Fetch the created project with `GET /projects/{project_id}`.
- ✔️ Confirm another user cannot fetch the project.
- ✔️ Delete a test project with `DELETE /projects/{project_id}`.
- ✔️ Confirm deleted project no longer appears in list responses.

## Chats and Messages

- ✔️ Create a chat with `POST /projects/{project_id}/chats`.
- ✔️ List project chats with `GET /projects/{project_id}/chats`.
- ✔️ Fetch a chat with `GET /chats/{chat_id}`.
- ✔️ Confirm another user cannot access the chat.
- ✔️ Create a message with `POST /chats/{chat_id}/messages`.
- ✔️ Confirm the response includes both user and assistant messages.
- ✔️ List messages with `GET /chats/{chat_id}/messages`.
- ✔️ Confirm invalid `agent_name` behavior is predictable.
- ✔️ Delete a test chat with `DELETE /chats/{chat_id}`.

## Workflows

- ✔️ Create a workflow with `POST /projects/{project_id}/workflows`.
- ✔️ List workflows with `GET /projects/{project_id}/workflows`.
- ✔️ Fetch a workflow with `GET /workflows/{workflow_id}`.
- ✔️ Confirm another user cannot access the workflow.
- ✔️ Add or verify workflow steps for the workflow.
- ✔️ Run a workflow with `POST /workflows/{workflow_id}/run`.
- ✔️ Confirm a workflow run row is created.
- ✔️ Confirm step run rows are created for workflows with steps.
- ✔️ Fetch a run with `GET /runs/{run_id}`.
- ✔️ Fetch run events with `GET /runs/{run_id}/events`.
- ✔️ Resume a run with `POST /runs/{run_id}/resume` when applicable.
- ✔️ Test streaming with `POST /workflows/{workflow_id}/runs/stream`.
- ✔️ Test the run stream with `GET /runs/{run_id}/stream`.
- ✔️ Delete a test workflow with `DELETE /workflows/{workflow_id}`.

## File Upload

- ✔️ Create or choose a project owned by the test user.
- ✔️ Upload a small `.txt` file with `POST /projects/{project_id}/documents`.
- ✔️ Confirm the response includes document ID, filename, filepath, status, and
  created timestamp.
- ✔️ Confirm the file exists under `uploads/`.
- ✔️ List documents with `GET /projects/{project_id}/documents`.
- ✔️ Confirm another user cannot list or upload documents for the project.
- ✔️ Try uploading an unsupported or oversized file once validation exists.
- ✔️ Try uploading a duplicate filename once collision handling exists.

Example:

```bash
curl -X POST http://127.0.0.1:8000/projects/1/documents \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@sample.txt"
```

## Document Processing

These checks apply once the processing endpoint and pipeline are implemented.

- ✔️ Process an uploaded TXT document.
- ✔️ Process an uploaded PDF document.
- ✔️ Process an uploaded DOCX document.
- ✔️ Confirm document status changes to `processing` while work is active.
- ✔️ Confirm document status changes to `indexed` after success.
- ✔️ Confirm document status changes to `failed` after extraction or embedding
  failure.
- ✔️ Confirm chunks are persisted in document order.
- ✔️ Confirm chunk overlap is applied as expected.
- ✔️ Confirm chunk metadata includes document ID, project ID, and source
  offsets or page metadata when available.
- ✔️ Confirm reprocessing does not create duplicate stale chunks.
- ✔️ Confirm another user cannot process or inspect chunks for the document.

## Embeddings and Retrieval

These checks apply once embeddings and retrieval are implemented.

- ✔️ Confirm embeddings are generated for every persisted chunk.
- ✔️ Confirm embedding model name and dimensions are recorded.
- ✔️ Run a retrieval query against a project with indexed documents.
- ✔️ Confirm retrieval returns chunks only from the authenticated user's
  project.
- ✔️ Confirm retrieval ranking is plausible for a known query.
- ✔️ Confirm chat responses can include retrieved context.
- ✔️ Confirm source metadata or citations are returned when enabled.

## Regression Checks

- [ ] Run the full test suite when tests exist.
- [ ] Check server logs for unexpected tracebacks.
- [ ] Confirm database migrations apply from a fresh database.
- [ ] Confirm API docs still load after schema changes.
- [ ] Confirm protected endpoints still reject missing, invalid, or cross-user
      access.
- [ ] Confirm write endpoints commit the expected data.
- [ ] Confirm failed write paths do not leave partial records unless explicitly
      intended.

## Useful Manual SQL Checks

Open psql:

```bash
docker exec -it ai-platform-postgres psql -U postgres -d ai_platform
```

Inspect tables:

```sql
\dt
select id, email, created_at from users order by id desc limit 5;
select id, user_id, name from projects order by id desc limit 5;
select id, project_id, filename, status from documents order by id desc limit 5;
select id, workflow_id, status, created_at from workflow_runs order by id desc limit 5;
```
