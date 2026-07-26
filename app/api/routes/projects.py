
from fastapi import APIRouter, status

from app.dependencies import (
    CurrentUserDep,
    DbSessionDep,
    OwnedProjectDep,
    ProjectRepositoryDep,
    ProjectUpdateServiceDep,
    RetrievalServiceDep,
)
from app.schemas import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    RetrievalRequest,
    RetrievalResponse,
)

router = APIRouter()

# -------------------------------------------------
# CREATE PROJECT
# -------------------------------------------------
@router.post(
    "/", 
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_project(
    payload: ProjectCreate,
    db: DbSessionDep,
    user: CurrentUserDep,
    service: ProjectUpdateServiceDep,
):
    return await service.create(
        db=db,
        payload=payload,
        user_id=user.id,
    )

# -------------------------------------------------
#  GET SINGLE PROJECT
# -------------------------------------------------
@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project: OwnedProjectDep,
):
    return project


# -------------------------------------------------
# UPDATE PROJECT
# -------------------------------------------------
@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    payload: ProjectUpdate,
    db: DbSessionDep,
    project: OwnedProjectDep,
    service: ProjectUpdateServiceDep,
):
    return await service.update(
        db=db,
        project=project,
        payload=payload,
    )

# -------------------------------------------------
#  GET PROJECTS
# -------------------------------------------------
@router.get("/", response_model=list[ProjectResponse])
async def get_projects(
    db: DbSessionDep,
    user: CurrentUserDep,
    projects: ProjectRepositoryDep
):
    return await projects.list_for_user(
        db,
        user.id,
    )   

# -------------------------------------------------
#  RETRIEVE PROJECTS
# -------------------------------------------------
@router.post(
    "/{project_id}/retrieve",
    response_model=RetrievalResponse,
)
async def retrieve(
    request: RetrievalRequest,
    db: DbSessionDep,
    project: OwnedProjectDep,
    current_user: CurrentUserDep,
    retrieval_service: RetrievalServiceDep,
):
    return await retrieval_service.retrieve(
        db=db,
        project_id=project.id,
        user_id=current_user.id,
        query=request.query,
        top_k=request.top_k,
    )

# -------------------------------------------------
# DELETE PROJECT
# -------------------------------------------------
@router.delete(
    "/{project_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project(
    db: DbSessionDep,
    project: OwnedProjectDep,
    service: ProjectUpdateServiceDep,
):
    await service.delete(db, project)
