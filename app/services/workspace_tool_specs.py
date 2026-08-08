"""LLM-facing tool schemas for `WorkspaceToolRegistry`.

Each spec pairs a Pydantic argument model (the JSON schema handed to the
model, and what its tool-call arguments get validated against) with an
`invoke` function that resolves any ids into ORM objects and calls the
matching `WorkspaceToolRegistry` method. Session-scoped values (project_id,
user_id) are injected from `context`, never taken from model output, so the
model can't address another project's data.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.services.ai.tool_types import ToolSchema
from app.services.workspace_tools import ToolResult, WorkspaceToolRegistry


class ListProjectDocumentsArgs(BaseModel):
    pass


class GetEmbeddingConfigurationArgs(BaseModel):
    pass


class CheckEmbeddingRebuildNeedArgs(BaseModel):
    pass


class UpdateFilesForEmbeddingModelArgs(BaseModel):
    pass


class SyncProjectEmbeddingsArgs(BaseModel):
    pass


class ProcessDocumentArgs(BaseModel):
    document_id: int = Field(description="Id of the document to queue for processing")


class RebuildDocumentEmbeddingsArgs(BaseModel):
    document_id: int = Field(description="Id of the document to rebuild embeddings for")


class ListWorkflowsArgs(BaseModel):
    pass


class CreateWorkflowArgs(BaseModel):
    name: str = Field(description="Human-readable name for the new workflow")


class CreateWorkflowStepArgs(BaseModel):
    workflow_id: int = Field(description="Id of the workflow this step belongs to")
    name: str = Field(description="Short step name")
    prompt_template: str = Field(
        description=(
            "Prompt sent to the model when this step runs. Use {{input}} for the "
            "document/workflow input and {{dependency_outputs}} for prior step outputs."
        )
    )
    step_order: int = Field(default=1, description="Execution order, starting at 1")
    depends_on: list[int] = Field(
        default_factory=list,
        description="Ids of steps (by step_order value used in this same tool call) this step depends on",
    )


class RunWorkflowArgs(BaseModel):
    workflow_id: int = Field(description="Id of the workflow to run")
    document_id: int = Field(description="Id of the indexed document to run the workflow against")


class ListWorkflowRunsArgs(BaseModel):
    workflow_id: int = Field(description="Id of the workflow whose runs to list")


class ToolNotFoundError(Exception):
    def __init__(self, tool_id: int, tool_kind: str) -> None:
        super().__init__(f"No {tool_kind} found with id {tool_id}")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    read_only: bool
    invoke: Callable[[WorkspaceToolRegistry, AsyncSession, dict, BaseModel], Awaitable[ToolResult]]

    def to_schema(self) -> ToolSchema:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return ToolSchema(name=self.name, description=self.description, parameters=schema)


async def _list_project_documents(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: ListProjectDocumentsArgs
) -> ToolResult:
    return await registry.list_project_documents(db, project_id=context["project_id"])


async def _get_embedding_configuration(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: GetEmbeddingConfigurationArgs
) -> ToolResult:
    return await registry.get_embedding_configuration()


async def _check_embedding_rebuild_need(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: CheckEmbeddingRebuildNeedArgs
) -> ToolResult:
    return await registry.check_embedding_rebuild_need(db, project_id=context["project_id"])


async def _update_files_for_embedding_model(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: UpdateFilesForEmbeddingModelArgs
) -> ToolResult:
    return await registry.update_files_for_embedding_model(db, project_id=context["project_id"])


async def _sync_project_embeddings(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: SyncProjectEmbeddingsArgs
) -> ToolResult:
    project = await db.get(Project, context["project_id"])
    return await registry.sync_project_embeddings(db, project=project)


async def _process_document(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: ProcessDocumentArgs
) -> ToolResult:
    document = await registry.documents.get_by_id(db, args.document_id)
    if document is None or document.project_id != context["project_id"]:
        raise ToolNotFoundError(args.document_id, "document")
    return await registry.process_document(db, document=document)


async def _rebuild_document_embeddings(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: RebuildDocumentEmbeddingsArgs
) -> ToolResult:
    document = await registry.documents.get_by_id(db, args.document_id)
    if document is None or document.project_id != context["project_id"]:
        raise ToolNotFoundError(args.document_id, "document")
    return await registry.rebuild_document_embeddings(db, document=document)


async def _list_workflows(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: ListWorkflowsArgs
) -> ToolResult:
    return await registry.list_workflows(db, project_id=context["project_id"])


async def _create_workflow(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: CreateWorkflowArgs
) -> ToolResult:
    return await registry.create_workflow(db, project_id=context["project_id"], name=args.name)


async def _create_workflow_step(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: CreateWorkflowStepArgs
) -> ToolResult:
    return await registry.create_workflow_step(
        db,
        workflow_id=args.workflow_id,
        name=args.name,
        prompt_template=args.prompt_template,
        step_order=args.step_order,
        depends_on=args.depends_on,
    )


async def _run_workflow(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: RunWorkflowArgs
) -> ToolResult:
    document = await registry.documents.get_by_id(db, args.document_id)
    if document is None or document.project_id != context["project_id"]:
        raise ToolNotFoundError(args.document_id, "document")
    if not (document.text or "").strip():
        return ToolResult(
            tool="run_workflow",
            status="failed",
            data={"document_id": document.id},
            message="Document has no extracted text yet; process it before running a workflow against it.",
        )
    user_input = f"Document filename: {document.filename}\n\n{document.text}"
    return await registry.run_workflow(db, workflow_id=args.workflow_id, user_input=user_input)


async def _list_workflow_runs(
    registry: WorkspaceToolRegistry, db: AsyncSession, context: dict, args: ListWorkflowRunsArgs
) -> ToolResult:
    return await registry.list_workflow_runs(
        db, workflow_id=args.workflow_id, user_id=context["user_id"]
    )


WORKSPACE_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        "list_project_documents",
        "List documents uploaded to the current project, with their processing and embedding status.",
        ListProjectDocumentsArgs,
        True,
        _list_project_documents,
    ),
    ToolSpec(
        "get_embedding_configuration",
        "Read the embedding provider/model/dimensions currently active for the workspace.",
        GetEmbeddingConfigurationArgs,
        True,
        _get_embedding_configuration,
    ),
    ToolSpec(
        "check_embedding_rebuild_need",
        "Classify each project document's embeddings as current, rebuild-required, missing, failed, or not ready.",
        CheckEmbeddingRebuildNeedArgs,
        True,
        _check_embedding_rebuild_need,
    ),
    ToolSpec(
        "update_files_for_embedding_model",
        "Queue re-embedding for exactly the documents whose embeddings are stale, missing, or failed; skips documents already current.",
        UpdateFilesForEmbeddingModelArgs,
        False,
        _update_files_for_embedding_model,
    ),
    ToolSpec(
        "sync_project_embeddings",
        "Queue a full project-wide embedding sync job.",
        SyncProjectEmbeddingsArgs,
        False,
        _sync_project_embeddings,
    ),
    ToolSpec(
        "process_document",
        "Queue text extraction/processing for a single document by id.",
        ProcessDocumentArgs,
        False,
        _process_document,
    ),
    ToolSpec(
        "rebuild_document_embeddings",
        "Queue an embedding rebuild for a single document by id.",
        RebuildDocumentEmbeddingsArgs,
        False,
        _rebuild_document_embeddings,
    ),
    ToolSpec(
        "list_workflows",
        "List workflows defined in the current project.",
        ListWorkflowsArgs,
        True,
        _list_workflows,
    ),
    ToolSpec(
        "create_workflow",
        "Create a new, empty workflow in the current project. Use create_workflow_step afterward to add steps.",
        CreateWorkflowArgs,
        False,
        _create_workflow,
    ),
    ToolSpec(
        "create_workflow_step",
        "Add a step to an existing workflow.",
        CreateWorkflowStepArgs,
        False,
        _create_workflow_step,
    ),
    ToolSpec(
        "run_workflow",
        "Queue a workflow run against a project document's extracted text.",
        RunWorkflowArgs,
        False,
        _run_workflow,
    ),
    ToolSpec(
        "list_workflow_runs",
        "List recent runs for a workflow, with status and errors.",
        ListWorkflowRunsArgs,
        True,
        _list_workflow_runs,
    ),
]
