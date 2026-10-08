"""Test area 5: individual certificate failure must not stop the job.

Certificate generation is mocked/monkeypatched here so failures are
deterministic and no external service is involved.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Certificate, GenerationJob, JobStatus
from app.schemas import JobCreateRequest
from app.services import job_service, pdf_service


def _job_status(client: TestClient, job_id: int) -> dict:
    return client.get(f"/api/jobs/{job_id}").json()


def _certificates(client: TestClient, job_id: int) -> list[dict]:
    return client.get(f"/api/jobs/{job_id}/certificates").json()


def test_one_failure_does_not_stop_other_recipients(
    client: TestClient, sample_payload: dict, monkeypatch
) -> None:
    """The FIRST recipient fails to render; the second must still finish."""

    def flaky_renderer(output_path, **kwargs) -> object:
        if kwargs["recipient_name"] == "Manvitha Cheekati":
            raise RuntimeError("Simulated renderer crash")
        return pdf_service.generate_certificate_pdf(output_path, **kwargs)

    # Patch the name bound inside job_service (where the worker calls it).
    monkeypatch.setattr(
        "app.services.job_service.generate_certificate_pdf", flaky_renderer
    )

    job = client.post("/api/jobs", json=sample_payload).json()
    status = _job_status(client, job["id"])
    certificates = _certificates(client, job["id"])

    # Job finished despite the failure.
    assert status["status"] == JobStatus.COMPLETED_WITH_ERRORS.value
    assert status["success_count"] == 1
    assert status["failure_count"] == 1
    assert status["progress"] == 100.0  # every recipient was processed
    assert status["completed_at"] is not None

    # No recipient is stuck in PENDING.
    assert all(c["status"] != "PENDING" for c in certificates)

    failed = [c for c in certificates if c["status"] == "FAILED"]
    succeeded = [c for c in certificates if c["status"] == "COMPLETED"]

    assert len(failed) == 1 and len(succeeded) == 1
    assert failed[0]["recipient_name"] == "Manvitha Cheekati"
    assert "Simulated renderer crash" in failed[0]["error_message"]
    assert failed[0]["download_url"] is None  # nothing to download
    assert succeeded[0]["download_url"] is not None

    # The failed PDF cannot be downloaded, the successful one can.
    assert (
        client.get(f"/api/certificates/{failed[0]['id']}/download").status_code
        == 409
    )
    assert (
        client.get(
            f"/api/certificates/{succeeded[0]['id']}/download"
        ).status_code
        == 200
    )


def test_all_recipients_failing_marks_job_failed(
    client: TestClient, sample_payload: dict, monkeypatch
) -> None:
    """When nothing succeeds the job ends as FAILED (not stuck forever)."""

    def broken_renderer(output_path, **kwargs) -> None:
        raise RuntimeError("Renderer unavailable")

    monkeypatch.setattr(
        "app.services.job_service.generate_certificate_pdf", broken_renderer
    )

    job = client.post("/api/jobs", json=sample_payload).json()
    status = _job_status(client, job["id"])

    assert status["status"] == JobStatus.FAILED.value
    assert status["success_count"] == 0
    assert status["failure_count"] == 2
    assert status["completed_at"] is not None


def test_worker_revalidates_recipient_data_before_rendering(
    client: TestClient, sample_payload: dict
) -> None:
    """Defensive validation: a bad row that slips into the DB is recorded
    as a per-recipient FAILED result instead of crashing the worker."""

    db = SessionLocal()
    try:
        job = job_service.create_job(db, JobCreateRequest(**sample_payload))
        job_id = job.id
        # Corrupt one row directly, bypassing API validation.
        cert = (
            db.query(Certificate).filter(Certificate.job_id == job_id).first()
        )
        cert.recipient_email = "not-a-valid-email"
        db.commit()
    finally:
        db.close()

    job_service.process_job(job_id)

    status = _job_status(client, job_id)
    certificates = _certificates(client, job_id)

    assert status["status"] == JobStatus.COMPLETED_WITH_ERRORS.value
    failed = [c for c in certificates if c["status"] == "FAILED"]
    assert len(failed) == 1
    assert "Invalid email address" in failed[0]["error_message"]
    # The healthy recipient still completed.
    assert sum(c["status"] == "COMPLETED" for c in certificates) == 1


def test_failure_message_is_persisted_for_debugging(
    client: TestClient, sample_payload: dict, monkeypatch
) -> None:
    """error_message survives so users can see WHY a certificate failed."""

    def flaky_renderer(output_path, **kwargs) -> None:
        raise ValueError("Template data missing")

    monkeypatch.setattr(
        "app.services.job_service.generate_certificate_pdf", flaky_renderer
    )

    job = client.post("/api/jobs", json=sample_payload).json()
    certificates = _certificates(client, job["id"])

    for cert in certificates:
        assert cert["status"] == "FAILED"
        assert cert["error_message"] == "Template data missing"
