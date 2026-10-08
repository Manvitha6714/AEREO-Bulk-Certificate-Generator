"""SQLAlchemy ORM models for jobs and certificates."""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobStatus(str, enum.Enum):
    """Lifecycle states of a generation job."""

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


class CertificateStatus(str, enum.Enum):
    """Lifecycle states of a single certificate."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class GenerationJob(Base):
    """One bulk certificate generation request."""

    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_name: Mapped[str] = mapped_column(String(255))
    certificate_title: Mapped[str] = mapped_column(String(255))
    organization_name: Mapped[str] = mapped_column(String(255), default="AEREO")
    date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(32), default=JobStatus.QUEUED.value, index=True
    )

    total_count: Mapped[int] = mapped_column(default=0)
    success_count: Mapped[int] = mapped_column(default=0)
    failure_count: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Certificate.id",
    )

    @property
    def progress(self) -> float:
        """Percentage of recipients processed so far (0.0 - 100.0)."""

        if not self.total_count:
            return 0.0
        # `or 0` keeps the property safe before column defaults are
        # applied (e.g. an in-memory job that was never flushed).
        processed = (self.success_count or 0) + (self.failure_count or 0)
        return round(processed / self.total_count * 100, 2)


class Certificate(Base):
    """A single generated (or failed) certificate for one recipient."""

    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="CASCADE"), index=True
    )
    recipient_name: Mapped[str] = mapped_column(String(255))
    recipient_email: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=CertificateStatus.PENDING.value, index=True
    )
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    job: Mapped[GenerationJob] = relationship(back_populates="certificates")

    __table_args__ = (
        # Fast lookup of "all certificates for a job with status X".
        Index("ix_certificates_job_status", "job_id", "status"),
    )
