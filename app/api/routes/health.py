from fastapi import APIRouter

from app.dependencies import DbSessionDep, HealthServiceDep

router = APIRouter()


@router.get("/health")
async def health(
    db: DbSessionDep,
    service: HealthServiceDep,
):
    return await service.check(db)
