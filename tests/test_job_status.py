"""Test area 4: job status, progress tracking and 404 handling."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import GenerationJob, JobStatus
from app.schemas import JobCreateRequest
from app.services import job_service


def test_completed_job_reports_full_progress(
    client: TestClient, created_job: dict
) -> None:
    response = client.get(f"/api/jobs/{created_job['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == JobStatus.COMPLETED.value
    assert body["total_count"] == 2
    assert body["success_count"] == 2
    assert body["failure_count"] == 0
    assert body["progress"] == 100.0
    assert body["completed_at"] is not None


def test_queued_job_reports_zero_progress(
    client: TestClient, sample_payload: dict
) -> None:
    """A job created but NOT yet processed stays QUEUED at 0%.

    Uses the service directly so no background task runs - this is the
    state clients see between POST and worker completion.
    """

    db = SessionLocal()
    try:
        job = job_service.create_job(db, JobCreateRequest(**sample_payload))
        job_id = job.id
    finally:
        db.close()

    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == JobStatus.QUEUED.value
    assert body["progress"] == 0.0
    assert body["success_count"] == 0
    assert body["completed_at"] is None


def test_processing_job_reports_partial_progress(
    client: TestClient, sample_payload: dict
) -> None:
    """Mid-flight snapshot: 1 of 4 processed -> 25% progress."""

    payload = dict(
        sample_payload,
        recipients=[
            {"name": f"Student {i}", "email": f"student{i}@example.com"}
            for i in range(4)
        ],
    )

    db = SessionLocal()
    try:
        job = job_service.create_job(db, JobCreateRequest(**payload))
        job_id = job.id
        # Simulate a worker that already finished one recipient.
        job.status = JobStatus.PROCESSING.value
        job.success_count = 1
        db.commit()
    finally:
        db.close()

    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == JobStatus.PROCESSING.value
    assert body["progress"] == 25.0
    assert body["success_count"] == 1
    assert body["failure_count"] == 0


def test_progress_property_handles_edge_cases() -> None:
    """Unit test of the progress formula (no HTTP involved)."""

    job = GenerationJob(
        event_name="e", certificate_title="t", date=None, total_count=4
    )

    assert job.progress == 0.0  # nothing processed yet

    job.success_count, job.failure_count = 1, 1
    assert job.progress == 50.0

    job.success_count, job.failure_count = 4, 0
    assert job.progress == 100.0

    job.total_count = 0
    assert job.progress == 0.0  # division-by-zero guard


def test_unknown_job_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/jobs/99999")

    assert response.status_code == 404
    assert "99999" in response.json()["detail"]


def test_unknown_job_certificates_endpoint_returns_404(
    client: TestClient,
) -> None:
    response = client.get("/api/jobs/99999/certificates")

    assert response.status_code == 404
