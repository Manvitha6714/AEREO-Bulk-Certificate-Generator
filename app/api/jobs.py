"""Job endpoints: create a job, inspect status/progress, list certificates."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Certificate, GenerationJob
from app.schemas import (
    CertificateResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
)
from app.services import job_service

router = APIRouter(tags=["jobs"])


def _get_job_or_404(db: Session, job_id: int) -> GenerationJob:
    """Shared lookup so every job endpoint returns the same 404 shape."""

    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id {job_id} not found.",
        )
    return job


@router.post(
    "/jobs",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """Create a bulk certificate generation job.

    Validation errors (empty name, bad email, duplicates) are returned
    as HTTP 422 by Pydantic before anything is persisted. The PDF work
    runs after the response via BackgroundTasks.
    """

    job = job_service.create_job(db, payload)

    # Added AFTER the DB commit, so the response returns quickly.
    # FastAPI's TestClient runs background tasks synchronously, which
    # makes tests deterministic - no threads, no sleeps, no polling.
    background_tasks.add_task(job_service.process_job, job.id)

    return JobCreateResponse(
        id=job.id,
        status=job.status,
        total_count=job.total_count,
        success_count=job.success_count,
        failure_count=job.failure_count,
        progress=job.progress,
        detail=(
            f"Job accepted with {job.total_count} recipient(s). "
            "Poll GET /api/jobs/{id} for progress."
        ),
        job_url=f"/api/jobs/{job.id}",
        certificates_url=f"/api/jobs/{job.id}/certificates",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: int, db: Session = Depends(get_db)) -> JobStatusResponse:
    """Return job status, counters and progress percentage."""

    job = _get_job_or_404(db, job_id)
    return JobStatusResponse(
        id=job.id,
        event_name=job.event_name,
        certificate_title=job.certificate_title,
        date=job.date,
        status=job.status,
        total_count=job.total_count,
        success_count=job.success_count,
        failure_count=job.failure_count,
        progress=job.progress,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get(
    "/jobs/{job_id}/certificates",
    response_model=list[CertificateResponse],
)
def list_job_certificates(
    job_id: int, db: Session = Depends(get_db)
) -> list[CertificateResponse]:
    """List every recipient's certificate (PENDING/COMPLETED/FAILED).

    `download_url` is only present when the PDF was actually generated.
    """

    _get_job_or_404(db, job_id)
    certificates = db.query(Certificate).filter(Certificate.job_id == job_id).all()

    return [
        CertificateResponse(
            id=cert.id,
            job_id=cert.job_id,
            recipient_name=cert.recipient_name,
            recipient_email=cert.recipient_email,
            status=cert.status,
            error_message=cert.error_message,
            created_at=cert.created_at,
            download_url=(
                f"/api/certificates/{cert.id}/download"
                if cert.status == "COMPLETED"
                else None
            ),
        )
        for cert in certificates
    ]
