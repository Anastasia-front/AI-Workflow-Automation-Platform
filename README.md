# AI Workflow Automation Platform

A lightweight FastAPI-based AI workflow automation platform for managing users, projects, chats, documents, workflows, and agent runs.

See [DECISIONS.md](DECISIONS.md) for the architecture decision log.

## Setup

1. Create and activate the virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:

   ```bash
   uvicorn app.main:app --reload
   ```

## Commands & Workflow

### 1. Generate JWT secret key

Generate a secure secret for authentication:

```bash
python3 -c "import secrets; print(secrets.token_hex(64))"

or
openssl rand -hex 64 # and paste manually
```

Copy the output into your `.env` file:

```text
JWT_SECRET=your_generated_secret_here
```

**Best practice (production systems)**

```
generate secret once
store in:
AWS Secrets Manager / GCP Secret Manager / Vault
never in .env in production
```

For DB_PASSWORD:

```
openssl rand -base64 32
```

### 2. Create environment file

```bash
cp .env.example .env
```

Then ensure `.env` contains all needed variables.

For PROVIDER_CONFIG_ENCRYPTION_KEY use:

```text
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Then copy the printed value into .env

### 3. Verify environment setup

```bash
python3 -c "from app.core.config import settings; print(settings.DATABASE_URL)"
```

### 4. Docker (Database)

Start infrastructure:

```bash
docker compose up -d
```

Stop infrastructure:

```bash
docker compose down
```

Stop and reset database (DELETE ALL DATA):

```bash
docker compose down -v
docker compose up -d
```

Check running containers:

```bash
docker ps
```

### 5. Database (Postgres)

Open Postgres CLI:

```bash
docker exec -it ai-platform-postgres psql -U postgres -d ai_platform
```

Inside psql:

```sql
\l      -- list databases
\c ai_platform      -- connect to DB
\dt      -- list tables
```

Useful commands:

```
-- Table structure
\d users

-- More detailed table structure
\d+ users

-- First rows
SELECT * FROM users LIMIT 20;

-- List databases
\l

-- List roles
\du

-- Current connection
\conninfo

-- Quit the pager when you see (END)
q

-- Disable pager
\pset pager off
```

### 6. Database migrations (Alembic)

Create a new migration:

```bash
alembic revision --autogenerate -m "message here"
```

Apply migrations:

```bash
alembic upgrade head
```

Rollback one migration:

```bash
alembic downgrade -1
```

Check migration history:

```bash
alembic history
```

### 7. Development server (FastAPI)

Run the API server:

```bash
uvicorn app.main:app --reload
```

Default API URL:

```text
http://127.0.0.1:8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

ReDoc:

```text
http://127.0.0.1:8000/redoc
```

### 7b. Background jobs (Celery + Redis)

Document processing, embedding rebuild/sync, and workflow runs execute in a
separate Celery worker process backed by Redis -- not inside the FastAPI
request. Postgres remains the source of truth for status; Redis is only the
broker.

The worker must run natively (same host as the API, not in Docker) so it
resolves `localhost` the same way the API does -- this matters for local
providers like Ollama at `http://localhost:11434`, which is unreachable from
inside a container as `localhost` there refers to the container itself.

Start Redis (already included in `docker compose up -d`, see step 4):

```bash
docker compose up -d redis
```

Start the worker (separate terminal, same venv/.env as the API):

```bash
celery -A app.core.celery_app worker --loglevel=info
```

`CELERY_BROKER_URL` defaults to `redis://localhost:6379/0` (see `.env.example`).

If the worker is not running, start/process/sync/run requests will still
return `202` immediately and create a `queued`/`pending` record, but nothing
will pick the job up until a worker is started.

### 8. Auth testing

Register user:

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"123456"}'
```

Login:

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"123456"}'
```

Access protected route:

