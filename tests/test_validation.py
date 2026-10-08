"""Test area 2: input validation (Pydantic schemas + HTTP 422 responses)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas import JobCreateRequest, Recipient


# --- Validation rules tested directly on the schema (fast, unit-style) -------


def test_valid_payload_is_accepted(sample_payload: dict) -> None:
    payload = JobCreateRequest(**sample_payload)

    assert payload.event_name == "AEREO Python Workshop"
    assert str(payload.date) == "2026-10-08"
    assert len(payload.recipients) == 2


def test_whitespace_only_name_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Recipient(name="   ", email="rahul@example.com")

    assert "at least 1 character" in str(exc_info.value)


def test_name_is_stripped_of_surrounding_spaces() -> None:
    recipient = Recipient(name="  Rahul Kumar  ", email="rahul@example.com")

    assert recipient.name == "Rahul Kumar"


def test_invalid_email_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Recipient(name="Rahul Kumar", email="not-an-email")

    assert "email" in str(exc_info.value).lower()


def test_duplicate_recipients_are_rejected_case_insensitively() -> None:
    payload = {
        "event_name": "Workshop",
        "certificate_title": "Certificate",
        "date": "2026-10-08",
        "recipients": [
            {"name": "Rahul Kumar", "email": "rahul@example.com"},
            {"name": "R. Kumar", "email": "RAHUL@example.com"},
        ],
    }
    with pytest.raises(ValidationError) as exc_info:
        JobCreateRequest(**payload)

    assert "Duplicate recipient" in str(exc_info.value)


def test_empty_recipient_list_is_rejected() -> None:
    payload = {
        "event_name": "Workshop",
        "certificate_title": "Certificate",
        "date": "2026-10-08",
        "recipients": [],
    }
    with pytest.raises(ValidationError):
        JobCreateRequest(**payload)


def test_missing_event_name_is_rejected(sample_payload: dict) -> None:
    payload = {k: v for k, v in sample_payload.items() if k != "event_name"}
    with pytest.raises(ValidationError):
        JobCreateRequest(**payload)


def test_invalid_date_format_is_rejected(sample_payload: dict) -> None:
    payload = dict(sample_payload, date="08/10/2026")
    with pytest.raises(ValidationError):
        JobCreateRequest(**payload)


# --- The same rules enforced through the HTTP API ----------------------------


def test_http_empty_name_returns_422(
    client: TestClient, sample_payload: dict
) -> None:
    payload = dict(sample_payload, recipients=[{"name": "  ", "email": "a@b.com"}])
    response = client.post("/api/jobs", json=payload)

    assert response.status_code == 422


def test_http_invalid_email_returns_422(
    client: TestClient, sample_payload: dict
) -> None:
    payload = dict(sample_payload, recipients=[{"name": "Rahul", "email": "rahul@"}])
    response = client.post("/api/jobs", json=payload)

    assert response.status_code == 422


def test_http_duplicate_emails_return_422(
    client: TestClient, sample_payload: dict
) -> None:
    payload = dict(
        sample_payload,
        recipients=[
            {"name": "Rahul Kumar", "email": "rahul@example.com"},
            {"name": "Rahul K", "email": "rahul@example.com"},
        ],
    )
    response = client.post("/api/jobs", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"][0]["msg"]
    assert "Duplicate recipient" in detail


def test_http_missing_recipients_returns_422(
    client: TestClient, sample_payload: dict
) -> None:
    payload = {k: v for k, v in sample_payload.items() if k != "recipients"}
    response = client.post("/api/jobs", json=payload)

    assert response.status_code == 422
