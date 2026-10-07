import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.certificate import CertificateRecord, CertificateStatus
from app.models.job import Job, JobStatus
from app.schemas.certificate import RecipientInput
from app.utils.exceptions import JobNotFoundError


def create_job(db: Session, recipients: list[RecipientInput]) -> Job:
    """Create a new certificate generation Job and associated CertificateRecord rows.

    All records and the parent job are initially set to PENDING status.
    """
    job = Job(
        status=JobStatus.PENDING,
        total_count=len(recipients),
        success_count=0,
        failure_count=0,
    )
    db.add(job)
    db.flush()  # Populate job.id for foreign keys

    records = [
        CertificateRecord(
            job_id=job.id,
            recipient_name=r.name.strip(),
            recipient_email=r.email.strip() if r.email else None,
            status=CertificateStatus.PENDING,
        )
        for r in recipients
    ]
    db.add_all(records)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: uuid.UUID) -> Job:
    """Retrieve a Job by its UUID.

    Raises JobNotFoundError if the job does not exist.
    """
    stmt = select(Job).where(Job.id == job_id)
    job = db.execute(stmt).scalar_one_or_none()
    if not job:
        raise JobNotFoundError(f"Job with ID '{job_id}' was not found.")
    return job


def get_job_records(db: Session, job_id: uuid.UUID) -> list[CertificateRecord]:
    """Retrieve all certificate records belonging to a Job.

    Raises JobNotFoundError if the job does not exist.
    """
    # Verify job existence first
    get_job(db, job_id)

    stmt = (
        select(CertificateRecord)
        .where(CertificateRecord.job_id == job_id)
        .order_by(CertificateRecord.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())
