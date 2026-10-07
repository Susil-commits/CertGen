import logging
import time
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
    """Process all certificate records in a bulk job with isolated per-recipient error handling

    and structured logging.
    """
    factory = session_factory or SessionLocal
    db: Session = factory()
    job_start_time = time.perf_counter()

    try:
        stmt = select(Job).where(Job.id == job_id)
        job = db.execute(stmt).scalar_one_or_none()
        if not job:
            logger.error(
                "Bulk job not found for processing",
                extra={"event": "job_not_found", "job_id": str(job_id)},
            )
            return

        # Transition to PROCESSING
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Bulk job execution started",
            extra={
                "event": "job_started",
                "job_id": str(job_id),
                "total_count": job.total_count,
            },
        )

        # Fetch records belonging to this job
        records_stmt = (
            select(CertificateRecord)
            .where(CertificateRecord.job_id == job_id)
            .order_by(CertificateRecord.created_at.asc())
        )
        records = list(db.execute(records_stmt).scalars().all())

        for record in records:
            rec_start_time = time.perf_counter()
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
                duration_ms = round((time.perf_counter() - rec_start_time) * 1000, 2)
                record.status = CertificateStatus.SUCCESS
                record.file_path = file_path
                record.error_message = None
                job.success_count += 1

                logger.info(
                    "Certificate generated successfully",
                    extra={
                        "event": "certificate_success",
                        "job_id": str(job_id),
                        "record_id": str(record.id),
                        "recipient_name": record.recipient_name,
                        "duration_ms": duration_ms,
                    },
                )
            except Exception as exc:
                duration_ms = round((time.perf_counter() - rec_start_time) * 1000, 2)
                record.status = CertificateStatus.FAILED
                record.error_message = str(exc)
                record.file_path = None
                job.failure_count += 1

                logger.warning(
                    "Isolated certificate generation failure",
                    extra={
                        "event": "certificate_failure",
                        "job_id": str(job_id),
                        "record_id": str(record.id),
                        "recipient_name": record.recipient_name,
                        "error_message": str(exc),
                        "duration_ms": duration_ms,
                    },
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

        total_duration_ms = round((time.perf_counter() - job_start_time) * 1000, 2)
        logger.info(
            "Bulk job completed",
            extra={
                "event": "job_completed",
                "job_id": str(job.id),
                "status": job.status.value,
                "total_count": job.total_count,
                "success_count": job.success_count,
                "failure_count": job.failure_count,
                "total_duration_ms": total_duration_ms,
            },
        )

    except Exception as exc:
        logger.exception(
            "Catastrophic error in bulk job",
            extra={"event": "job_catastrophic_failure", "job_id": str(job_id), "error": str(exc)},
        )
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
