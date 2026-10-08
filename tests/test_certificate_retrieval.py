"""Test area 6: retrieving / downloading generated certificates."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Certificate
from app.schemas import JobCreateRequest
from app.services import job_service


def test_list_certificates_shows_download_urls(
    client: TestClient, created_job: dict
) -> None:
    response = client.get(f"/api/jobs/{created_job['id']}/certificates")

    assert response.status_code == 200
    certificates = response.json()
    assert len(certificates) == 2
    for cert in certificates:
        assert cert["status"] == "COMPLETED"
        assert cert["download_url"] == f"/api/certificates/{cert['id']}/download"
        assert cert["error_message"] is None


def test_download_returns_a_pdf_file(
    client: TestClient, created_job: dict
) -> None:
    certificates = client.get(
        f"/api/jobs/{created_job['id']}/certificates"
    ).json()
    cert = certificates[0]

    response = client.get(f"/api/certificates/{cert['id']}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:5] == b"%PDF-"
    assert "certificate" in response.headers["content-disposition"]


def test_download_matches_the_requested_certificate(
    client: TestClient, created_job: dict
) -> None:
    """Each download contains the recipient it belongs to."""

    certificates = client.get(
        f"/api/jobs/{created_job['id']}/certificates"
    ).json()

    for cert in certificates:
        content = client.get(f"/api/certificates/{cert['id']}/download").content
        assert cert["recipient_name"].encode() in content


def test_unknown_certificate_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/certificates/99999/download")

    assert response.status_code == 404
    assert "99999" in response.json()["detail"]


def test_pending_certificate_cannot_be_downloaded(
    client: TestClient, sample_payload: dict
) -> None:
    """A job created but not yet processed has no PDFs yet -> 409."""

    db = SessionLocal()
    try:
        job = job_service.create_job(db, JobCreateRequest(**sample_payload))
        job_id = job.id
    finally:
        db.close()

    certificates = client.get(f"/api/jobs/{job_id}/certificates").json()
    assert certificates[0]["status"] == "PENDING"
    assert certificates[0]["download_url"] is None

    response = client.get(f"/api/certificates/{certificates[0]['id']}/download")
    assert response.status_code == 409
    assert "PENDING" in response.json()["detail"]


def test_missing_file_on_disk_returns_404(
    client: TestClient, created_job: dict
) -> None:
    """DB row says COMPLETED but the file was deleted from storage."""

    certificates = client.get(
        f"/api/jobs/{created_job['id']}/certificates"
    ).json()
    cert_id = certificates[0]["id"]

    db = SessionLocal()
    try:
        cert = db.get(Certificate, cert_id)
        file_path = Path(cert.file_path)
        assert file_path.is_file()
        file_path.unlink()
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/certificates/{cert_id}/download")
    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_each_job_gets_its_own_certificates(
    client: TestClient, sample_payload: dict
) -> None:
    """Two jobs never mix their certificates."""

    first = client.post("/api/jobs", json=sample_payload).json()
    second = client.post("/api/jobs", json=sample_payload).json()

    first_certs = client.get(f"/api/jobs/{first['id']}/certificates").json()
    second_certs = client.get(f"/api/jobs/{second['id']}/certificates").json()

    assert all(c["job_id"] == first["id"] for c in first_certs)
    assert all(c["job_id"] == second["id"] for c in second_certs)
    assert {c["id"] for c in first_certs}.isdisjoint(
        {c["id"] for c in second_certs}
    )