```bash
curl http://127.0.0.1:8000/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 9. Code quality / debugging

Run a Python file:

```bash
python3 file.py
```

Check imports / environment issues:

```bash
python3 -c "import app; print('OK')"
```

Check installed packages:

```bash
pip list
```

### 10. Project reset (full clean restart)

⚠️ Deletes DB and rebuilds everything

```bash
docker compose down -v
docker compose up -d
alembic upgrade head
```

### 11. Quick health check

```bash
curl http://127.0.0.1:8000/docs
```

or

```bash
curl http://127.0.0.1:8000/health
```

### Recommended workflow

Daily development loop:

```bash
docker compose up -d
source venv/bin/activate
uvicorn app.main:app --reload
```

When model changes:

```bash
alembic revision --autogenerate -m "update"
alembic upgrade head
```

## Notes

- A `.gitignore` file is included to exclude local environment files, build artifacts, editor files, and sensitive configuration.
- Keep environment variables in a local `.env` file or another file that is not checked into source control.

### Application security layer

- `config.py` → settings
- `database.py` → engine + session + Base + `get_db`
- `models/` → Base import
- `services/` → DB dependency
- `api/` → `get_db` dependency

### Architecture domain feature layered structure:

```
            Route
              ↓
            Service
              ↓
            Model
              ↓
            DB / ORM
```

- Route:
  - HTTP concerns
  - status codes
  - auth dependencies

- Service:
  - business logic

- Model:
  - persistence

- Schema:
  - API contracts

### Chat and messages flow:

```
User
 → owns Project
 → creates Chat inside Project
 → sends Messages
 → gets chat history
```

### AI architecture layer

- route only handles HTTP
- service handles DB + orchestration
- AI service handles LLM provider

gemma2:2b - the model is actually a good choice at this stage because:

It’s lightweight (1.6 GB) → fast on local machines
It’s sufficient for:

- chat responses
- basic assistant behavior
- API wiring / architecture testing

Then move to:

- llama3
- mistral
- qwen2.5

### Chat Context (Memory Upgrade)

```
        user message
              ↓
        load chat history (DB)
              ↓
        send full context to Ollama
              ↓
        AI response
              ↓
        save both messages
```

## System Prompts + AI Context Architecture

### Core AI backend concepts:

- prompt engineering
- context injection
- AI orchestration
- conversational control
- instruction hierarchy

### Core idea of an automation platform instead of just chat.

```
      User Request
            ↓
      Workflow
            ↓
      Multiple AI Steps
            ↓
      Structured Output
```

Example workflows:

- blog generation
- research pipeline
- code review
- summarization
- SEO generation
- email automation

### Backend infrastructure for now:

```
      Auth Layer
            ↓
      Ownership Layer
            ↓
      Domain Layer
            ↓
      Conversation Layer
            ↓
      Agent Layer
            ↓
      Workflow Layer
            ↓
      AI Service Layer
            ↓
      Ollama
```

### Workflow Steps Engine

```
      Goal:

            Workflow
              ↓
            Step 1
            Step 2
            Step 3
              ↓
            Final output

      Example:

            Input:
            "Write article about FastAPI"

            Step 1 → Research topic
            Step 2 → Create outline
            Step 3 → Write final article
```

### Streaming execution design

```
      WorkflowService
            ↓
      step-by-step execution
            ↓
      stream progress events to frontend
```

Frontend behavior:

- show live step progress
- render execution timeline
- debug workflow runs in real-time
- build “agent execution UI

The clean architecture separation:

- workflows → definition (CRUD, metadata, steps structure)
- workflow_steps → step configuration (templates, order, prompts)
- workflow_runs → execution layer (runtime, logs, streaming, results)
  - run_workflow() → core engine (no streaming)
  - run_workflow_stream() → wraps core engine and yields events

```
      - Workflows = Blueprint
      - Steps = Instructions
      - WorkflowRuns = Execution Engine
      - Streaming = Runtime telemetry
