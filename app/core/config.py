from pydantic_settings import BaseSettings, SettingsConfigDict

from app.enums import ChatProvider, EmbeddingProvider


class Settings(BaseSettings):
    DATABASE_URL: str

    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    JWT_SECRET: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 43200
    GOOGLE_CLIENT_ID: str = ""

    CHAT_PROVIDER: ChatProvider = ChatProvider.OLLAMA
    EMBEDDING_PROVIDER: EmbeddingProvider = EmbeddingProvider.OLLAMA

    CHAT_BASE_URL: str = "http://ollama.ai-platform.internal:11434"
    EMBEDDING_BASE_URL: str = "http://ollama.ai-platform.internal:11434"

    CHAT_API_KEY: str = ""
    EMBEDDING_API_KEY: str = ""
    PROVIDER_CONFIG_ENCRYPTION_KEY: str = ""

    CHAT_MODEL: str = "gemma2:2b"
    CHAT_FALLBACK_MODEL: str = "llama3.2:3b"
    CHAT_PROVIDER_CHAIN: str = "gemini,groq,openrouter,ollama"

    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 768
    EMBEDDING_PROVIDER_CHAIN: str = "openrouter,gemini,ollama"

    PROVIDER_MAX_RETRIES: int = 2
    PROVIDER_RETRY_BASE_DELAY_SECONDS: float = 1
    PROVIDER_REQUEST_TIMEOUT_SECONDS: float = 60
    PROVIDER_FAILURE_THRESHOLD: int = 3
    PROVIDER_COOLDOWN_SECONDS: int = 60

    PROVIDER_RATE_LIMIT_ENABLED: bool = False
    PROVIDER_RATE_LIMIT_RPM: int = 60

    WORKSPACE_TOOL_MAX_STEPS: int = 4
    WORKSPACE_TOOL_ARGUMENT_MAX_RETRIES: int = 2

    STORAGE_PROVIDER: str
    AWS_S3_BUCKET: str = "ai-platform-uploads"
    AWS_REGION: str = "eu-central-1"

    CELERY_BROKER_URL: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
