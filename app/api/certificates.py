"""Certificate download endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Certificate
from app.utils.files import slugify

router = APIRouter(tags=["certificates"])


@router.get("/certificates/{certificate_id}/download")
def download_certificate(
    certificate_id: int, db: Session = Depends(get_db)
) -> FileResponse:
    """Download the generated PDF for one certificate.

    404 -> unknown certificate id OR the PDF file no longer exists on disk.
    409 -> certificate exists but generation has not finished/failed.
    """

    certificate = db.get(Certificate, certificate_id)
    if certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate with id {certificate_id} not found.",
        )

    if certificate.status != "COMPLETED" or not certificate.file_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Certificate {certificate_id} has status "
                f"'{certificate.status}' and cannot be downloaded."
            ),
        )

    file_path = Path(certificate.file_path)
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"PDF file for certificate {certificate_id} is missing "
                "from storage."
            ),
        )

    # Slugify the recipient name so the suggested download filename is
    # safe (no quotes, slashes or path segments) on every OS/browser.
    filename = (
        f"certificate_{certificate_id}_{slugify(certificate.recipient_name)}.pdf"
    )
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=filename,
    )