```

## Workflow engine full testing guide

This guide validates the full workflow execution pipeline:

- Workflow Runs
- Workflow Step Runs (execution persistence)
- Workflow Run Events (event bus)
- Retry logic
- Streaming (SSE)
- Error handling
<pre>
* The full retry policy *
A production-grade retry policy for something like an LLM call in your workflow engine would look like: attempt fails → check if the failure type looks transient → if yes, wait with exponential backoff (+ jitter) → retry, feeding back specific error context if it's a validation failure (Topic 9's self-correction pattern) → repeat up to a max attempt count → if still failing, or if the failure type looked permanent from the start, stop retrying and route to a dead-letter queue for human review, logging the full failure context.
</pre>

1. Preconditions

```
1.1 Database must contain:
                  SELECT * FROM workflows;
                  SELECT * FROM workflow_steps;

Expected:

                  At least 1 workflow
                  At least 2–3 steps per workflow

Example:

                  workflow_id = 2
                  steps:
                  1 → research
                  2 → summarize
                  3 → final output

1.2 Tables must exist
                  \dt

You must see:

                  workflow_runs
                  workflow_step_runs
                  workflow_run_events

If missing → run migrations.
```

2. Test NON-STREAM workflow execution

```
2.1 Run workflow

Use API:
                  POST /workflows/{workflow_id}/run

Example:
                  {
                  "input": "How to test workflow system"
                  }

2.2 Expected API response

                  {
                  "workflow_id": 2,
                  "input": "...",
                  "output": "final AI result",
                  "status": "completed"
                  }

2.3 Verify workflow_runs table

                  SELECT * FROM workflow_runs ORDER BY id DESC;

Expected:

                  New row inserted
                  output NOT NULL
                  status = completed

2.4 Verify workflow_step_runs table

                  SELECT * FROM workflow_step_runs ORDER BY id DESC;

Expected:
                  field	expected
                  workflow_run_id	matches run
                  step_order	1..N
                  input	prompt with injected variables
                  output	AI response
                  status	completed
                  execution_time_ms	> 0
                  retry_count	>= 0

If empty → step execution is not running.

2.5 Verify event log table

                  SELECT * FROM workflow_run_events ORDER BY id DESC;

Expected events:

                  step_start
                  step_done
                  workflow_done

Each row should contain:

                  workflow_run_id
                  event_type
                  payload JSON
```

3. Test RETRY logic

```
3.1 Force failure (temporary test)

Modify AIService to temporarily fail:
raise Exception("TEST FAILURE")

3.2 Run workflow again

Expected:

                  retry_count increases (1–3)
                  multiple retry events appear:
                  SELECT * FROM workflow_run_events WHERE event_type = 'retry';

3.3 Expected behavior

                  step_run still created
                  status = failed (if max retries exceeded)
                  error_message populated
```

4. Test STREAMING (SSE)

```
4.1 Run streaming endpoint

                  POST /workflows/{workflow_id}/runs/stream

4.2 Use curl to verify SSE

                  curl -N http://localhost:8000/workflows/2/runs/stream \
                  -H "Content-Type: application/json" \
                  -d '{"input":"test streaming workflow"}'

4.3 Expected SSE format

                  event: step_start
                  data: {...}

                  event: step_done
                  data: {...}

                  event: workflow_done
                  data: {...}

4.4 Verify DB events still written

                  SELECT * FROM workflow_run_events;

Expected:

                  step_start
                  step_done
                  retry (if any)
                  workflow_done
```

5. Test STREAMING an existing run (SSE, DB-tailed)

```
5.1 Stream events for a run already created (e.g. via /workflows/{workflow_id}/run,
    including runs executed by the Celery worker)

                  GET /runs/{run_id}/stream

5.2 Use curl to verify SSE

                  curl -N http://localhost:8000/runs/2/stream \
                  -H "Authorization: Bearer <token>"

