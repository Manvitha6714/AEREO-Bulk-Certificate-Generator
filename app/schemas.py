"""Pydantic request/response schemas and input validation rules.

Validation lives here (close to the API contract) so it can be tested
directly without going through HTTP when needed.
"""

# NOTE: `import datetime` (module) instead of `from datetime import ...`
# on purpose - a field named `date: date = Field(...)` would otherwise
# shadow the imported type in the class body and break Pydantic.
import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

# --- Reusable constrained types ------------------------------------------------

# strip_whitespace removes accidental spaces; min_length=1 then rejects
# empty / whitespace-only strings with a clear Pydantic error.
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# Guard rails for a "bulk" endpoint: at least one recipient, and a cap
# so a single request cannot accidentally flood the server.
RecipientList = Annotated[list["Recipient"], Field(min_length=1, max_length=500)]


class Recipient(BaseModel):
    """One person receiving a certificate."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: NonEmptyStr = Field(..., examples=["Manvitha Cheekati"])
    email: EmailStr = Field(..., examples=["manvitha@example.com"])

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        """Double-check the name survives stripping (defensive, testable)."""

        if not value.strip():
            raise ValueError("Recipient name must not be empty.")
        return value.strip()


class JobCreateRequest(BaseModel):
    """Payload for POST /api/jobs: one event, many recipients."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    event_name: NonEmptyStr = Field(..., examples=["AEREO Python Workshop"])
    certificate_title: NonEmptyStr = Field(
        ..., examples=["Certificate of Participation"]
    )
    date: datetime.date = Field(
        ..., description="Event date in YYYY-MM-DD format."
    )
    organization_name: NonEmptyStr = Field(
        default="AEREO",
        description="Organization printed on the certificate.",
        examples=["AEREO"],
    )
    recipients: RecipientList

    @model_validator(mode="after")
    def reject_duplicate_recipients(self) -> "JobCreateRequest":
        """Duplicate e-mails within one job are an input error.

        Comparison is case-insensitive, so Rahul@X.com and rahul@X.com
        are treated as the same person.
        """

        seen: set[str] = set()
        duplicates: set[str] = set()
        for recipient in self.recipients:
            key = recipient.email.lower()
            if key in seen:
                duplicates.add(key)
            seen.add(key)

        if duplicates:
            duplicated = ", ".join(sorted(duplicates))
            raise ValueError(
                f"Duplicate recipient email(s) found: {duplicated}. "
                "Each recipient must appear only once per job."
            )
        return self


# --- Responses ------------------------------------------------------------------


class JobCreateResponse(BaseModel):
    """Immediate response after creating a job (processing is async)."""

    id: int
    status: str
    total_count: int
    success_count: int
    failure_count: int
    progress: float
    detail: str
    job_url: str
    certificates_url: str


class JobStatusResponse(BaseModel):
    """GET /api/jobs/{job_id} - status + progress snapshot."""

    id: int
    event_name: str
    certificate_title: str
    date: datetime.date
    status: str
    total_count: int
    success_count: int
    failure_count: int
    progress: float
    created_at: datetime.datetime
    completed_at: datetime.datetime | None = None


class CertificateResponse(BaseModel):
    """GET /api/jobs/{job_id}/certificates - one row per recipient."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    recipient_name: str
    recipient_email: str
    status: str
    error_message: str | None = None
    created_at: datetime.datetime
    download_url: str | None = None
