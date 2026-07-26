from fastapi import APIRouter, File, UploadFile, status

from app.dependencies import (
    BackgroundJobServiceDep,
    DbSessionDep,
    DocumentChunkRepositoryDep,
    DocumentRepositoryDep,
    DocumentServiceDep,
    OwnedDocumentDep,
    OwnedProjectDep,
)
from app.schemas import (
    DocumentChunkResponse,
    DocumentProcessingResponse,
    DocumentResponse,
)

router = APIRouter()

# FastAPI treats file uploads as request-body metadata rather than injectable
# dependencies, so keep this default separate from the dependency aliases.
UPLOAD_FILE_DEFAULT = File(...)


# -------------------------------------------------
# GET DOCUMENTS
# -------------------------------------------------
@router.get(
    "/projects/{project_id}/documents",
    response_model=list[DocumentResponse],
)
async def get_documents(
    db: DbSessionDep,
    project: OwnedProjectDep,
    documents: DocumentRepositoryDep,
):
    return await documents.list_for_project(db, project.id)


# -------------------------------------------------
# UPLOAD DOCUMENT
# -------------------------------------------------
@router.post(
    "/projects/{project_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    db: DbSessionDep,
    project: OwnedProjectDep,
    service: DocumentServiceDep,
    file: UploadFile = UPLOAD_FILE_DEFAULT,
):
    return await service.upload(
        db,
        project,
        file,
    )


# -------------------------------------------------
# PROCESS DOCUMENT
# -------------------------------------------------
@router.post(
    "/documents/{document_id}/process",
    response_model=DocumentProcessingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_document(
    db: DbSessionDep,
    document: OwnedDocumentDep,
    service: DocumentServiceDep,
    jobs: BackgroundJobServiceDep,
):
    return await service.enqueue_processing_response(db, document, jobs)

# -------------------------------------------------
# CANCEL PROCESS DOCUMENT
# -------------------------------------------------
@router.post(
    "/documents/{document_id}/process/cancel",
    response_model=DocumentProcessingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_document_processing(
    db: DbSessionDep,
    document: OwnedDocumentDep,
    service: DocumentServiceDep,
    jobs: BackgroundJobServiceDep,
):
    return await service.cancel_processing(db, document, jobs)

# -------------------------------------------------
# RETRY PROCESS DOCUMENT
# -------------------------------------------------
@router.post(
    "/documents/{document_id}/process/retry",
    response_model=DocumentProcessingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_document_processing(
    db: DbSessionDep,
    document: OwnedDocumentDep,
    service: DocumentServiceDep,
    jobs: BackgroundJobServiceDep,
):
    return await service.retry_processing(db, document, jobs)


# -------------------------------------------------
# GET SINGLE DOCUMENT
# -------------------------------------------------
@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
)
async def get_document(
    document: OwnedDocumentDep,
):
    return document


# -------------------------------------------------
# GET DOCUMENT CHUNKS
# -------------------------------------------------
@router.get(
    "/documents/{document_id}/chunks",
    response_model=list[DocumentChunkResponse],
)
async def get_document_chunks(
    db: DbSessionDep,
    document: OwnedDocumentDep,
    chunks: DocumentChunkRepositoryDep,
):
    return await chunks.list_for_document(
        db,
        document.id,
    )


# -------------------------------------------------
# DELETE DOCUMENT
# -------------------------------------------------
@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    db: DbSessionDep,
    document: OwnedDocumentDep,
    service: DocumentServiceDep,
):
    await service.delete(db, document)
