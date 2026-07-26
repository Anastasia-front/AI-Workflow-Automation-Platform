from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.dependencies.agent_run import get_owned_agent_run
from app.dependencies.auth import get_current_user
from app.dependencies.chat import get_owned_chat
from app.dependencies.document import get_owned_document
from app.dependencies.project import get_owned_project
from app.dependencies.repositories import (
    get_chat_repository,
    get_document_chunk_repository,
    get_document_repository,
    get_message_repository,
    get_project_repository,
    get_workflow_event_repository,
    get_workflow_repository,
    get_workflow_run_repository,
    get_workflow_step_repository,
)
from app.dependencies.services import (
    get_agent_run_update_service,
    get_background_job_service,
    get_chat_service,
    get_chat_update_service,
    get_document_service,
    get_embedding_job_service,
    get_health_service,
    get_project_update_service,
    get_retrieval_service,
    get_workflow_service,
    get_workflow_step_update_service,
    get_workflow_update_service,
)
from app.dependencies.workflow import get_owned_workflow
from app.dependencies.workflow_run import get_owned_workflow_run
from app.dependencies.workflow_steps import get_owned_workflow_step
from app.models import (
    AgentRun,
    Chat,
    Document,
    Project,
    User,
    Workflow,
    WorkflowRun,
    WorkflowStep,
)
from app.repositories import (
    ChatRepository,
    DocumentChunkRepository,
    DocumentRepository,
    MessageRepository,
    ProjectRepository,
    WorkflowEventRepository,
    WorkflowRepository,
    WorkflowRunRepository,
    WorkflowStepRepository,
)
from app.services import (
    AgentRunUpdateService,
    BackgroundJobService,
    ChatService,
    ChatUpdateService,
    DocumentService,
    EmbeddingJobService,
    HealthService,
    ProjectUpdateService,
    RetrievalService,
    WorkflowService,
    WorkflowStepUpdateService,
    WorkflowUpdateService,
)

# These aliases are imported by route modules only. Provider functions stay in
# their domain modules so dependency resolution remains one-way and cycle-free.
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
OAuth2PasswordFormDep = Annotated[OAuth2PasswordRequestForm, Depends()]

OwnedAgentRunDep = Annotated[AgentRun, Depends(get_owned_agent_run)]
OwnedChatDep = Annotated[Chat, Depends(get_owned_chat)]
OwnedDocumentDep = Annotated[Document, Depends(get_owned_document)]
OwnedProjectDep = Annotated[Project, Depends(get_owned_project)]
OwnedWorkflowDep = Annotated[Workflow, Depends(get_owned_workflow)]
OwnedWorkflowRunDep = Annotated[WorkflowRun, Depends(get_owned_workflow_run)]
OwnedWorkflowStepDep = Annotated[WorkflowStep, Depends(get_owned_workflow_step)]

ChatRepositoryDep = Annotated[ChatRepository, Depends(get_chat_repository)]
DocumentChunkRepositoryDep = Annotated[
    DocumentChunkRepository,
    Depends(get_document_chunk_repository),
]
DocumentRepositoryDep = Annotated[DocumentRepository, Depends(get_document_repository)]
MessageRepositoryDep = Annotated[MessageRepository, Depends(get_message_repository)]
ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]
WorkflowEventRepositoryDep = Annotated[
    WorkflowEventRepository,
    Depends(get_workflow_event_repository),
]
WorkflowRepositoryDep = Annotated[WorkflowRepository, Depends(get_workflow_repository)]
WorkflowRunRepositoryDep = Annotated[
    WorkflowRunRepository,
    Depends(get_workflow_run_repository),
]
WorkflowStepRepositoryDep = Annotated[
    WorkflowStepRepository,
    Depends(get_workflow_step_repository),
]

AgentRunUpdateServiceDep = Annotated[
    AgentRunUpdateService,
    Depends(get_agent_run_update_service),
]
BackgroundJobServiceDep = Annotated[
    BackgroundJobService,
    Depends(get_background_job_service),
]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
ChatUpdateServiceDep = Annotated[ChatUpdateService, Depends(get_chat_update_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
EmbeddingJobServiceDep = Annotated[
    EmbeddingJobService,
    Depends(get_embedding_job_service),
]
HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
ProjectUpdateServiceDep = Annotated[
    ProjectUpdateService,
    Depends(get_project_update_service),
]
RetrievalServiceDep = Annotated[RetrievalService, Depends(get_retrieval_service)]
WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]
WorkflowStepUpdateServiceDep = Annotated[
    WorkflowStepUpdateService,
    Depends(get_workflow_step_update_service),
]
WorkflowUpdateServiceDep = Annotated[
    WorkflowUpdateService,
    Depends(get_workflow_update_service),
]
