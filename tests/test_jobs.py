import uuid
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.certificate import CertificateRecord, CertificateStatus
from app.models.job import Job, JobStatus


@pytest.mark.asyncio
async def test_create_job_valid_payload(client: AsyncClient, db_session: Session) -> None:
    """Test creating a bulk job with a valid recipient payload returns 202 and processes records."""
    payload = {
        "recipients": [
            {"name": "Ada Lovelace", "email": "ada@example.com"},
            {"name": "Alan Turing", "email": "alan@example.com"},
            {"name": "Grace Hopper"},
        ]
    }

    response = await client.post("/api/jobs/", json=payload)
    assert response.status_code == 202

    data = response.json()
    assert "job_id" in data
    assert data["status"] == "PENDING"
    assert data["total_count"] == 3

    # Verify database state after background processing
    job_uuid = uuid.UUID(data["job_id"])
    job = db_session.execute(select(Job).where(Job.id == job_uuid)).scalar_one_or_none()
    assert job is not None
    assert job.status == JobStatus.COMPLETED
    assert job.total_count == 3
    assert job.success_count == 3
    assert job.failure_count == 0

    records = (
        db_session.execute(
            select(CertificateRecord).where(CertificateRecord.job_id == job_uuid)
        )
        .scalars()
        .all()
    )
    assert len(records) == 3
    names = [r.recipient_name for r in records]
    assert "Ada Lovelace" in names
    assert "Alan Turing" in names
    assert "Grace Hopper" in names
    for r in records:
        assert r.status == CertificateStatus.SUCCESS
        assert r.file_path is not None
        assert Path(r.file_path).exists()


@pytest.mark.asyncio
async def test_certificate_generation_partial_failure(
    client: AsyncClient, db_session: Session
) -> None:
    """Test that a failure in one recipient is isolated: valid recipients succeed,

    the bad recipient is marked FAILED with an error message, and the job status
    transitions to COMPLETED_WITH_ERRORS.
    """
    payload = {
        "recipients": [
            {"name": "Margaret Hamilton", "email": "apollo@nasa.gov"},
            {"name": "__FORCE_FAIL__", "email": "error@example.com"},
            {"name": "Hedy Lamarr", "email": "hedy@example.com"},
        ]
    }

    response = await client.post("/api/jobs/", json=payload)
    assert response.status_code == 202
    job_id = uuid.UUID(response.json()["job_id"])

    # Query DB to inspect isolated per-record status
    job = db_session.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
    assert job is not None
    assert job.status == JobStatus.COMPLETED_WITH_ERRORS
    assert job.total_count == 3
    assert job.success_count == 2
    assert job.failure_count == 1

    records = (
        db_session.execute(
            select(CertificateRecord)
            .where(CertificateRecord.job_id == job_id)
            .order_by(CertificateRecord.created_at.asc())
        )
        .scalars()
        .all()
    )
    assert len(records) == 3

    # Find the isolated failed record
    failed_rec = next(r for r in records if r.recipient_name == "__FORCE_FAIL__")
    assert failed_rec.status == CertificateStatus.FAILED
    assert failed_rec.file_path is None
    assert failed_rec.error_message is not None
    assert "Simulated generation error" in failed_rec.error_message

    # Verify other records succeeded normally
    success_recs = [r for r in records if r.recipient_name != "__FORCE_FAIL__"]
    assert len(success_recs) == 2
    for rec in success_recs:
        assert rec.status == CertificateStatus.SUCCESS
        assert rec.error_message is None
        assert rec.file_path is not None
        assert Path(rec.file_path).exists()
