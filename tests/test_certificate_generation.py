"""Test area 3: certificate generation (PDF files are really produced)."""

from __future__ import annotations

import base64
import re
import zlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Certificate


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Return text from a ReportLab PDF (Info dict + decoded streams).

    ReportLab content streams are ASCII85 + Flate encoded by default;
    undecodable streams are skipped so the helper never raises.
    """

    parts = [pdf_bytes.decode("latin-1")]
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.S):
        raw = match.group(1).strip()
        try:
            if raw.endswith(b"~>"):  # ASCII85 end-of-data marker
                raw = base64.a85decode(raw[:-2])
            parts.append(zlib.decompress(raw).decode("latin-1"))
        except Exception:  # noqa: BLE001 - skip non-text streams
            continue
    return "\n".join(parts)


def _load_certificates(job_id: int) -> list[Certificate]:
    db = SessionLocal()
    try:
        return (
            db.query(Certificate).filter(Certificate.job_id == job_id).all()
        )
    finally:
        db.close()


def test_one_pdf_is_generated_per_recipient(
    client: TestClient, sample_payload: dict
) -> None:
    job = client.post("/api/jobs", json=sample_payload).json()
    certificates = _load_certificates(job["id"])

    assert len(certificates) == len(sample_payload["recipients"])
    for cert in certificates:
        assert cert.status == "COMPLETED"
        assert cert.file_path is not None
        assert Path(cert.file_path).is_file()


def test_generated_pdf_is_a_valid_non_empty_pdf(
    client: TestClient, sample_payload: dict
) -> None:
    job = client.post("/api/jobs", json=sample_payload).json()
    cert = _load_certificates(job["id"])[0]

    content = Path(cert.file_path).read_bytes()

    assert content[:5] == b"%PDF-"
    assert len(content) > 1000  # a real document, not an empty file


def test_pdf_contains_certificate_content(
    client: TestClient, sample_payload: dict
) -> None:
    """The required content (title, name, event, organization) is embedded."""

    job = client.post("/api/jobs", json=sample_payload).json()
    cert = _load_certificates(job["id"])[0]

    content = Path(cert.file_path).read_bytes().decode("latin-1")

    assert sample_payload["certificate_title"] in content
    assert sample_payload["event_name"] in content
    assert cert.recipient_name in content
    assert "AEREO" in content  # organization name


def test_bulk_generation_processes_every_recipient(
    client: TestClient,
) -> None:
    """50 recipients -> 50 successful certificates in a single job."""

    payload = {
        "event_name": "AEREO Python Workshop",
        "certificate_title": "Certificate of Participation",
        "date": "2026-10-08",
        "recipients": [
            {"name": f"Student {i}", "email": f"student{i}@example.com"}
            for i in range(50)
        ],
    }
    job = client.post("/api/jobs", json=payload).json()

    status = client.get(f"/api/jobs/{job['id']}").json()
    assert status["total_count"] == 50
    assert status["success_count"] == 50
    assert status["failure_count"] == 0
    assert status["status"] == "COMPLETED"

    certificates = _load_certificates(job["id"])
    assert len(certificates) == 50
    assert all(c.status == "COMPLETED" for c in certificates)


def test_pdf_contains_event_date(
    client: TestClient, sample_payload: dict
) -> None:
    """The event date appears on the certificate (decoded from streams)."""

    job = client.post("/api/jobs", json=sample_payload).json()
    cert = _load_certificates(job["id"])[0]

    text = _extract_pdf_text(Path(cert.file_path).read_bytes())

    assert "Date: October 8, 2026" in text
