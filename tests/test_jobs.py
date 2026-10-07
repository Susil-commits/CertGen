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


@pytest.mark.asyncio
async def test_job_status_transitions(client: AsyncClient) -> None:
    """Test retrieving job status and records via GET endpoints, verifying transitions and 404s."""
    payload = {
        "recipients": [
            {"name": "Claude Shannon", "email": "shannon@bell-labs.com"},
            {"name": "John von Neumann", "email": "vonneumann@ias.edu"},
        ]
    }

    # 1. Create Job
    post_res = await client.post("/api/jobs/", json=payload)
    assert post_res.status_code == 202
    job_id = post_res.json()["job_id"]

    # 2. Get Job Status
    get_job_res = await client.get(f"/api/jobs/{job_id}/")
    assert get_job_res.status_code == 200
    job_data = get_job_res.json()
    assert job_data["job_id"] == job_id
    assert job_data["status"] == "COMPLETED"
    assert job_data["total_count"] == 2
    assert job_data["success_count"] == 2
    assert job_data["failure_count"] == 0
    assert "created_at" in job_data
    assert "updated_at" in job_data

    # 3. Get Job Records
    records_res = await client.get(f"/api/jobs/{job_id}/records/")
    assert records_res.status_code == 200
    records_data = records_res.json()
    assert len(records_data) == 2
    for item in records_data:
        assert "record_id" in item
        assert item["status"] == "SUCCESS"
        assert item["recipient_name"] in ["Claude Shannon", "John von Neumann"]
        assert item["file_path"] is not None

    # 4. Check 404 for unknown job ID
    unknown_job_id = uuid.uuid4()
    not_found_job = await client.get(f"/api/jobs/{unknown_job_id}/")
    assert not_found_job.status_code == 404
    assert "not found" in not_found_job.json()["detail"].lower()

    not_found_records = await client.get(f"/api/jobs/{unknown_job_id}/records/")
    assert not_found_records.status_code == 404
    assert "not found" in not_found_records.json()["detail"].lower()


@pytest.mark.asyncio
async def test_download_generated_certificate(client: AsyncClient) -> None:
    """Test downloading a successfully generated certificate file and handling not-found cases."""
    payload = {
        "recipients": [
            {"name": "Tim Berners-Lee", "email": "timbl@w3.org"},
        ]
    }

    post_res = await client.post("/api/jobs/", json=payload)
    assert post_res.status_code == 202
    job_id = post_res.json()["job_id"]

    records_res = await client.get(f"/api/jobs/{job_id}/records/")
    assert records_res.status_code == 200
    record_id = records_res.json()[0]["record_id"]

    # Download certificate
    download_res = await client.get(f"/api/certificates/{record_id}/download/")
    assert download_res.status_code == 200
    assert download_res.headers["content-type"] in ["application/pdf", "image/png"]
    assert len(download_res.content) > 0

    # Test downloading non-existent record
    unknown_record_id = uuid.uuid4()
    missing_res = await client.get(f"/api/certificates/{unknown_record_id}/download/")
    assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_download_failed_certificate_returns_409(client: AsyncClient) -> None:
    """Test that attempting to download a FAILED certificate returns HTTP 409 with reason."""
    payload = {
        "recipients": [
            {"name": "__FORCE_FAIL__", "email": "fail@example.com"},
        ]
    }

    post_res = await client.post("/api/jobs/", json=payload)
    assert post_res.status_code == 202
    job_id = post_res.json()["job_id"]

    records_res = await client.get(f"/api/jobs/{job_id}/records/")
    assert records_res.status_code == 200
    failed_record_id = records_res.json()[0]["record_id"]

    download_res = await client.get(f"/api/certificates/{failed_record_id}/download/")
    assert download_res.status_code == 409
    detail = download_res.json()["detail"]
    assert "failed" in detail.lower()
    assert "simulated generation error" in detail.lower()


@pytest.mark.asyncio
async def test_job_with_duplicate_recipients(client: AsyncClient) -> None:
    """Test that duplicate recipients in a batch each receive isolated, distinct records and certificates."""
    payload = {
        "recipients": [
            {"name": "Marie Curie", "email": "marie@sorbonne.fr"},
            {"name": "Marie Curie", "email": "marie@sorbonne.fr"},
        ]
    }

    post_res = await client.post("/api/jobs/", json=payload)
    assert post_res.status_code == 202
    job_id = post_res.json()["job_id"]

    # Verify job status
    job_res = await client.get(f"/api/jobs/{job_id}/")
    assert job_res.status_code == 200
    assert job_res.json()["total_count"] == 2
    assert job_res.json()["success_count"] == 2

    # Verify both records exist with distinct record IDs
    records_res = await client.get(f"/api/jobs/{job_id}/records/")
    records = records_res.json()
    assert len(records) == 2
    assert records[0]["record_id"] != records[1]["record_id"]
    assert records[0]["status"] == "SUCCESS"
    assert records[1]["status"] == "SUCCESS"
    assert records[0]["file_path"] != records[1]["file_path"]


@pytest.mark.asyncio
async def test_minimal_frontend_served(client: AsyncClient) -> None:
    """Test that the minimal frontend UI is accessible at /ui."""
    res = await client.get("/ui")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Bulk" in res.text
    assert "Certificate" in res.text
