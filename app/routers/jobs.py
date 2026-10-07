import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.job import JobCreateRequest, JobCreateResponse
from app.services import job_service
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