5.3 Expected behavior

                  Replays events already stored for the run, then polls the
                  DB every ~1s for new rows until a terminal event
                  (completed/failed/cancelled) or client disconnect.
```

5. Validate FULL PIPELINE CONSISTENCY

```
After execution:

5.1 workflow_runs
                  SELECT id, status, output FROM workflow_runs;

Expected:

                  status = completed
                  output NOT NULL

5.2 workflow_step_runs

                  SELECT step_order, status, execution_time_ms FROM workflow_step_runs;

Expected:

                  All steps executed in correct order
                  execution_time_ms populated
                  no missing steps

5.3 workflow_run_events

                  SELECT event_type, COUNT(*)
                  FROM workflow_run_events
                  GROUP BY event_type;

Expected:

                  step_start > 0
                  step_done > 0
                  workflow_done = 1
```

6. Debug checklist (if something is broken)

```
6.1 No step_runs created

Check:

                  _execute_steps() is actually called
                  db.add(step_run) executed
                  await db.commit() reached
                  no silent exception before commit

6.2 No events created

Check:

                  _emit_event() is called
                  await db.flush() not failing
                  workflow_run.id exists (flush before execution)

6.3 workflow_runs created but empty output

Likely causes:

                  AI service returned None
                  exception swallowed in retry loop
                  final_output never assigned

6.4 SQL table missing errors

Run migrations:

                  alembic upgrade head

or recreate DB schema.
```

7. Success Criteria (FULL SYSTEM READY)

```
System is correct if ALL are true:

                  Execution
                  workflow_runs created
                  workflow_steps executed in order
                  workflow_step_runs populated
                  Reliability
                  retry logic works
                  errors stored in DB
                  Observability
                  workflow_run_events populated
                  SSE stream emits events correctly
                  Output
                  workflow_run.output is never NULL
```

### DAG execution model

```
        Step A
       /      \
   Step B    Step C
       \      /
        Step D
         |
      Step E
```

Key capabilities:

- parallel execution (B & C run concurrently)
- dependency resolution
- conditional routing
- step-level isolation
- partial failure handling

2. Core conceptual shift

- Old model

Each step depends on: previous_output

- New model

Each step depends on:

```
dependencies = [step_ids]
inputs = resolved dependency outputs
```

No global "previous_output" anymore.

```
            File -> Responsibility

workflow_service.py  -> orchestration
dag_engine.py        -> DAG scheduling
step_executor.py     -> AI execution
event_bus.py         -> SSE + events
```

#### For now architecture becomes:

- Layer 1 — DAG Storage - Workflow - WorkflowStep - dependencies - conditions - tools - models
- Layer 2 — Runtime Engine - scheduler - executor - retry manager - timeout manager - event bus - parallel runner
- Layer 3 — Agent Runtime - tool calls - memory - context - reflection - routing - planning

```
workflow/
├── workflow.py # orchestration
├── dag_engine.py # scheduler
├── ai_executor.py # LLM calls
├── event_bus.py # events
├── repositories/
│ ├── workflow_runs.py
│ ├── workflow_steps.py
│ └── workflow_events.py
```

Production version is to build tasks explicitly:

```
Step 14 = success
Step 15 = raises AttributeError

=> results contains:

- success result for 14
- failed result for 15

=> workflow can:

- continue_on_error=True -> keep going
- continue_on_error=False -> stop cleanly
```

Persistent DAG state:

```
Run workflow
↓
Step 1 completed
↓
Step 2 completed
↓
Server crashes
↓
Restart
↓
Resume from Step 3
```

Attach ownership from the moment the run is created:

```
Route
 └── get_current_user()
      └── user.id
            ↓
WorkflowService.run_workflow(user_id)
            ↓
WorkflowRunRepository.create(user_id)
            ↓
WorkflowRun.user_id saved
```

### RAG

The pipeline naturally becomes

```
            Upload
                ↓
            Document
                ↓
            Extract text
                ↓
            Chunks
                ↓
            Embeddings
                ↓
            Vector search
                ↓
            Relevant chunks
                ↓
            Prompt
                ↓
            LLM
                ↓
            Answer
