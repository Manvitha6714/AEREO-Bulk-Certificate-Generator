"""Test area 1: creating a generation job."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Certificate, GenerationJob, JobStatus
from app.schemas import JobCreateRequest
from app.services import job_service


def test_create_job_returns_202_with_queued_status(
    client: TestClient, sample_payload: dict
) -> None:
    """POST /api/jobs accepts the request quickly with 202 + QUEUED."""

    response = client.post("/api/jobs", json=sample_payload)

    assert response.status_code == 202
    body = response.json()
    # The response is serialized BEFORE background work starts.
    assert body["status"] == JobStatus.QUEUED.value
    assert body["total_count"] == 2
    assert body["success_count"] == 0
    assert body["failure_count"] == 0
    assert body["progress"] == 0.0
    assert body["job_url"] == f"/api/jobs/{body['id']}"
    assert body["certificates_url"] == f"/api/jobs/{body['id']}/certificates"


def test_create_job_persists_job_and_one_pending_row_per_recipient(
    sample_payload: dict,
) -> None:
    """Service level: creation stores the job + PENDING rows only.

    No PDF is generated at creation time - that happens in the
    background task.
    """

    db = SessionLocal()
    try:
        payload = JobCreateRequest(**sample_payload)
        job = job_service.create_job(db, payload)

        assert job.status == JobStatus.QUEUED.value
        assert job.total_count == 2
        assert job.success_count == 0
        assert job.failure_count == 0
        assert job.completed_at is None

        certificates = db.query(Certificate).filter(Certificate.job_id == job.id).all()
        assert len(certificates) == 2
        assert all(c.status == "PENDING" for c in certificates)
        assert all(c.file_path is None for c in certificates)
    finally:
        db.close()


def test_created_job_is_retrievable_by_id(
    client: TestClient, sample_payload: dict
) -> None:
    """The id returned by POST works on GET /api/jobs/{id}."""

    created = client.post("/api/jobs", json=sample_payload).json()
    response = client.get(f"/api/jobs/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["event_name"] == sample_payload["event_name"]
    assert body["certificate_title"] == sample_payload["certificate_title"]


def test_bulk_request_with_many_recipients(client: TestClient) -> None:
    """A larger bulk payload (50 recipients) is accepted in one request."""

    payload = {
        "event_name": "AEREO Python Workshop",
        "certificate_title": "Certificate of Participation",
        "date": "2026-10-08",
        "recipients": [
            {"name": f"Student {i}", "email": f"student{i}@example.com"}
            for i in range(50)
        ],
    }
    response = client.post("/api/jobs", json=payload)

    assert response.status_code == 202
    assert response.json()["total_count"] == 50
