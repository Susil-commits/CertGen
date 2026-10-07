import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.certificate import CertificateRecord, CertificateStatus
from app.models.job import Job, JobStatus
from app.services.certificate_service import generate_certificate

logger = logging.getLogger(__name__)


def process_certificate_job(job_id: uuid.UUID) -> None:
    """Background task to process all certificate records for a bulk generation job.

    Opens its own dedicated DB session to ensure clean isolation from the request lifespan.
    """
    db: Session = SessionLocal()
    try:
        stmt = select(Job).where(Job.id == job_id)
        job = db.execute(stmt).scalar_one_or_none()
        if not job:
            logger.error("Background task could not find job %s", job_id)
            return

        # Transition job status to PROCESSING
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        # Retrieve all pending records
        records_stmt = (
            select(CertificateRecord)
            .where(CertificateRecord.job_id == job_id)
            .order_by(CertificateRecord.created_at.asc())
        )
        records = list(db.execute(records_stmt).scalars().all())

        for record in records:
            try:
                recipient_dict = {
                    "record_id": str(record.id),
                    "name": record.recipient_name,
                    "email": record.recipient_email,
                }
                file_path = generate_certificate(
                    recipient=recipient_dict,
                    record_id=record.id,
                    output_format="pdf",
                )
                record.status = CertificateStatus.SUCCESS
                record.file_path = file_path
                record.error_message = None
                job.success_count += 1
            except Exception as exc:
                record.status = CertificateStatus.FAILED
                record.error_message = str(exc)
                job.failure_count += 1
                logger.warning(
                    "Error processing certificate for record %s: %s",
                    record.id,
                    exc,
                )

            job.updated_at = datetime.now(timezone.utc)
            db.commit()

        # Update final job status
        if job.failure_count == 0:
            job.status = JobStatus.COMPLETED
        elif job.success_count > 0:
            job.status = JobStatus.COMPLETED_WITH_ERRORS
        else:
            job.status = JobStatus.FAILED

        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "Job %s finished with status %s (Success: %d, Failures: %d)",
            job_id,
            job.status.value,
            job.success_count,
            job.failure_count,
        )

    except Exception as exc:
        logger.exception("Unexpected error in background job %s: %s", job_id, exc)
        try:
            stmt = select(Job).where(Job.id == job_id)
            job = db.execute(stmt).scalar_one_or_none()
            if job:
                job.status = JobStatus.FAILED
                job.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
