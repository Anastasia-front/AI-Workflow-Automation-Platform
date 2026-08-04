import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import router
from app.core import AsyncSessionLocal
from app.services import ApplicationError
from app.services.provider_config import provider_config
from app.services.workflow.recovery import (
    recover_running_workflows,
)
from app.web.docs_landing import router as docs_landing_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        await provider_config.seed_defaults(db)
        await provider_config.load_from_db(db)
    await recover_running_workflows()
    yield


app = FastAPI(
    title="AI Automation Platform",
    description=(
        "Backend for AI workflow automation, document processing, and multi-provider LLM integration."
    ),
    lifespan=lifespan,
    docs_url="/swagger",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(ApplicationError)
async def application_error_handler(_request: Request, exc: ApplicationError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )

app.include_router(docs_landing_router)
app.include_router(router)
