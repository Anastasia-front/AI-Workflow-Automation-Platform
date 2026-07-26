from fastapi import APIRouter, BackgroundTasks, status

from app.dependencies import (
    BackgroundJobServiceDep,
    DbSessionDep,
    EmbeddingJobServiceDep,
    OwnedDocumentDep,
    OwnedProjectDep,
)

router = APIRouter(tags=["Embeddings"])

# -------------------------------------------------
# RUN DOCUMENT EMBEDDINGS REBUILD
# -------------------------------------------------
@router.post(
    "/documents/{document_id}/embeddings/rebuild",
    status_code=status.HTTP_202_ACCEPTED,
)
async def rebuild_document_embeddings(
    background_tasks: BackgroundTasks,
    db: DbSessionDep,
    document: OwnedDocumentDep,
    embedding_jobs: EmbeddingJobServiceDep,
):
    return await embedding_jobs.rebuild_document(
        db=db,
        document=document,
        background_tasks=background_tasks,
    )

# -------------------------------------------------
# RUN PROJECT EMBEDDINGS SYNC
# -------------------------------------------------
@router.post(
    "/projects/{project_id}/embeddings/sync",
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_project_embeddings(
    background_tasks: BackgroundTasks,
    db: DbSessionDep,
    project: OwnedProjectDep,
    embedding_jobs: EmbeddingJobServiceDep,
):
    return await embedding_jobs.sync_project(
        db=db,
        project=project,
        background_tasks=background_tasks,
    )

# -------------------------------------------------
# DOCUMENT EMBEDDINGS REBUILD CANCEL
# -------------------------------------------------
@router.post(
    "/documents/{document_id}/embeddings/rebuild/cancel",
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_document_embedding_rebuild(
    db: DbSessionDep,
    document: OwnedDocumentDep,
    jobs: BackgroundJobServiceDep,
    embedding_jobs: EmbeddingJobServiceDep,
):
    return await embedding_jobs.cancel_document_rebuild(
        db=db,
        document=document,
        jobs=jobs,
    )

# -------------------------------------------------
# DOCUMENT EMBEDDINGS REBUILD RESUME
# -------------------------------------------------
@router.post(
    "/documents/{document_id}/embeddings/rebuild/resume",
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_document_embedding_rebuild(
    background_tasks: BackgroundTasks,
    db: DbSessionDep,
    document: OwnedDocumentDep,
    embedding_jobs: EmbeddingJobServiceDep,
):
    return await embedding_jobs.resume_document_rebuild(
        db=db,
        document=document,
        background_tasks=background_tasks,
    )


# -------------------------------------------------
# DOCUMENT EMBEDDINGS REBUILD RETRY
# -------------------------------------------------
@router.post(
    "/documents/{document_id}/embeddings/rebuild/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_document_embedding_rebuild(
    background_tasks: BackgroundTasks,
    db: DbSessionDep,
    document: OwnedDocumentDep,
    embedding_jobs: EmbeddingJobServiceDep,
):
    return await embedding_jobs.retry_document_rebuild(
        db=db,
        document=document,
        background_tasks=background_tasks,
    )


# -------------------------------------------------
# PROJECT EMBEDDINGS SYNC CANCEL
# -------------------------------------------------
@router.post(
    "/projects/{project_id}/embeddings/sync/cancel",
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_project_embedding_sync(
    db: DbSessionDep,
    project: OwnedProjectDep,
    jobs: BackgroundJobServiceDep,
    embedding_jobs: EmbeddingJobServiceDep,
):
    return await embedding_jobs.cancel_project_sync(
        db=db,
        project=project,
        jobs=jobs,
    )


# -------------------------------------------------
# PROJECT EMBEDDINGS SYNC RESUME
# -------------------------------------------------
@router.post(
    "/projects/{project_id}/embeddings/sync/resume",
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_project_embedding_sync(
    background_tasks: BackgroundTasks,
    db: DbSessionDep,
    project: OwnedProjectDep,
    embedding_jobs: EmbeddingJobServiceDep,
):
    return await embedding_jobs.resume_project_sync(
        db=db,
        project=project,
        background_tasks=background_tasks,
    )


# -------------------------------------------------
# PROJECT EMBEDDINGS SYNC RETRY
# -------------------------------------------------
@router.post(
    "/projects/{project_id}/embeddings/sync/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_project_embedding_sync(
    background_tasks: BackgroundTasks,
    db: DbSessionDep,
    project: OwnedProjectDep,
    embedding_jobs: EmbeddingJobServiceDep,
):
    return await embedding_jobs.retry_project_sync(
        db=db,
        project=project,
        background_tasks=background_tasks,
    )

# -------------------------------------------------
# PROJECT EMBEDDINGS SYNC STATUS
# -------------------------------------------------
@router.get("/projects/{project_id}/embeddings/sync")
async def get_project_embedding_sync_status(
    project: OwnedProjectDep,
    embedding_jobs: EmbeddingJobServiceDep,
):
    return embedding_jobs.project_sync_status(project)
