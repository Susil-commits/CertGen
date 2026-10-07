import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.certificate import CertificateRecordResponse
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobStatusResponse
from app.services import job_service
from app.utils.exceptions import JobNotFoundError
from app.workers.tasks import process_certificate_job

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.post(
    "/",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobCreateResponse,
    summary="Submit a bulk certificate generation job",
)
def create_job_endpoint(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """Accepts a list of recipients, creates a Job with PENDING status,

    and enqueues background processing.
    """
    job = job_service.create_job(db=db, recipients=payload.recipients)
    background_tasks.add_task(process_certificate_job, job.id)
    return JobCreateResponse.model_validate(job)


@router.get(
    "/{job_id}/",
    response_model=JobStatusResponse,
    summary="Get job execution status and counts",
)
def get_job_status_endpoint(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    """Retrieve current processing status and progress counters for a bulk job."""
    try:
        job = job_service.get_job(db=db, job_id=job_id)
        return JobStatusResponse.model_validate(job)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{job_id}/records/",
    response_model=list[CertificateRecordResponse],
    summary="List all recipient records for a job",
)
def get_job_records_endpoint(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[CertificateRecordResponse]:
    """Retrieve detailed generation records for each recipient in a bulk job."""
    try:
        records = job_service.get_job_records(db=db, job_id=job_id)
        return [CertificateRecordResponse.model_validate(r) for r in records]
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
