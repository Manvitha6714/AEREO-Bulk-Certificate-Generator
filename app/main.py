"""FastAPI application entry point.

Run locally with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import certificates, jobs
from app.config import settings
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create tables and the storage folder once at startup."""

    init_db()
    settings.storage_path  # property call creates the directory
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Bulk certificate generation API: submit one job with many "
        "recipients and download the generated PDFs."
    ),
    lifespan=lifespan,
)

app.include_router(jobs.router, prefix="/api")
app.include_router(certificates.router, prefix="/api")


@app.get("/", tags=["health"])
def read_root() -> dict[str, str]:
    """Simple health check / entry point."""

    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "endpoints": "POST /api/jobs, GET /api/jobs/{id}, "
        "GET /api/jobs/{id}/certificates, "
        "GET /api/certificates/{id}/download",
    }