```

And the architecture should become:

```
            Chat Endpoint
                  │
                  ▼
            RAGService
                  │
                  ├────────► RetrievalService
                  │
                  └────────► AIService
                              │
                              ▼
                              Ollama
```

Rag service responsibility is only:

```
                  question
                  ↓
                  retrieve chunks
                  ↓
                  build context
                  ↓
                  call AIService
                  ↓
                  return answer + sources
```

- It should not know anything about FastAPI.
- It should not know anything about HTTP.
- It should simply expose answer.

The flow becomes:

```
                  POST /messages
                        │
                        ▼
                  ChatService.create_message()
                        │
                        ├── save user message
                        ├── load history
                        ├── RAGService.retrieve()
                        ├── AIService.generate_chat_response()
                        ├── save assistant + sources
                        └── return messages
```

Clean separation:

```
                  Router
                              HTTP only
                  ChatService
                              orchestration
                  RAGService
                              retrieval + AI coordination
                  PromptBuilder
                              pure string logic
                  AIService
                              external LLM I/O
                  RetrievalService
                              vector DB search
```

Maybe add later RAG features like in production SaaS:

- Score aggregation
- Better source structure
- RAG tracing persistence

## Infrastructure

```
                        GitHub
                              |
                        GitHub Actions
                              |
                  -------------------------
                  |                       |
            Terraform            Docker build
                  |                       |
            AWS Infra              Amazon ECR
                  |
            -------------------------------
            |             |              |
            EC2           RDS            S3
```

### Infrastructure (Terraform)

Infrastructure is managed with **Terraform** and follows a modular structure.

## Structure

```text
infra/
├── backend.tf          # Terraform backend configuration
├── provider.tf         # AWS provider configuration
├── variables.tf        # Root input variables
├── outputs.tf          # Root outputs
├── main.tf             # Module composition
├── userdata.sh         # EC2 bootstrap script
└── modules/
    ├── network/        # VPC, subnets, security groups
    ├── iam/            # IAM roles and instance profiles
    ├── ec2/            # API server
    ├── rds/            # PostgreSQL database
    ├── s3/             # File storage
    ├── ecr/            # Docker image registry
    └── ssm/            # Parameter Store (application secrets)
