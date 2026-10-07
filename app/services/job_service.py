import logging
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.certificate import CertificateRecord, CertificateStatus
from app.models.job import Job, JobStatus
from app.schemas.certificate import RecipientInput
from app.utils.exceptions import JobNotFoundError

logger = logging.getLogger(__name__)


def create_job(db: Session, recipients: list[RecipientInput]) -> Job:
    """Create a new certificate generation Job and associated CertificateRecord rows.

    Detects duplicates and sets all records and parent job to PENDING status.
    """
    # Check for duplicate recipient entries
    seen_recipients = set()
    duplicate_count = 0
    for r in recipients:
        key = (r.name.strip().lower(), (r.email or "").strip().lower())
        if key in seen_recipients:
            duplicate_count += 1
        seen_recipients.add(key)

    if duplicate_count > 0:
        logger.warning(
            "Bulk job contains %d duplicate recipient entry/entries; generating distinct records for each.",
            duplicate_count,
            extra={"duplicate_count": duplicate_count},
        )

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
