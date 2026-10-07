import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.certificate import CertificateRecord, CertificateStatus
from app.models.job import Job, JobStatus


@pytest.mark.asyncio
async def test_create_job_valid_payload(client: AsyncClient, db_session: Session) -> None:
    """Test creating a bulk job with a valid recipient payload returns 202 and stores pending records."""
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

    # Verify database state
    job_uuid = uuid.UUID(data["job_id"])
    job = db_session.execute(select(Job).where(Job.id == job_uuid)).scalar_one_or_none()
    assert job is not None
    assert job.status == JobStatus.PENDING
    assert job.total_count == 3
    assert job.success_count == 0
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
        assert r.status == CertificateStatus.PENDING
        assert r.file_path is None
