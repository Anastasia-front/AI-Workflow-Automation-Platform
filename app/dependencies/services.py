
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db, settings
from app.dependencies.auth import get_current_user
from app.dependencies.repositories import (
    get_agent_run_repository,
    get_chat_repository,
    get_document_chunk_repository,
    get_document_repository,
    get_message_repository,
    get_project_repository,
    get_retrieval_repository,
    get_workflow_repository,
    get_workflow_run_repository,
    get_workflow_step_repository,
)
from app.models import User
from app.prompts import RAGPromptBuilder
from app.repositories import (
    AgentRunRepository,
    ChatRepository,
    DocumentChunkRepository,
    DocumentRepository,
    MessageRepository,
    ProjectRepository,
    RetrievalRepository,
    WorkflowRepository,
    WorkflowRunRepository,
    WorkflowStepRepository,
)
from app.services import (
    AgentRunUpdateService,
    AgentService,
    AIService,
    BackgroundJobService,
    ChatService,
    ChatUpdateService,
    DocumentService,
    EmbeddingJobService,
    EmbeddingManagementService,
    EmbeddingService,
    HealthService,
    ProjectUpdateService,
    RAGService,
    RetrievalService,
    WorkflowService,
    WorkflowStepUpdateService,
    WorkflowUpdateService,
    WorkspaceToolRegistry,
)
from app.services.provider_config import ProviderConfigService
from app.services.storage import (
    LocalStorageService,
    S3StorageService,
    StorageService,
)
from app.services.workflow import DAGEngine, EventBus


def get_workflow_service():
    events = EventBus()

    return WorkflowService(
        runs=WorkflowRunRepository(),
        events=events,
        engine=DAGEngine(events=events),
    )


def get_project_update_service(
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> ProjectUpdateService:
    return ProjectUpdateService(projects=projects)


def get_chat_update_service(
    chats: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> ChatUpdateService:
    return ChatUpdateService(chats=chats)


def get_workflow_update_service(
    workflows: Annotated[WorkflowRepository, Depends(get_workflow_repository)],
) -> WorkflowUpdateService:
    return WorkflowUpdateService(workflows=workflows)


def get_workflow_step_update_service(
    steps: Annotated[WorkflowStepRepository, Depends(get_workflow_step_repository)],
) -> WorkflowStepUpdateService:
    return WorkflowStepUpdateService(steps=steps)


def get_agent_run_update_service(
    agent_runs: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
) -> AgentRunUpdateService:
    return AgentRunUpdateService(agent_runs=agent_runs)


def get_background_job_service() -> BackgroundJobService:
    return BackgroundJobService()


def get_health_service() -> HealthService:
    return HealthService()


async def get_embedding_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> EmbeddingService:
    # Provider choices live in the database, scoped to the requesting user
    # (falling back to the system default), and must be refreshed before
    # constructing services that route requests to external model providers.
    # A request-scoped ProviderConfigService instance is used (rather than
    # the shared `provider_config` singleton) so concurrent requests from
    # different users can't clobber each other's loaded credentials.
    config = ProviderConfigService()
    await config.load_from_db(db, user.id)
    # Chain mode (not a single fixed provider): a user with no personal API
    # key falls through to the next provider in EMBEDDING_PROVIDER_CHAIN --
    # normally Ollama, which needs no key -- instead of failing outright.
    return EmbeddingService(chain=config.embedding_chain())


async def get_ai_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AIService:
    # See get_embedding_service: uses a request-scoped ProviderConfigService
    # instance loaded for this user, not the shared singleton.
    config = ProviderConfigService()
    await config.load_from_db(db, user.id)
    # Chain mode: a user with no personal API key for the default provider
    # (e.g. Gemini) falls through to the next entry in CHAT_PROVIDER_CHAIN --
    # normally Ollama, which needs no key -- instead of failing outright.
    return AIService(chain=config.chat_chain())


def get_retrieval_service(
    retrievals: Annotated[RetrievalRepository, Depends(get_retrieval_repository)],
    embeddings: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> RetrievalService:
    return RetrievalService(
        embedding_service=embeddings,
        retrieval_repository=retrievals,
    )


def get_rag_prompt_builder() -> RAGPromptBuilder:
    return RAGPromptBuilder()


def get_rag_service(
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
    ai: Annotated[AIService, Depends(get_ai_service)],
    prompts: Annotated[RAGPromptBuilder, Depends(get_rag_prompt_builder)],
) -> RAGService:
    return RAGService(
        retrieval_service=retrieval,
        ai_service=ai,
        prompt_builder=prompts,
    )


def get_workspace_tool_registry(
    documents: Annotated[DocumentRepository, Depends(get_document_repository)],
    workflows: Annotated[WorkflowRepository, Depends(get_workflow_repository)],
    workflow_steps: Annotated[WorkflowStepRepository, Depends(get_workflow_step_repository)],
    workflow_runs: Annotated[WorkflowRunRepository, Depends(get_workflow_run_repository)],
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
    jobs: Annotated[BackgroundJobService, Depends(get_background_job_service)],
) -> WorkspaceToolRegistry:
    return WorkspaceToolRegistry(
        documents=documents,
        workflows=workflows,
        workflow_steps=workflow_steps,
        workflow_runs=workflow_runs,
        workflow_service=workflow_service,
        embedding_service=embedding_service,
        jobs=jobs,
    )


def get_agent_service(
    ai: Annotated[AIService, Depends(get_ai_service)],
    rag: Annotated[RAGService, Depends(get_rag_service)],
    documents: Annotated[DocumentRepository, Depends(get_document_repository)],
    workspace_tools: Annotated[WorkspaceToolRegistry, Depends(get_workspace_tool_registry)],
    prompts: Annotated[RAGPromptBuilder, Depends(get_rag_prompt_builder)],
) -> AgentService:
    return AgentService(
        ai=ai,
        rag=rag,
        documents=documents,
        workspace_tools=workspace_tools,
        prompts=prompts,
    )


def get_chat_service(
    messages: Annotated[MessageRepository, Depends(get_message_repository)],
    rag: Annotated[RAGService, Depends(get_rag_service)],
    ai: Annotated[AIService, Depends(get_ai_service)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> ChatService:
    return ChatService(
        messages=messages,
        rag=rag,
        ai=ai,
        agent_service=agent_service,
    )


def get_storage_service() -> StorageService:
    if settings.STORAGE_PROVIDER == "s3":
        return S3StorageService(
            bucket_name=settings.AWS_S3_BUCKET,
            region=settings.AWS_REGION,
        )

    return LocalStorageService()


def get_document_service(
    storage: Annotated[StorageService, Depends(get_storage_service)],
    documents: Annotated[DocumentRepository, Depends(get_document_repository)],
    chunks: Annotated[DocumentChunkRepository, Depends(get_document_chunk_repository)],
    embeddings: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> DocumentService:
    return DocumentService(
        storage=storage,
        documents=documents,
        chunks=chunks,
        embeddings=embeddings,
    )


def get_embedding_management_service(
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> EmbeddingManagementService:
    return EmbeddingManagementService(
        embedding_service=embedding_service,
    )


def get_embedding_job_service() -> EmbeddingJobService:
    return EmbeddingJobService()