```

## Module responsibilities

| Module      | Purpose                                                                                      |
| ----------- | -------------------------------------------------------------------------------------------- |
| **network** | Creates or manages networking resources (VPC, subnets, security groups).                     |
| **iam**     | Creates IAM roles and instance profiles required by EC2.                                     |
| **ec2**     | Runs the backend application.                                                                |
| **rds**     | Hosts the PostgreSQL database.                                                               |
| **s3**      | Stores uploaded documents and application files.                                             |
| **ecr**     | Stores Docker images for deployment.                                                         |
| **ssm**     | Stores application secrets and environment variables in AWS Systems Manager Parameter Store. |

## Deployment

Initialize Terraform:

```bash
terraform init
```

Preview infrastructure changes:

```bash
terraform plan
```

Create or update infrastructure:

```bash
terraform apply
```

Destroy infrastructure:

```bash
terraform destroy
```

## Current backend

Terraform state is currently stored **locally**.

## Future improvement

Migrate the Terraform state to an S3 backend:

```hcl
terraform {
  backend "s3" {
    bucket = "your-terraform-state"
    key    = "ai-platform/terraform.tfstate"
    region = "eu-central-1"
  }
}
```

This enables shared state, state locking, and safer team collaboration.

## Terraform Commands

Format Terraform files:

```bash
terraform fmt
```

Initialize Terraform:

```bash
terraform init
```

Validate configuration:

```bash
terraform validate
```

Preview infrastructure changes:

```bash
terraform plan
```

Apply infrastructure:

```bash
terraform apply
```

Destroy infrastructure:

```bash
terraform destroy
```

---

## Pre-Apply Checklist

Before running `terraform apply`, verify:

- [ ] `terraform validate` succeeds
- [ ] `terraform plan` shows only expected resources
- [ ] No NAT Gateway is being created
- [ ] No Load Balancer is being created
- [ ] EC2 instance type is `t2.micro`
- [ ] RDS instance class is `db.t3.micro`
- [ ] RDS is **not** publicly accessible
- [ ] S3 bucket name is globally unique
- [ ] SSH access is restricted to your IP (recommended)
- [ ] `terraform.tfvars` is **not** committed to Git

---

## Current Security Notes

Current EC2 Security Group allows:

| Port       | Source      | Purpose |
| ---------- | ----------- | ------- |
| `22/tcp`   | `0.0.0.0/0` | SSH     |
| `80/tcp`   | `0.0.0.0/0` | HTTP    |
| `8000/tcp` | `0.0.0.0/0` | FastAPI |

This configuration is acceptable for local development and initial testing, but should be tightened before production deployment.

### Recommended Improvements

- Restrict SSH (`22`) to your public IP
- Place the backend behind Nginx
- Expose only ports `80` and `443`
- Close public access to port `8000`
- Enable HTTPS (TLS)

---

## Terraform Backend

Terraform state is currently stored locally.

Later, migrate the state to an S3 backend:

```hcl
terraform {
  backend "s3" {
    bucket = "your-terraform-state"
    key    = "ai-platform/terraform.tfstate"
    region = "eu-central-1"
  }
}
```

Using a remote backend is recommended once the infrastructure becomes stable or Terraform is managed through CI/CD.

---

## SSM Parameters

Terraform stores application secrets in AWS Systems Manager Parameter Store under:

```text
/ai-platform/*
```

Example parameters:

```text
/ai-platform/JWT_SECRET
/ai-platform/OLLAMA_MODEL
/ai-platform/OLLAMA_FALLBACK_MODEL
/ai-platform/OLLAMA_EMBEDDING_MODEL
/ai-platform/STORAGE_PROVIDER
```

`DATABASE_URL` should be added after the RDS instance has been created, since it depends on the generated database endpoint.

Example:

```text
postgresql+asyncpg://postgres:<password>@<rds-endpoint>:5432/app
```

### Before terraform apply, fix/check these:

- Security risk: EC2 SSH port 22 is open to 0.0.0.0/0. Better restrict it to your IP. Use CIDR format (your.ip.address/32)
- Security risk: EC2 port 8000 is open publicly. Fine for testing, but not ideal long-term.
- Cost risk: RDS db.t3.micro may be free-tier eligible only depending on your AWS account/- free-tier status. Monitor Billing.
- IAM issue: AmazonS3FullAccess is too broad. It works, but later replace it with bucket-specific permissions.
- Missing DATABASE_URL in SSM: Your SSM parameters include JWT/Ollama/storage settings, but not - DATABASE_URL. You will need to add it after RDS endpoint exists or generate it from Terraform.
- S3 bucket name: ai-platform-uploads must be globally unique. If apply fails, change project_name.

## GitHub Actions flow:

```
git push → build Docker image → push to ECR → SSH into EC2 → pull image → restart container
```

A solid CI/CD pipeline:

- Checkout code.
- Configure AWS credentials.
- Login to ECR.
- Build image.
- Push image.
- SSH to EC2.
- Download .env from SSM.
- Pull latest image.
- Run Alembic migrations.
- Replace the running container.
- Verify with /health.

```
git push
        │
        ▼
GitHub Actions
        │
        ├── build Docker image
        ├── push → Amazon ECR
        └── send SSM command
                    │
                    ▼
               EC2 instance
                    │
        pull newest image
        run migrations
        restart container
        health check
                    │
                    ▼
        http://ec2-3-75-228-59.eu-central-1.compute.amazonaws.com/docs
```

## Adding a new environment variable

Whenever you add a new environment variable, update **both** places:

### 1. Local development

Add the variable to:

```bash
.env
```

### 2. AWS (Production)

Add the variable to Terraform:

```hcl
infra/terraform.tfvars
# or wherever env_vars are defined
```

Then apply the changes:

```bash
cd infra

terraform plan
terraform apply
```

Terraform will update the AWS SSM Parameter Store automatically.

> **Reminder:** If you forget to update AWS SSM, the application will work locally but fail after deployment because the new variable will not exist on EC2.

TODO:

### TERRAFORM NETWORK CONFIGURATION

Today (backend only)

```
Internet
      │
      ▼
EC2
 ├── 22  -> only your IPs
 ├── 80  -> open (API)
 └── 443 -> open (when HTTPS is enabled)
```

Later (frontend + backend)

```
Internet
      │
      ▼
Frontend EC2
 ├──22   -> your IPs
 ├──80   -> everyone
 └──443  -> everyone

        │ REST API

Backend EC2
 ├──22   -> your IPs
 ├──80/443 -> preferably only frontend SG or Load Balancer
 └──5432 -> only RDS SG
```

- SSH (22) → restricted to your IP(s)
- HTTP (80) → open to everyone if you're serving a website
- HTTPS (443) → open to everyone if you're serving a website

UPDATE:

- variables.tf

```
variable "ssh_allowed_cidrs" {
type = list(string)
}

variable "http_allowed_cidrs" {
type = list(string)
}

variable "https_allowed_cidrs" {
type = list(string)
}
```

- terraform.tfvars:

```
ssh_allowed_cidrs = [
"149.232.202.17/32",
"93.1.106.242/32",
]

http_allowed_cidrs = [
"0.0.0.0/0",
]

https_allowed_cidrs = [
"0.0.0.0/0",
]
```

main.tf

```
ingress {
from_port = 22
to_port = 22
protocol = "tcp"
cidr_blocks = var.ssh_allowed_cidrs
}

ingress {
from_port = 80
to_port = 80
protocol = "tcp"
cidr_blocks = var.http_allowed_cidrs
}

ingress {
from_port = 443
to_port = 443
protocol = "tcp"
cidr_blocks = var.https_allowed_cidrs
}
```

## Redis + Celery worker

Document-processing flow

```
POST /documents/{id}/process
        ↓
document.status = queued
        ↓
Celery task is created
        ↓
HTTP 202 returned immediately
        ↓
worker receives documents.process
        ↓
document.status = processing
        ↓
extract → chunk → embed
        ↓
document.status = indexed
```

On failure:

```
document.status = failed
document.error = actual error message
```

Workflow flow:

```
POST /workflows/{id}/run
        ↓
workflow_run.status = pending
        ↓
Celery task queued
        ↓
HTTP 202 with run_id
        ↓
frontend stays on workflow page
        ↓
frontend polls workflow run status
        ↓
pending → running → completed
        ↓
redirect to execution page only after completed
```

On failure:

```
status = failed
error = actual error
```

## HTTPS / custom domain name deploy flow:

```
Cloudflare DNS / Namecheap / Gandi / Porkbun
        ↓
DNS
        ↓
Elastic IP
        ↓
Ubuntu Frontend EC2 (Django + Nginx)
        │
        ├── backend.ai-platform.internal (FastAPI)
        │
        └── ollama.ai-platform.internal (Ollama)
        ↓
Nginx
        ↓
Gunicorn
        ↓
Django
```

Then run:

```
sudo apt update
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d ai-automation-platform.dev -d www.ai-automation-platform.dev
```

Then configure:

```
Registrar: Cloudflare Registrar
DNS: Cloudflare
Server: EC2
Elastic IP: Yes
Web server: Nginx
HTTPS: Let's Encrypt
```
