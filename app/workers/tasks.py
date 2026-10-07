import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database import SessionLocal
from app.models.certificate import CertificateRecord, CertificateStatus
from app.models.job import Job, JobStatus
from app.services.certificate_service import generate_certificate

logger = logging.getLogger(__name__)


def process_certificate_job(
    job_id: uuid.UUID,
    session_factory: sessionmaker | None = None,
) -> None:
    """Process all certificate records in a bulk job with isolated per-recipient error handling.

    Each certificate is rendered within its own try/except block. If an individual recipient
    generation fails (e.g. invalid data, template error), that record is marked FAILED and its
    error message is saved. Other records continue processing unaffected, and the parent job
    transitions to COMPLETED_WITH_ERRORS if at least one certificate succeeded.
    """
    factory = session_factory or SessionLocal
    db: Session = factory()
    try:
        stmt = select(Job).where(Job.id == job_id)
        job = db.execute(stmt).scalar_one_or_none()
        if not job:
            logger.error("Bulk job worker: Job '%s' not found.", job_id)
            return

        # Transition to PROCESSING
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        # Fetch records belonging to this job
        records_stmt = (
            select(CertificateRecord)
            .where(CertificateRecord.job_id == job_id)
            .order_by(CertificateRecord.created_at.asc())
        )
        records = list(db.execute(records_stmt).scalars().all())

        for record in records:
            # Per-record failure isolation boundary
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
                logger.info(
                    "Generated certificate for record %s (%s)",
                    record.id,
                    record.recipient_name,
                )
            except Exception as exc:
                record.status = CertificateStatus.FAILED
                record.error_message = str(exc)
                record.file_path = None
                job.failure_count += 1
                logger.warning(
                    "Failure isolated for record %s (%s): %s",
                    record.id,
                    record.recipient_name,
                    exc,
                )

            # Persist progress after each record for real-time visibility
            job.updated_at = datetime.now(timezone.utc)
            db.commit()

        # Determine final job outcome
        if job.failure_count == 0 and job.success_count > 0:
            job.status = JobStatus.COMPLETED
        elif job.success_count > 0 and job.failure_count > 0:
            job.status = JobStatus.COMPLETED_WITH_ERRORS
        else:
            job.status = JobStatus.FAILED

        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "Completed bulk job %s: status=%s, total=%d, success=%d, failed=%d",
            job.id,
            job.status.value,
            job.total_count,
            job.success_count,
            job.failure_count,
        )

    except Exception as exc:
        logger.exception("Catastrophic error in bulk job %s: %s", job_id, exc)
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
