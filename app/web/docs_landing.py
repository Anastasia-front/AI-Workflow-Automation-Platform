from html import escape
from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

FRONTEND_URL = "https://ai-automation-platform.com"
GITHUB_REPOSITORY_URL = "https://github.com/Anastasia-front/ai-platform-backend"
FAVICON_SVG_PATH = Path(__file__).resolve().parents[2] / "static" / "favicon.svg"

router = APIRouter()


def _external_link_attrs(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return ' target="_blank" rel="noopener noreferrer"'
    return ""


def _resource_card(title: str, description: str, href: str, label: str) -> str:
    safe_href = escape(href, quote=True)
    attrs = _external_link_attrs(href)
    return f"""
        <article class="card">
          <div>
            <h2>{escape(title)}</h2>
            <p>{escape(description)}</p>
          </div>
          <a class="card-link" href="{safe_href}"{attrs}>{escape(label)}</a>
        </article>
    """


def _docs_sections() -> str:
    return """
      <section class="content-section" aria-labelledby="overview-title">
        <p id="eyebrow">brief info</p>
        <h2 id="overview-title">Overview</h2>
        <p>
          The backend is a FastAPI service for an AI automation platform. It exposes authenticated
          APIs for users, projects, chats, messages, documents, document retrieval, provider
          configuration, workflows, workflow steps, workflow runs, agent runs, embeddings and health.
        </p>
        <div class="facts-grid">
          <article><strong>Chat and agents</strong><span>Chats can use plain AI responses, project RAG, or agentic modes selected from registered agents.</span></article>
          <article><strong>Documents and RAG</strong><span>Uploads are extracted, chunked, embedded, searched by project, and returned with source metadata for citations.</span></article>
          <article><strong>Workflow execution</strong><span>Workflows contain ordered or DAG-style steps, conditions, step runs, run events, retries, cancellation, resume and streaming execution.</span></article>
          <article><strong>AI providers</strong><span>Chat providers implemented in source are Ollama, Gemini, OpenRouter and Groq. Embedding providers are Ollama, Gemini and OpenRouter.</span></article>
        </div>
      </section>

      <section class="content-section" aria-labelledby="architecture-title">
        <p id="eyebrow">main flows</p>
        <h2 id="architecture-title">Architecture</h2>
        <div class="diagram-grid">
          <article>
            <h4>Public request path</h4>
            <pre>Client
-> Cloudflare / DNS
-> Nginx :443 for docs.ai-automation-platform.com
-> FastAPI on 127.0.0.1:8000
-> router / service / database or provider</pre>
          </article>
          <article>
            <h4>Synchronous application path</h4>
            <pre>FastAPI route
-> dependency ownership check
-> service layer
-> repository / SQLAlchemy
-> PostgreSQL or AI provider
-> JSON / SSE response</pre>
          </article>
          <article>
            <h4>Asynchronous execution path</h4>
            <pre>FastAPI route
-> persisted queued record
-> Celery task
-> Redis broker
-> worker
-> document / embedding / workflow service
-> PostgreSQL status and result</pre>
          </article>
          <article>
            <h4>Operations and configuration path</h4>
            <pre>Deployment / runtime
-> environment variables / AWS SSM parameters
-> provider configuration seed and database load
-> Redis + PostgreSQL + storage service
-> FastAPI lifespan recovery
-> Nginx docs/static assets
-> health, OpenAPI and docs landing page</pre>
          </article>
        </div>
        <ul class="compact-list">
          <li><strong>Data persistence:</strong> PostgreSQL through async SQLAlchemy; Alembic records schema changes. The Terraform RDS module provisions PostgreSQL 15, and Docker Compose uses pgvector PostgreSQL 17 for local containers.</li>
          <li><strong>Background processing:</strong> Redis is configured as the Celery broker. The API does not rely on a Celery result backend; task state is persisted in PostgreSQL columns.</li>
          <li><strong>Secrets:</strong> deployment retrieves environment values and origin TLS material from AWS SSM Parameter Store.</li>
          <li><strong>Ports:</strong> production deployment maps the FastAPI container to <code>127.0.0.1:8000</code>; Nginx exposes public 443 for documentation and HTTP 80 for configured internal/public paths.</li>
          <li><strong>TLS:</strong> the Nginx docs virtual host uses an origin certificate and redirects the docs hostname from HTTP to HTTPS.</li>
        </ul>
      </section>

      <section class="content-section" aria-labelledby="api-title">
        <p id="eyebrow">visual summary</p>
        <h2 id="api-title">API Inventory</h2>
        <p>
          Route groups are included
          directly at paths such as <code>/auth</code>, <code>/projects</code>, <code>/chats</code>,
          <code>/documents</code>, <code>/runs</code>, <code>/providers</code> and <code>/health</code>.
        </p>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Group</th><th>Operations</th><th>Methods</th><th>Authentication</th><th>Purpose</th></tr></thead>
            <tbody>
              <tr><td>Auth</td><td>5</td><td>GET, POST</td><td>Mixed</td><td>Register, login, Google login, refresh and current user lookup.</td></tr>
              <tr><td>Projects</td><td>6</td><td>DELETE, GET, PATCH, POST</td><td>Bearer token</td><td>Project CRUD and project-scoped retrieval.</td></tr>
              <tr><td>Chats</td><td>5</td><td>DELETE, GET, PATCH, POST</td><td>Bearer token</td><td>Project chats and chat metadata.</td></tr>
              <tr><td>Messages</td><td>4</td><td>GET, POST</td><td>Bearer token</td><td>Chat messages, streamed responses and regeneration.</td></tr>
              <tr><td>Documents</td><td>8</td><td>DELETE, GET, POST</td><td>Bearer token</td><td>Upload, process, cancel, retry, list, inspect chunks and delete documents.</td></tr>
              <tr><td>Embeddings</td><td>9</td><td>GET, POST</td><td>Bearer token</td><td>Document rebuild and project embedding sync lifecycle.</td></tr>
              <tr><td>Workflows</td><td>7</td><td>DELETE, GET, PATCH, POST</td><td>Bearer token</td><td>Workflow CRUD, queued runs and streamed runs.</td></tr>
              <tr><td>Workflow Steps</td><td>4</td><td>DELETE, GET, POST</td><td>Bearer token</td><td>Create, list, fetch and delete workflow steps.</td></tr>
              <tr><td>Workflow Runs</td><td>9</td><td>DELETE, GET, POST</td><td>Bearer token</td><td>List, inspect, resume, retry, cancel, delete, read execution events and stream live progress.</td></tr>
              <tr><td>Agent Runs</td><td>2</td><td>GET, POST</td><td>Bearer token</td><td>Create and fetch agent runs attached to workflows.</td></tr>
              <tr><td>Providers</td><td>6</td><td>GET, PATCH</td><td>Bearer token</td><td>List providers, update defaults and check provider health.</td></tr>
              <tr><td>Health</td><td>1</td><td>GET</td><td>Public</td><td>Service health check.</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="content-section" aria-labelledby="limits-title">
        <p id="eyebrow">small restrictions</p>
        <h2 id="limits-title">Rate Limits and Operational Limits</h2>
        <h3>Enforced limits</h3>
        <ul class="compact-list">
          <li>Document upload accepts one file per HTTP request and enforces a 10 MB backend file-size limit.</li>
          <li>Allowed upload extensions are PDF, DOCX, TXT, Markdown, CSV, JSON, LOG, YAML and YML, with matching MIME validation.</li>
          <li>Workflow run listing enforces <code>page_size</code> between 1 and 100.</li>
          <li>Provider HTTP calls use a 60 second default timeout and 2 configured retries, plus circuit-breaker settings.</li>
          <li>Nginx sets <code>client_max_body_size 100m</code>, which is higher than the backend document limit.</li>
        </ul>
          <h3>Infrastructure or provider-dependent limits</h3>
        <p>Effective AI throughput and context limits depend on the configured provider, model, network and worker capacity.</p>
      </section>

      <section class="content-section" aria-labelledby="evolution-title">
        <p id="eyebrow">project evolution</p>
        <h2 id="evolution-title">Changelog</h2>
        <p>The entries below are repository-history milestones, not official product versions.</p>
        <ol class="timeline">
          <li><strong>2026-05-20:</strong> initial routes and schemas entered the repository.</li>
          <li><strong>2026-05-21 to 2026-05-23:</strong> database setup, users, JWT authentication, protected routes and user-owned projects were added.</li>
          <li><strong>2026-05-24 to 2026-06-05:</strong> chat, agents, workflows, workflow steps, DAG execution, streaming events and persistent workflow run state were introduced.</li>
          <li><strong>2026-06-18 to 2026-06-25:</strong> document processing, chunking, embeddings, retrieval and RAG citations were added.</li>
          <li><strong>2026-06-28 to 2026-07-07:</strong> storage services, multiple chat and embedding providers, provider configuration and Google login were added.</li>
          <li><strong>2026-07-10 to 2026-07-14:</strong> Celery tracking, cancellation statuses, embedding metadata, message provider metadata and workflow soft delete were added.</li>
          <li><strong>2026-07-22 to 2026-07-23:</strong> Nginx-backed documentation hosting, deployment pipeline updates, the custom docs landing page and tests were added.</li>
        </ol>
      </section>
    """


def render_docs_landing(
    *,
    api_title: str,
    api_version: str,
    api_description: str | None,
) -> str:
    description = api_description or (
        "API documentation, architecture overview, operational limits and service resources."
    )
    cards = "\n".join(
        [
            _resource_card(
                "Swagger UI",
                "Interactive API explorer",
                "/swagger",
                "Open Swagger",
            ),
            _resource_card("ReDoc", "Structured API reference", "/redoc", "Open ReDoc"),
            _resource_card(
                "OpenAPI Specification",
                "Raw machine-readable schema",
                "/openapi.json",
                "View JSON",
            ),
            _resource_card(
                "API Status",
                "Service health endpoint",
                "/health",
                "Check status",
            ),
            _resource_card(
                "Web Application",
                "Open the production frontend",
                FRONTEND_URL,
                "Open app",
            ),
            _resource_card(
                "GitHub Repository",
                "Open the source repository",
                GITHUB_REPOSITORY_URL,
                "Open source",
            ),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2">
    <title>{escape(api_title)} API Documentation</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f7f8fb;
        --panel: #ffffff;
        --text: #18202f;
        --muted: #5e6878;
        --line: #d9dee8;
        --accent: #0ea5e9;
        --accent-strong: #0ea5e9;
        --eyebrow:#ea7130;
        --shadow: 0 18px 45px rgba(24, 32, 47, 0.08);
      }}

      * {{ box-sizing: border-box; }}

      body {{
        margin: 0;
        min-height: 100vh;
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--text);
        background:
          linear-gradient(180deg, #eef3fb 0, rgba(238, 243, 251, 0) 340px),
          var(--bg);
      }}

      main {{
        width: min(1120px, calc(100% - 32px));
        margin: 0 auto;
        padding: 56px 0;
      }}

      .intro {{
        display: grid;
        gap: 18px;
        margin-bottom: 34px;
      }}

      #eyebrow {{
        margin: 0;
        color: var(--eyebrow);
        font-size: 0.84rem;
        font-weight: 700;
        text-transform: uppercase;
      }}

      h1 {{
        margin: 0;
        font-size: clamp(2.25rem, 7vw, 4.75rem);
        line-height: 0.98;
        letter-spacing: 0;
      }}

      .subtitle {{
        margin: 0;
        color: var(--muted);
        font-size: 1.16rem;
        line-height: 1.6;
      }}

      .metadata {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin: 0;
        padding: 0;
        list-style: none;
      }}

      .metadata li {{
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 8px 12px;
        background: rgba(255, 255, 255, 0.72);
        color: var(--muted);
        font-size: 0.92rem;
      }}

      .metadata-row {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 16px;
        margin: 8px 0 0;
      }}

      .section-nav {{
        position: relative;
        flex: 0 0 auto;
      }}

      .section-nav summary {{
        min-height: 38px;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        border: 1px solid var(--line);
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.72);
        color: var(--muted);
        font-size: 0.92rem;
        cursor: pointer;
        list-style: none;
      }}

      .section-nav summary::-webkit-details-marker {{
        display: none;
      }}

      .section-nav summary::after {{
        content: "";
        width: 7px;
        height: 7px;
        border-right: 2px solid currentColor;
        border-bottom: 2px solid currentColor;
        transform: translateY(-2px) rotate(45deg);
      }}

      .section-nav[open] summary::after {{
        transform: translateY(2px) rotate(225deg);
      }}

      .section-nav summary:focus-visible {{
        outline: 3px solid rgba(14, 165, 233, 0.35);
        outline-offset: 3px;
      }}

      .section-nav-menu {{
        position: absolute;
        right: 0;
        z-index: 2;
        width: 240px;
        margin-top: 8px;
        padding: 8px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--panel);
        box-shadow: var(--shadow);
      }}

      .section-nav-menu a {{
        display: block;
        padding: 10px 12px;
        border-radius: 6px;
        color: var(--text);
        font-weight: 700;
        text-decoration: none;
      }}

      .section-nav-menu a:hover,
      .section-nav-menu a:focus-visible {{
        background: #eef7fd;
        color: var(--accent);
      }}

      .grid {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 16px;
        margin-bottom: 34px;
      }}

      .card {{
        min-height: 210px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        gap: 28px;
        padding: 24px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--panel);
        box-shadow: var(--shadow);
      }}

      h2 {{
        margin: 0 0 10px;
        font-size: 1.18rem;
        letter-spacing: 0;
      }}

      .card p {{
        margin: 0;
        color: var(--muted);
        line-height: 1.55;
      }}

      .card-link {{
        width: fit-content;
        max-width: 100%;
        display: inline-flex;
        align-items: center;
        min-height: 42px;
        padding: 0 16px;
        border-radius: 6px;
        background: var(--accent);
        color: #ffffff;
        font-weight: 700;
        text-decoration: none;
      }}

      .card-link:hover,
      .card-link:focus-visible {{
        background: var(--accent-strong);
      }}

      .card-link:focus-visible {{
        outline: 3px solid rgba(14, 165, 233, 0.35);
        outline-offset: 3px;
      }}

      .content-section {{
        margin-top: 18px;
        padding: 28px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--panel);
        box-shadow: var(--shadow);
      }}

      .content-section p,
      .content-section li {{
        color: var(--muted);
        line-height: 1.6;
      }}

      .content-section h2 {{
        font-size: 1.55rem;
      }}

      .content-section h3 {{
        margin: 22px 0 8px;
        font-size: 1rem;
      }}

      .content-section h4 {{
        margin: 0 0 12px;
        font-size: 1.25rem;
      }}

      .facts-grid,
      .diagram-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
        margin-top: 18px;
      }}

      .facts-grid article,
      .diagram-grid article {{
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 16px;
        background: #fbfcff;
      }}

      .facts-grid strong {{
        display: block;
        margin-bottom: 6px;
      }}

      .facts-grid span {{
        color: var(--muted);
        line-height: 1.55;
      }}

      pre {{
        overflow-x: auto;
        margin: 0;
        color: #334155;
        font: 0.9rem/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      }}

      code {{
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        color: #334155;
      }}

      .compact-list {{
        margin: 14px 0 0;
        padding-left: 22px;
      }}

      .note {{
        margin-bottom: 0;
      }}

      .table-wrap {{
        overflow-x: auto;
        margin-top: 16px;
      }}

      table {{
        width: 100%;
        min-width: 860px;
        border-collapse: collapse;
      }}

      th,
      td {{
        padding: 12px;
        border-bottom: 1px solid var(--line);
        text-align: left;
        vertical-align: top;
      }}

      th {{
        color: var(--text);
        font-size: 0.84rem;
        text-transform: uppercase;
      }}

      td {{
        color: var(--muted);
      }}

      .timeline {{
        margin: 14px 0 0;
        padding-left: 22px;
      }}

      @media (max-width: 860px) {{
        main {{ padding: 40px 0; }}
        .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      }}

      @media (max-width: 620px) {{
        main {{ width: min(100% - 24px, 1120px); }}
        .metadata-row {{ display: grid; }}
        .section-nav {{ width: 100%; }}
        .section-nav summary {{ width: 100%; justify-content: space-between; }}
        .section-nav-menu {{ left: 0; right: auto; width: 100%; }}
        .grid {{ grid-template-columns: 1fr; }}
        .card {{ min-height: 180px; padding: 20px; }}
        .facts-grid,
        .diagram-grid {{ grid-template-columns: 1fr; }}
        .content-section {{ padding: 20px; }}
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="intro" aria-labelledby="page-title">
        <p id="eyebrow">documentation</p>
        <h1 id="page-title">{escape(api_title)} API</h1>
        <p class="subtitle">{escape(description)}</p>
        <div class="metadata-row">
          <ul class="metadata" aria-label="API metadata">
            <li>Framework: {escape('FastAPI')}</li>
            <li>Version: {escape(api_version)}</li>
          </ul>
          <details class="section-nav">
            <summary>Sections</summary>
            <nav class="section-nav-menu" aria-label="Page sections">
              <a href="#overview-title">Overview</a>
              <a href="#architecture-title">Architecture</a>
              <a href="#api-title">API Inventory</a>
              <a href="#limits-title">Rate Limits and Operational Limits</a>
              <a href="#evolution-title">Changelog</a>
            </nav>
          </details>
        </div>
      </section>
      <section class="grid" aria-label="Documentation resources">
        {cards}
      </section>
      {_docs_sections()}
    </main>
  </body>
</html>"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def docs_landing(request: Request) -> HTMLResponse:
    return HTMLResponse(
        render_docs_landing(
            api_title=request.app.title,
            api_version=request.app.version,
            api_description=request.app.description,
        )
    )


@router.get("/docs", include_in_schema=False)
async def legacy_docs_redirect() -> RedirectResponse:
    return RedirectResponse(url="/swagger", status_code=status.HTTP_302_FOUND)


@router.get("/favicon.svg", include_in_schema=False)
async def favicon_svg() -> FileResponse:
    return FileResponse(
        FAVICON_SVG_PATH,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )
