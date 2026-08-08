import re
from datetime import timedelta

from app.enums import WorkflowRunStatus

CHAT_KIND = "chat"
EMBEDDING_KIND = "embedding"

TRANSIENT_EMBEDDING_STATUS_CODES = {429, 500, 502, 503, 504}

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".log",
    ".yaml",
    ".yml",
}

ALLOWED_CONTENT_TYPES = {
    "application/octet-stream",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "text/csv",
    "application/json",
    "text/json",
    "application/x-yaml",
    "text/yaml",
    "text/x-yaml",
    "text/x-log",
}

SIMILARITY_THRESHOLD = 0.55

# Tighter than SIMILARITY_THRESHOLD -- used to decide which retrieved chunks
# are confident enough to surface as user-facing "Sources", as opposed to
# SIMILARITY_THRESHOLD which decides what's loosely relevant enough to feed
# the LLM as context. Cosine distance: lower is a closer match.
SOURCE_RELEVANCE_THRESHOLD = 0.35

# In a small/homogeneous document corpus, an absolute distance threshold
# alone isn't enough -- nearly every document ends up with at least one
# chunk that's "close enough" to any query. Documents are ranked by their
# single best (closest) chunk match, and only the top MAX_SOURCES are kept,
# so citations stay meaningful instead of listing most of the project.
MAX_SOURCES = 3

PASSWORD_RULE_MESSAGE = (
    "Password must be at least 6 characters and include an uppercase letter, "
    "a number, and a special character."
)

DOCUMENT_REFERENCE_TERMS = (
    "uploaded",
    "document",
    "documents",
    "file",
    "files",
    "contract",
    "contracts",
    "cv",
    "cvs",
    "candidate",
    "candidates",
    "job",
    "job description",
    "resume",
    "resumes",
    "invoice",
    "invoices",
    "gmail_thread",
    "requirements",
)

DOCUMENT_LIST_TERMS = (
    "list",
    "show",
    "available",
    "what files",
    "which files",
    "document names",
    "file names",
    "filenames",
)

DELEGATION_FAILURE_PHRASES = (
    "you need to",
    "you'll need to",
    "you must",
    "please provide",
    "please paste",
    "please describe",
    "provide me with",
    "tell me about",
    "send me",
    "step 1: you",
    "once you provide",
)

SENSITIVE_FIELD_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|authorization|"
    r"client[_-]?secret|secret|password|passwd|pwd|credential|private[_-]?key)",
    flags=re.IGNORECASE,
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<prefix>\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"authorization|client[_-]?secret|secret|password|passwd|pwd|credential|"
    r"private[_-]?key)\b\s*[:=]\s*)(?P<quote>['\"]?)(?P<value>[^'\"\s,&}]+)",
    flags=re.IGNORECASE,
)
ENV_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<prefix>\b[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|"
    r"CREDENTIAL|PRIVATE_KEY)\b\s*[:=]\s*)(?P<quote>['\"]?)(?P<value>[^'\"\s,&}]+)"
)
QUERY_SECRET_RE = re.compile(
    r"(?P<prefix>[?&](?:key|api_key|api-key|token|access_token|auth|signature|"
    r"client_secret)=)(?P<value>[^&\s'\"}]+)",
    flags=re.IGNORECASE,
)
GOOGLE_API_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20

# SSE polling interval (seconds) for GET /runs/{run_id}/stream's DB-tail loop.
STREAM_POLL_INTERVAL_SECONDS = 1

TERMINAL_RUN_STATUSES = {
    WorkflowRunStatus.COMPLETED,
    WorkflowRunStatus.FAILED,
    WorkflowRunStatus.CANCELED,
}

# PARTIAL_OUTPUT_FLUSH_CHARS: chars buffered before a partial_output event is
# flushed. Steps run concurrently via asyncio.gather, and AsyncSession isn't
# safe for concurrent writes, so every emit (including partials) goes through
# a single lock -- this keeps write volume reasonable per step.
# Chars buffered before a workflow step's partial_output event is flushed.
PARTIAL_OUTPUT_FLUSH_CHARS = 40

MAX_RESOURCE_NAME_LENGTH = 255

# Threshold before a PENDING/RUNNING workflow run is considered abandoned
# (e.g. worker crashed mid-execution) and eligible for recovery.
# How long a run may sit in PENDING/RUNNING with no status update before it
# is considered abandoned (worker crashed/restarted) rather than still being
# actively worked on by a live Celery worker.
STALE_AFTER = timedelta(minutes=10)

FRONTEND_URL = "https://ai-automation-platform.com"
GITHUB_REPOSITORY_URL = "https://github.com/Anastasia-front/ai-platform-backend"
API_URL = "https://api.ai-automation-platform.com"
DOCS_URL = "https://docs.ai-automation-platform.com"
POSTMAN_DOCS_URL = "https://postman.ai-automation-platform.com"