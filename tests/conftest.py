"""Shared pytest fixtures.

IMPORTANT: the environment variables below must be set BEFORE any
`app.*` module is imported, because `app.config.Settings` and the
SQLAlchemy engine are created at import time. This gives every test
run its own temporary database and storage folder - fully isolated
from the developer's local data and deterministic (no external services).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_DIR = Path(tempfile.mkdtemp(prefix="certgen_tests_"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR / 'test.db'}"
os.environ["CERTIFICATE_STORAGE_DIR"] = str(_TEST_DIR / "certificates")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """HTTP client with a fresh database schema for each test."""

    Base.metadata.drop_all(bind=engine)  # clean slate per test
    init_db()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def sample_payload() -> dict:
    """A valid POST /api/jobs body (the example from the assignment)."""

    return {
        "event_name": "AEREO Python Workshop",
        "certificate_title": "Certificate of Participation",
        "date": "2026-10-08",
        "recipients": [
            {"name": "Manvitha Cheekati", "email": "manvitha@example.com"},
            {"name": "Rahul Kumar", "email": "rahul@example.com"},
        ],
    }


@pytest.fixture()
def created_job(client: TestClient, sample_payload: dict) -> dict:
    """Create a job and return its API status payload (fully processed)."""

    response = client.post("/api/jobs", json=sample_payload)
    assert response.status_code == 202
    return response.json()
