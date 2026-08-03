# Backend Architecture Decision Log

> Update this file whenever a change introduces or reverses a meaningful backend architecture, data model, infrastructure, security, processing, or provider decision.

## Table of Contents

1. [FastAPI as the web framework](#fastapi-as-the-web-framework)
2. [PostgreSQL as the primary datastore](#postgresql-as-the-primary-datastore)
3. [SQLAlchemy + Alembic for persistence and migrations](#sqlalchemy--alembic-for-persistence-and-migrations)
4. [API-only backend, separated from the frontend](#api-only-backend-separated-from-the-frontend)
5. [JWT authentication](#jwt-authentication)
6. [Separate entities for projects, chats, messages, documents, workflows, runs, and events](#separate-entities-for-projects-chats-messages-documents-workflows-runs-and-events)
7. [File storage and processing](#file-storage-and-processing)
8. [Document processing separated from embedding generation](#document-processing-separated-from-embedding-generation)
9. [RAG scoped per project](#rag-scoped-per-project)
10. [AI provider abstraction](#ai-provider-abstraction)
11. [Chat and embedding providers configured separately](#chat-and-embedding-providers-configured-separately)
12. [Workflows use ordered steps with explicit dependencies](#workflows-use-ordered-steps-with-explicit-dependencies)
13. [Workflow runs and run events are persisted](#workflow-runs-and-run-events-are-persisted)
14. [Background execution via Celery + Redis](#background-execution-via-celery--redis)
15. [PostgreSQL as source of truth for job status](#postgresql-as-source-of-truth-for-job-status)
16. [Environment-based configuration via Pydantic Settings](#environment-based-configuration-via-pydantic-settings)
17. [Docker and Terraform for deployment](#docker-and-terraform-for-deployment)
18. [RDS access restricted to the EC2 security group](#rds-access-restricted-to-the-ec2-security-group)
19. [Layered separation of routes, services, repositories, and models](#layered-separation-of-routes-services-repositories-and-models)

---

## FastAPI as the web framework

**Status:** Accepted

**Context**
The backend needs an async-capable Python web framework to serve a REST API with typed request/response validation and interactive docs for a multi-client (frontend + future integrations) product.

**Decision**
Use FastAPI as the application framework, served by Uvicorn.

**Why**
FastAPI provides native async support (needed for async DB access and I/O-bound AI provider calls), automatic OpenAPI docs, and Pydantic-based request/response validation, which fits an API-only, schema-driven backend.

**Consequences**
Fast to build typed endpoints; auto-generated docs (`/swagger`, `/redoc`) reduce the need for separate API documentation. Ties the codebase to Pydantic's request/response modeling conventions throughout.

**Evidence in code**

- `requirements.txt` — `fastapi==0.136.1`, `uvicorn==0.47.0`
- [app/main.py](app/main.py) — `FastAPI(title="AI Automation Platform", lifespan=lifespan, docs_url="/swagger", redoc_url="/redoc", openapi_url="/openapi.json")`
- `Dockerfile` — `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`

---

## PostgreSQL as the primary datastore

**Status:** Accepted

**Context**
The platform needs a relational store for structured entities (users, projects, workflows) and also needs vector similarity search for RAG retrieval.

**Decision**
Use PostgreSQL, with the `pgvector` extension, as the single primary datastore for both relational data and vector embeddings.

**Why**
Storing embeddings in the same database as the relational data they belong to (documents, chunks) avoids a separate vector-database dependency and keeps document/chunk/embedding data transactionally consistent.

**Consequences**
Simplifies infrastructure (one database instead of relational DB + separate vector store). Ties vector search performance to Postgres/pgvector characteristics rather than a specialized vector engine.

**Evidence in code**

- `docker-compose.yml` — `postgres` service uses image `pgvector/pgvector:pg17`
- `.env.example` — `DATABASE_URL=postgresql+asyncpg://DB_USER:DB_PASSWORD@localhost:5432/DB_NAME`
- [app/core/database.py](app/core/database.py) — `create_async_engine(settings.DATABASE_URL, ...)`
- [app/models/chunk_embedding.py](app/models/chunk_embedding.py) — `embedding: Vector(settings.EMBEDDING_DIM)` using `pgvector.sqlalchemy.Vector`
- `infra/modules/rds/main.tf` — `aws_db_instance.postgres`, engine `postgres`, version 15

---

## SQLAlchemy + Alembic for persistence and migrations

**Status:** Accepted

**Context**
The backend needs an ORM layer to map domain entities to Postgres tables, and a repeatable way to evolve the schema over time (30+ schema changes already applied).

**Decision**
Use SQLAlchemy 2.0 (async, declarative) as the ORM, and Alembic for schema migrations.

**Why**
SQLAlchemy 2.0's async engine integrates with FastAPI's async request handling; Alembic gives versioned, reviewable migrations tied directly to the SQLAlchemy models, which the project already relies on for iterative schema changes (e.g. adding Celery tracking columns, DAG execution support).

**Consequences**
Every schema change requires a corresponding Alembic revision, keeping history auditable. Adds a layer of migration-file maintenance on top of model changes.

**Evidence in code**

- `requirements.txt` — `SQLAlchemy==2.0.49`, `alembic==1.18.4`
- [app/core/database.py](app/core/database.py) — `class Base(DeclarativeBase)`, `AsyncSessionLocal`
- `app/models/` — 14 model files
- `alembic.ini`, `alembic/env.py` (reads `settings.DATABASE_URL`)
- `alembic/versions/` — e.g. `893dd2410a54_baseline_schema.py`, `91cc967ec6f2_dag_execution.py`, `d1a4c9b7f210_add_celery_job_tracking_columns.py`

---

## API-only backend, separated from the frontend

**Status:** Accepted

**Context**
Per the platform's workspace layout, the frontend (Django) is a separate repository and communicates only through the backend REST API.

**Decision**
The backend exposes only a JSON REST API and static assets (favicon); it does not render HTML templates or own any UI.

**Why**
Keeps the backend as the single source of truth for business logic while letting the frontend own presentation independently, per the platform's stated repository split.

**Consequences**
Backend and frontend can be deployed, versioned, and scaled independently. No CORS middleware is currently configured, implying the frontend either shares an origin at the network/proxy layer or CORS is expected to be added when needed — this should be verified against deployment topology (see `deploy/nginx/`).

**Evidence in code**

- `app/api/routes/` — REST routers only (auth, chats, documents, embeddings, projects, providers, workflows, workflow_runs, workflow_steps, workflow_events, agent_runs, health), aggregated in [app/api/router.py](app/api/router.py)
- [app/main.py](app/main.py) — mounts routers and a `/static` files directory only; no Jinja2/template engine is used
- No `CORSMiddleware`/`allow_origins` found anywhere under `app/` — not yet configured in code

---

## JWT authentication

**Status:** Accepted

**Context**
The API needs stateless authentication for a decoupled frontend and potential future clients, without server-side session storage.

**Decision**
Use JWT access and refresh tokens (via `python-jose`), with bcrypt password hashing and OAuth2-password-flow-compatible login.

**Why**
JWTs allow stateless verification of requests across services without a shared session store, fitting the API-only/decoupled-frontend architecture. The access/refresh split (distinguished via a `typ` claim) supports short-lived access tokens with a separate renewal path.

**Consequences**
Token revocation requires additional infrastructure (not evidenced in code today — e.g. no denylist found), a common trade-off of stateless JWTs. Google OAuth login is also supported alongside password login.

**Evidence in code**

- `requirements.txt` — `python-jose==3.5.0`, `passlib==1.7.4`, `bcrypt==4.0.1`
- [app/core/security.py](app/core/security.py) — `create_access_token`, `create_refresh_token`, `decode_access_token`, `pwd_context = CryptContext(schemes=["bcrypt"])`, `OAuth2PasswordBearer(tokenUrl="/auth/login")`
- [app/dependencies/auth.py](app/dependencies/auth.py) — `get_current_user` dependency enforcing `typ == "access"`
- [app/api/routes/auth.py](app/api/routes/auth.py) — `/register`, `/login`, `/google`, `/refresh`, `/me`
- [app/services/auth.py](app/services/auth.py) — `AuthService`

---

## Separate entities for projects, chats, messages, documents, workflows, runs, and events

**Status:** Accepted

**Context**
The platform combines several distinct capabilities — conversational chat, document/RAG management, and workflow automation — each with its own lifecycle and history.

**Decision**
Model each concern as its own SQLAlchemy entity/table rather than collapsing them into shared or generic tables: `Project`, `Chat`, `Message`, `Document`, `DocumentChunk`, `ChunkEmbedding`, `Workflow`, `WorkflowStep`, `WorkflowRun`, `WorkflowStepRun`, `WorkflowRunEvent`, `AgentRun`.

**Why**
Each entity has distinct fields and lifecycle state (e.g. a `Document` tracks processing/embedding status, a `WorkflowRun` tracks execution status and Celery task linkage) that don't map cleanly onto a shared/generic table. Projects act as the top-level scoping boundary for chats, documents, and workflows.

**Consequences**
Clear, queryable history per concern (e.g. per-step retries via `WorkflowStepRun.retry_count`) at the cost of more tables/migrations to maintain. Relationships are enforced via foreign keys with cascade deletes scoped through `Project`.

**Evidence in code**

- [app/models/project.py](app/models/project.py), [app/models/chat.py](app/models/chat.py), [app/models/message.py](app/models/message.py)
- [app/models/document.py](app/models/document.py), [app/models/document_chunk.py](app/models/document_chunk.py), [app/models/chunk_embedding.py](app/models/chunk_embedding.py)
- [app/models/workflow.py](app/models/workflow.py), [app/models/workflow_step.py](app/models/workflow_step.py), [app/models/workflow_run.py](app/models/workflow_run.py), [app/models/workflow_step_run.py](app/models/workflow_step_run.py), [app/models/workflow_run_event.py](app/models/workflow_run_event.py), [app/models/agent_run.py](app/models/agent_run.py)

---

## File storage and processing

**Status:** Accepted

**Context**
Users upload documents that must be persisted and later parsed for RAG, and the storage backend needs to work both in local development and on AWS in production.

**Decision**
Use a `StorageService` interface with two implementations — local disk (`LocalStorageService`) and S3 (`S3StorageService`) — selected via configuration, plus a separate set of format-specific extractors for text extraction.

**Why**
Abstracting storage behind an interface lets local development run without AWS credentials while production uses S3 (backed by an IAM role on the EC2 instance, per Terraform), without changing calling code.

**Consequences**
Any new storage backend must implement the same interface. File parsing is decoupled from storage, so new document formats only require a new extractor, not a storage change.

**Evidence in code**

- [app/services/storage/base.py](app/services/storage/base.py) — `StorageService` interface (`save/read/upload/download/delete/exists`)
- [app/services/storage/local.py](app/services/storage/local.py), [app/services/storage/s3.py](app/services/storage/s3.py)
- `app/core/config.py` — `STORAGE_PROVIDER` setting
- [app/services/extractors/](app/services/extractors/) — `base.py`, `docx.py`, `pdf.py` (pypdf), `txt.py`
- [app/api/routes/documents.py](app/api/routes/documents.py), [app/tasks/documents.py](app/tasks/documents.py)
- `infra/modules/s3/main.tf` — uploads bucket; `infra/modules/iam/main.tf` — IAM role granting S3 access to the EC2 instance

---

## Document processing separated from embedding generation

**Status:** Accepted

**Context**
Extracting text from an uploaded document and generating vector embeddings from that text are different concerns with different failure modes, providers, and costs.

**Decision**
Keep document parsing/chunking (`app/services/document.py`, `app/services/chunk.py`, `app/tasks/documents.py`) and embedding generation (`app/services/embedding.py`, `app/services/embedding_jobs.py`, `app/services/embedding_management.py`, `app/tasks/embeddings.py`) in separate modules and separate background tasks, tracked by separate status fields.

**Why**
A document can be successfully parsed and chunked while embedding generation fails or is retried independently (e.g. due to a provider outage), so the two need independently trackable status (`Document.status` vs `Document.embedding_status`, `Project.embedding_sync_status`).

**Consequences**
Failures in embedding generation don't require re-parsing the document; each stage can be retried/re-run independently. Adds a two-stage pipeline that callers must be aware of when checking "is this document ready for RAG."

**Evidence in code**

- [app/services/document.py](app/services/document.py), [app/services/chunk.py](app/services/chunk.py), [app/tasks/documents.py](app/tasks/documents.py)
- [app/services/embedding.py](app/services/embedding.py), [app/services/embedding_jobs.py](app/services/embedding_management.py), [app/tasks/embeddings.py](app/tasks/embeddings.py)
- [app/models/document.py](app/models/document.py) — separate `status` and `embedding_status` fields

---

## RAG scoped per project

**Status:** Accepted

**Context**
Multiple projects can each contain their own set of documents; a chat within a project should only retrieve context from that project's documents, not across the whole platform.

**Decision**
Thread `project_id` through retrieval and RAG service calls, filtering chunk retrieval to documents belonging to that project.

**Why**
Projects are the top-level organizational and data-isolation boundary in the domain model (`Project` owns `Document`s and `Chat`s), so scoping retrieval to a project keeps RAG answers relevant to that project's own content and prevents cross-project data leakage.

**Consequences**
Retrieval queries always require a project context; there is currently no cross-project or global search implemented.

**Evidence in code**

- [app/repositories/retrieval.py](app/repositories/retrieval.py) — joins/filters on `Document.project_id == project_id`
- [app/services/retrieval.py](app/services/retrieval.py), [app/services/rag.py](app/services/rag.py) — both take `project_id` as a parameter
- [app/prompts/rag.py](app/prompts/rag.py) — `RAGPromptBuilder`

---

## AI provider abstraction

**Status:** Accepted

**Context**
The platform needs to call different LLM providers (and switch between them, including fallback on failure) without changing calling code in chat/workflow services.

**Decision**
Define a base `AIProvider` abstract class with `chat`/`stream_chat`, and implement it per provider (Gemini, Groq, OpenRouter, Ollama), orchestrated through a single AI service with failover logic.

**Why**
A common interface lets the rest of the codebase (chat, workflows, agents) call `AIProvider.chat(...)` without knowing which underlying provider is active, and lets failover logic swap providers on error without touching callers.

**Consequences**
Adding a new provider means implementing the `AIProvider` interface, not modifying call sites. Currently only Gemini, Groq, OpenRouter, and Ollama are implemented — no OpenAI or Anthropic provider exists in code despite being common industry defaults.

**Evidence in code**

- [app/services/ai/providers/base.py](app/services/ai/providers/base.py) — `class AIProvider(ABC)`
- [app/services/ai/providers/gemini.py](app/services/ai/providers/gemini.py), `groq.py`, `openrouter.py`, `ollama.py`
- [app/services/ai/service.py](app/services/ai/service.py), [app/services/ai/failover.py](app/services/ai/failover.py), [app/services/ai/errors.py](app/services/ai/errors.py)

---

## Chat and embedding providers configured separately

**Status:** Accepted

**Context**
Chat completion and embedding generation are different capabilities that are often best served by different providers or models, and may need to be swapped independently.

**Decision**
Configure chat and embedding providers as fully separate settings (`CHAT_PROVIDER`/`EMBEDDING_PROVIDER`, distinct base URLs, API keys, models, and provider chains), and persist per-kind provider configuration in the database via `ProviderConfig.kind`.

**Why**
Decoupling the two lets the platform, for example, run chat against one provider while using a different (often cheaper or more specialized) provider for embeddings, and change one without affecting the other.

**Consequences**
Two independent provider configurations to manage and validate, but flexibility to mix providers per capability. `ProviderConfig` in the database allows runtime provider changes without redeploying, seeded from environment defaults at startup.

**Evidence in code**

- `app/core/config.py` — separate `CHAT_*` and `EMBEDDING_*` settings blocks, `ChatProvider`/`EmbeddingProvider` enums
- [app/models/provider_config.py](app/models/provider_config.py) — `ProviderConfig.kind`, unique constraint on `(kind, provider)`
- [app/services/provider_config.py](app/services/provider_config.py) — `seed_defaults`/`load_from_db`, invoked from `app/main.py` lifespan

---

## Workflows use ordered steps with explicit dependencies

**Status:** Accepted

**Context**
Automations in the platform need to express multi-step processes where some steps depend on the output of earlier steps, not just a linear sequence.

**Decision**
Model workflows as an ordered list of `WorkflowStep`s, each with a `step_order`, a `depends_on: list[int]` field, and an optional `condition` for conditional execution, executed by a DAG engine.

**Why**
A flat linear sequence can't express steps that depend on multiple prior steps or need conditional branching; an explicit dependency list lets the execution engine build and run a proper DAG rather than assuming strict order.

**Consequences**
Execution logic must resolve the dependency graph (`app/services/workflow/dag_engine.py`) rather than simply iterating steps in order. This was added as a dedicated migration, indicating it evolved from a simpler sequential model.

**Evidence in code**

- [app/models/workflow_step.py](app/models/workflow_step.py) — `depends_on: Mapped[list[int]]` (JSON), `condition`, `step_order`
- [app/services/workflow/dag_engine.py](app/services/workflow/dag_engine.py), [app/services/workflow/workflow.py](app/services/workflow/workflow.py), [app/services/workflow/ai_executor.py](app/services/workflow/ai_executor.py)
- `alembic/versions/91cc967ec6f2_dag_execution.py`

---

## Workflow runs and run events are persisted

**Status:** Accepted

**Context**
Workflow executions need to be auditable and recoverable — e.g. resumed after a backend restart, or inspected for debugging — not just tracked transiently in memory or Celery's own result backend.

**Decision**
Persist each workflow execution as a `WorkflowRun` with per-step `WorkflowStepRun` records (status, execution time, retry count, error message), and persist individual execution events as `WorkflowRunEvent` rows.

**Why**
Durable run/event history in Postgres allows recovering in-progress workflows on startup and exposing execution history/events via API, independent of Celery's transient task result storage.

**Consequences**
Every workflow step execution writes to Postgres, adding write load proportional to workflow complexity, but gives full replayable history and supports crash recovery.

**Evidence in code**

- [app/models/workflow_run.py](app/models/workflow_run.py), [app/models/workflow_step_run.py](app/models/workflow_step_run.py), [app/models/workflow_run_event.py](app/models/workflow_run_event.py)
- [app/services/workflow/recovery.py](app/services/workflow/recovery.py) — recovers running workflows on startup, invoked from `app/main.py` lifespan
- [app/api/routes/workflow_events.py](app/api/routes/workflow_events.py), [app/repositories/workflow_events.py](app/repositories/workflow_events.py)
- `alembic/versions/75ee3bb85ff1_add_workflow_runs_and_step_runs.py`, `149bf5603048_add_workflow_run_and_workflow_step_run_.py`

---

## Background execution via Celery + Redis

**Status:** Accepted

**Context**
Document processing, embedding generation, and workflow execution are long-running operations that must not block API request/response cycles.

**Decision**
Move long-running operations to Celery workers, with Redis as the message broker.

**Why**
Celery lets these operations run asynchronously outside the request lifecycle, with a dedicated `worker` process/container separate from the API process, so slow AI/IO-bound work doesn't hold up HTTP responses.

**Consequences**
Requires running and monitoring a separate worker process, and a Redis instance purely as a broker (not used as an application cache or result backend, per explicit code comment).

**Evidence in code**

- `requirements.txt` — `celery==5.5.3`, `redis==5.2.1`
- [app/core/celery_app.py](app/core/celery_app.py) — broker via `settings.CELERY_BROKER_URL`, `task_ignore_result=True`
- [app/tasks/documents.py](app/tasks/documents.py), [app/tasks/embeddings.py](app/tasks/embeddings.py), [app/tasks/workflows.py](app/tasks/workflows.py), [app/tasks/provider_config.py](app/tasks/provider_config.py)
- `docker-compose.yml` — `worker` service: `celery -A app.core.celery_app worker --loglevel=info`; `redis` service commented as broker-only

---

## PostgreSQL as source of truth for job status

**Status:** Accepted

**Context**
Celery task results are ephemeral by default and not designed for querying job status/history from the API.

**Decision**
Do not rely on Celery's result backend; instead store job/task status, progress, output, and errors directly on the relevant Postgres rows, linked via a `celery_task_id` column.

**Why**
The API and frontend need to query job status and history reliably (e.g. "is this document still processing?"), which a transient Celery result backend does not support well; Postgres gives durable, queryable, and consistent state.

**Consequences**
Task code must explicitly write status/progress/error to the DB at each stage rather than relying on Celery's built-in state tracking, adding some boilerplate to each task but keeping status consistent with the rest of the domain data.

**Evidence in code**

- [app/core/celery_app.py](app/core/celery_app.py) — comment: "PostgreSQL ... remains the sole source of truth for job status, progress, output and errors -- task results are never relied upon"
- [app/models/document.py](app/models/document.py) — `celery_task_id`, `status`, `processing_error`
- [app/models/workflow_run.py](app/models/workflow_run.py) — `celery_task_id`, `status`, `error`
- `alembic/versions/d1a4c9b7f210_add_celery_job_tracking_columns.py`

---

## Environment-based configuration via Pydantic Settings

**Status:** Accepted

**Context**
The backend runs in multiple environments (local dev, AWS) and needs configuration (DB URL, provider keys, storage backend) that varies per environment without code changes.

**Decision**
Centralize configuration in a single `Settings(BaseSettings)` class (Pydantic Settings), loaded from environment variables / a `.env` file, with a documented `.env.example`.

**Why**
Pydantic Settings gives typed, validated configuration loaded from the environment, consistent with FastAPI/Pydantic use elsewhere in the codebase, and matches twelve-factor-style config-via-environment expected for containerized/EC2 deployment.

**Consequences**
All configuration must go through this single settings object, giving one place to see every configurable value; secrets must be provisioned via environment/SSM rather than committed to the repo.

**Evidence in code**

- `app/core/config.py` — `class Settings(BaseSettings)`, `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`, module-level `settings = Settings()`
- `.env.example` — documents all expected variables
- `infra/modules/ssm/main.tf` — writes `DATABASE_URL`, `AWS_S3_BUCKET`, `AWS_REGION`, `GOOGLE_CLIENT_ID`, `OLLAMA_BASE_URL` to SSM Parameter Store for production

---

## Docker and Terraform for deployment

**Status:** Accepted

**Context**
The backend needs a reproducible build artifact and provisioned AWS infrastructure (compute, database, storage, networking) to run in production.

**Decision**
Package the API as a Docker image (also used for the Celery worker), and provision AWS infrastructure (EC2, RDS, S3, networking, IAM, ECR, Route53, SSM) via Terraform modules.

**Why**
Docker gives a consistent runtime across local development (`docker-compose.yml`) and production; Terraform modules give declarative, version-controlled infrastructure provisioning for the AWS resources the backend depends on.

**Consequences**
Infrastructure changes go through Terraform review rather than manual console changes. The API itself is deployed to a Terraform-provisioned EC2 instance (not via `docker-compose.yml`, which only manages `postgres`, `redis`, and `worker` for local dev).

**Evidence in code**

- `Dockerfile` — Python 3.13-slim-bookworm, installs `requirements.txt`, runs uvicorn
- `docker-compose.yml` — `postgres`, `redis`, `worker` services for local development
- `infra/main.tf` — wires `network`, `s3`, `iam`, `ec2`, `route53`, `ollama`, `rds`, `ecr`, `ssm` modules
- `infra/modules/ec2/main.tf` — `aws_instance.api`, Elastic IP, `infra/userdata.sh`
- `infra/modules/rds/main.tf`, `infra/modules/s3/main.tf`, `infra/modules/ecr/main.tf`, `infra/modules/ollama/main.tf` (self-hosted LLM inference on a separate EC2 instance)

---

## RDS access restricted to the EC2 security group

**Status:** Accepted

**Context**
The Postgres database holds all application data and must not be reachable from the public internet.

**Decision**
Restrict inbound access to the RDS instance's security group to only the backend EC2 instance's security group on port 5432, and mark the RDS instance as not publicly accessible.

**Why**
The only legitimate client of the database is the backend API/worker running on the EC2 instance; scoping the security group rule to that specific security group (rather than a CIDR range) prevents any other network path to the database, including the public internet.

**Consequences**
Only workloads running with the `ec2` security group can reach Postgres — any new service needing DB access (e.g. a bastion host, a second app server) must be explicitly added to that security group or granted a new rule.

**Evidence in code**

- `infra/modules/network/main.tf` — `aws_security_group.rds` ingress on port 5432 restricted to `security_groups = [aws_security_group.ec2.id]`
- `infra/modules/rds/main.tf` — `aws_db_instance.postgres` sets `publicly_accessible = false`, `vpc_security_group_ids = [var.security_group]`

---

## Layered separation of routes, services, repositories, and models

**Status:** Accepted

**Context**
As the number of domains (auth, chats, documents, workflows, providers) grew, request handling, business logic, and data access needed clear boundaries to stay maintainable.

**Decision**
Organize the codebase into distinct layers: `app/api/routes/` (HTTP), `app/schemas/` (Pydantic I/O models), `app/services/` (business logic), `app/repositories/` (data access), `app/models/` (SQLAlchemy ORM only), and `app/dependencies/` (FastAPI DI wiring composing repositories into services).

**Why**
Separating these concerns keeps routers thin (HTTP concerns only), keeps ORM models free of business logic, and lets services be composed from repositories via dependency injection — consistent with the explicit convention documented in code that repositories manipulate entities while services/routes control transaction boundaries.

**Consequences**
More files/indirection per feature (a new domain typically needs a model, schema, repository, service, and route), but each layer stays independently testable and swappable (e.g. storage or AI providers can change without touching routers).

**Evidence in code**

- [app/api/routes/](app/api/routes/), [app/api/router.py](app/api/router.py)
- [app/schemas/](app/schemas/)
- [app/services/](app/services/) (including `ai/`, `storage/`, `workflow/`, `extractors/` subpackages)
- [app/repositories/](app/repositories/)
- [app/models/](app/models/)
- [app/dependencies/services.py](app/dependencies/services.py), [app/dependencies/repositories.py](app/dependencies/repositories.py)
- [app/core/database.py](app/core/database.py) — comment: "Repositories manipulate entities. Services/routes decide when a transaction is committed."
