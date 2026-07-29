import re

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