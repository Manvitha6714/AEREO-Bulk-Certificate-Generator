"""Job lifecycle: creation, background processing and progress tracking.

Design notes
------------
* `create_job` only writes rows (job + one PENDING certificate per
  recipient) and returns immediately - the HTTP request stays fast.
* `process_job` is handed to FastAPI's BackgroundTasks. It opens its
  OWN database session because the request session is already closed
  by the time the background task runs.
* Every recipient is processed inside its own try/except. One bad
  recipient can never abort the whole job.
* Counters are incremented with atomic SQL updates
  (`success_count = success_count + 1`) instead of read-modify-write,
  so progress stays correct even if processing is ever parallelised.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Certificate, CertificateStatus, GenerationJob, JobStatus
from app.schemas import JobCreateRequest, Recipient
from app.services.pdf_service import generate_certificate_pdf
from app.utils.files import certificate_filename


def _utcnow() -> datetime:
    """Timezone-naive UTC timestamp (matches SQLite's DateTime storage)."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_job(db: Session, payload: JobCreateRequest) -> GenerationJob:
    """Persist a new job and one PENDING certificate row per recipient."""

    job = GenerationJob(
        event_name=payload.event_name,
        certificate_title=payload.certificate_title,
        organization_name=payload.organization_name,
        date=payload.date,
        status=JobStatus.QUEUED.value,
        total_count=len(payload.recipients),
    )
    db.add(job)
    # Flush so the job gets an id before we create child certificate rows.
    db.flush()

    for recipient in payload.recipients:
        db.add(
            Certificate(
                job_id=job.id,
                recipient_name=recipient.name,
                recipient_email=recipient.email,
                status=CertificateStatus.PENDING.value,
            )
        )

    db.commit()
    db.refresh(job)
    return job


def _validate_recipient(name: str, email: str) -> None:
    """Defensive re-validation inside the worker.

    The API already validated input, but a worker must never trust
    stale/duplicated data - failing here records a per-recipient error
    instead of writing a broken PDF. Plain string checks run FIRST so
    the stored error message stays short and human-readable.
    """

    if not name or not name.strip():
        raise ValueError("Recipient name must not be empty.")
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError(f"Invalid email address: {email}")


def _process_certificate(db: Session, job: GenerationJob, cert: Certificate) -> None:
    """Generate the PDF for one recipient and persist the outcome.

    Raises on failure - the caller decides how to record the error.
    """

    _validate_recipient(cert.recipient_name, cert.recipient_email)
    # Full Pydantic re-parse as a second, stricter safety net.
    Recipient(name=cert.recipient_name, email=cert.recipient_email)

    filename = certificate_filename(job.id, cert.id, cert.recipient_name)
    output_path = settings.storage_path / filename

    generate_certificate_pdf(
        output_path,
        certificate_title=job.certificate_title,
        recipient_name=cert.recipient_name,
        event_name=job.event_name,
        event_date=job.date,
        organization_name=job.organization_name,
    )

    if not output_path.is_file():
        raise RuntimeError("PDF renderer reported success but no file was written.")

    cert.status = CertificateStatus.COMPLETED.value
    cert.file_path = str(output_path)
    cert.error_message = None


def _increment(db: Session, job_id: int, column: str) -> None:
    """Atomically bump a job counter (safe under concurrency).

    Using `SET success_count = success_count + 1` in SQL avoids the
    classic read-modify-write race condition.
    """

    field = getattr(GenerationJob, column)
    db.execute(
        update(GenerationJob)
        .where(GenerationJob.id == job_id)
        .values(**{column: field + 1})
    )


def process_job(job_id: int) -> None:
    """Background entry point: process every recipient independently."""

    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:  # job deleted while queued - nothing to do
            return

        job.status = JobStatus.PROCESSING.value
        db.commit()

        certificates = db.query(Certificate).filter(Certificate.job_id == job_id).all()

        for cert in certificates:
            # One transaction per recipient: if this recipient fails,
            # the previous ones are already safely committed.
            try:
                _process_certificate(db, job, cert)
                _increment(db, job_id, "success_count")
                db.commit()
            except Exception as exc:  # noqa: BLE001 - record ANY failure, keep going
                db.rollback()
                cert.status = CertificateStatus.FAILED.value
                cert.error_message = str(exc) or exc.__class__.__name__
                _increment(db, job_id, "failure_count")
                db.commit()

        _finalize_job(db, job_id)
    except Exception:  # job-level failure (e.g. database gone)
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job is not None:
            job.status = JobStatus.FAILED.value
            job.completed_at = _utcnow()
            db.commit()
        raise
    finally:
        db.close()


def _finalize_job(db: Session, job_id: int) -> None:
    """Set the terminal status once every recipient has been processed."""

    job = db.get(GenerationJob, job_id)
    if job is None:
        return

    if job.failure_count == 0:
        job.status = JobStatus.COMPLETED.value
    elif job.success_count == 0:
        # Every single recipient failed -> the job itself is a failure.
        job.status = JobStatus.FAILED.value
    else:
        job.status = JobStatus.COMPLETED_WITH_ERRORS.value

    job.completed_at = _utcnow()
    db.commit()
