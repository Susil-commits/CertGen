import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import certificate_service
from app.utils.exceptions import (
    CertificateFileNotReadyError,
    CertificateRecordNotFoundError,
)

router = APIRouter(prefix="/api/certificates", tags=["Certificates"])


@router.get(
    "/{record_id}/download/",
    summary="Download generated certificate file",
    response_class=FileResponse,
)
def download_certificate_endpoint(
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download a recipient's completed certificate file.

    Returns HTTP 404 if the record does not exist or if generation has not succeeded.
    """
    try:
        file_path = certificate_service.get_certificate_file_path(
            db=db,
            record_id=record_id,
        )
        media_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "image/png"
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=file_path.name,
        )
    except CertificateRecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except CertificateFileNotReadyError as exc:
        # Per spec: serves the generated file (404 if not SUCCESS)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
